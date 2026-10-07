"""Stream a signed .app into <=1.8GB release parts without a second giant archive.

Optional upload targets an existing draft release. A temporary part is deleted
only after GitHub confirms its SHA256 and byte count. The signed app is untouched.
"""
import argparse
import hashlib
import json
import os
import shutil
import shlex
import subprocess
import tempfile
from pathlib import Path

PART_BYTES = 1800000000


def github_asset(repo, tag, name):
    result = subprocess.run(['gh', 'api', f'repos/{repo}/releases?per_page=100'],
                            check=True, capture_output=True, text=True)
    release = next((row for row in json.loads(result.stdout) if row['tag_name'] == tag), None)
    if release is None:
        raise RuntimeError('The draft release was not found')
    if not release['draft']:
        raise RuntimeError('Upload packaging requires a draft release')
    return next((row for row in release['assets'] if row['name'] == name), None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--repo', default='dAAAb/airi')
    parser.add_argument('--upload-release')
    args = parser.parse_args()
    if not args.prefix.replace('-', '').replace('_', '').isalnum():
        parser.error('Use a simple asset name prefix')
    app = args.app.resolve(strict=True)
    if app.suffix != '.app':
        parser.error('Expected an .app bundle')
    args.output = args.output.resolve()
    if args.output == app or args.output.is_relative_to(app):
        parser.error('The archive output must be outside the app bundle')
    args.output.mkdir(parents=True, exist_ok=True)
    record_path = args.output / (args.prefix + '-parts.json')
    if record_path.exists():
        raise RuntimeError('Use a fresh output directory for each packaging run')
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)
    tar = subprocess.Popen(['/usr/bin/tar', '-cf', '-', '-C', str(app.parent), app.name],
        stdout=subprocess.PIPE, env=dict(os.environ, COPYFILE_DISABLE='1'))
    gzip = subprocess.Popen(['/usr/bin/gzip', '-n', '-1'], stdin=tar.stdout, stdout=subprocess.PIPE)
    tar.stdout.close()
    parts = []
    try:
        while True:
            first = gzip.stdout.read(min(1024 * 1024, PART_BYTES))
            if not first:
                break
            if shutil.disk_usage(args.output).free < PART_BYTES + 5 * 1024**3:
                raise RuntimeError('Leave 5 GiB free while creating each part')
            name = f'{args.prefix}.tar.gz.part-{len(parts) + 1:03d}'
            path = args.output / name
            digest, size = hashlib.sha256(), 0
            with path.open('xb') as target:
                block = first
                while block:
                    target.write(block)
                    digest.update(block)
                    size += len(block)
                    if size == PART_BYTES:
                        break
                    block = gzip.stdout.read(min(1024 * 1024, PART_BYTES - size))
            row = {'name': name, 'bytes': size, 'sha256': digest.hexdigest()}
            parts.append(row)
            record_path.write_text(json.dumps({'app': app.name, 'parts': parts}, indent=2) + '\n')
            print(json.dumps(row), flush=True)
            if args.upload_release:
                existing = github_asset(args.repo, args.upload_release, name)
                if existing is None:
                    subprocess.run(['gh', 'release', 'upload', args.upload_release, str(path), '--repo', args.repo], check=True)
                asset = github_asset(args.repo, args.upload_release, name)
                if not asset or asset['size'] != size or asset.get('digest') != 'sha256:' + row['sha256']:
                    raise RuntimeError('GitHub asset checksum was not confirmed; local part retained')
                path.unlink()
        if gzip.wait() or tar.wait():
            raise RuntimeError('Archive process failed')
    except BaseException:
        gzip.terminate()
        tar.terminate()
        raise
    finally:
        gzip.stdout.close()
    (args.output / (args.prefix + '.sha256')).write_text(''.join(f'{r["sha256"]}  {r["name"]}\n' for r in parts))
    assembler = args.output / ('Open-' + args.prefix + '.command')
    assembler.write_text('''#!/bin/zsh
set -euo pipefail
installer_dir="${0:A:h}"
cd "$installer_dir"
# Finder unzips the small Installer.zip into a folder beside the downloaded parts.
if [[ ! -f ''' + args.prefix + '''.tar.gz.part-001 && -f ../''' + args.prefix + '''.tar.gz.part-001 ]]; then
  cd ..
fi
print 'Checking all downloaded parts…'
/usr/bin/shasum -a 256 -c "$installer_dir/''' + args.prefix + '''.sha256"
unpack_dir=$(/usr/bin/mktemp -d "./AIRI-unpacked.XXXXXX")
print 'Extracting the signed application…'
/bin/cat ''' + ' '.join(row['name'] for row in parts) + ''' | /usr/bin/tar -xzf - -C "$unpack_dir"
/usr/bin/codesign --verify --deep --strict "$unpack_dir"/''' + shlex.quote(app.name) + '''
print "Verified. The application is in $unpack_dir. Move it to Applications if desired."
/usr/bin/open "$unpack_dir"
''')
    assembler.chmod(0o755)
    # A .command downloaded alone can lose its executable bit. Shipping it in a
    # ZIP preserves its mode for Finder users and keeps the checksums beside it.
    installer_zip = args.output / (args.prefix + '-Installer.zip')
    with tempfile.TemporaryDirectory(prefix='.assembler-', dir=args.output) as temporary:
        folder = Path(temporary) / (args.prefix + '-Installer')
        folder.mkdir()
        for source in (assembler, record_path, args.output / (args.prefix + '.sha256')):
            shutil.copy2(source, folder / source.name)
        (folder / 'READ-ME.txt').write_text(
            '將全部 .tar.gz.part-* 分片與 Installer.zip 下載到同一個資料夾。\n'
            '解壓 Installer.zip 後，雙擊裡面的 Open-*.command。\n'
            '程式先驗證每段 SHA256，再解壓並檢查 App 簽章。\n'
            '也可在終端機執行：zsh Open-*.command。\n\n'
            'Download every part and Installer.zip into one folder. Unzip the installer,\n'
            'then double-click its Open-*.command. Checksums are verified before extraction.\n')
        subprocess.run(['/usr/bin/ditto', '-c', '-k', '--sequesterRsrc', '--keepParent',
                        str(folder), str(installer_zip)], check=True)
    print('Packaging complete:', record_path, 'Installer:', installer_zip, flush=True)


if __name__ == '__main__':
    main()
