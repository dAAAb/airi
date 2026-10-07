"""Fetch fixed public sources and weights, with hashes and atomic replacement."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import runpy
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
verify = runpy.run_path(str(ROOT.parent / 'model-assets.py'))['verify']


def safe_path(root, name):
    value = PurePosixPath(name)
    if not name or value.is_absolute() or '..' in value.parts or '\\' in name:
        raise ValueError('Unsafe manifest path')
    target = (root / name).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError('Manifest path escapes destination')
    return target


def download(row, root=ROOT):
    target = safe_path(root, row['destination'])
    safe_path(root, row['file'])
    if target.is_file() and verify(target, row):
        print('verified', row['destination'])
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, suffix='.partial', delete=False) as f:
        temporary = Path(f.name)
    try:
        url = f"https://huggingface.co/{row['repo']}/resolve/{row['revision']}/{row['file']}"
        subprocess.run(['curl', '-fL', '--retry', '3', '--silent', '--show-error',
                        url, '-o', str(temporary)], check=True)
        if not verify(temporary, row):
            raise RuntimeError('Checksum mismatch: ' + row['destination'])
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    print('downloaded', row['destination'])


def prepare_source(source):
    destination = safe_path(ROOT, source['destination'])
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix='.source-', dir=ROOT))
        try:
            for args in [
                ['init', str(temporary)],
                ['-C', str(temporary), 'remote', 'add', 'origin', source['url']],
                ['-C', str(temporary), 'fetch', '--depth=1', 'origin', source['commit']],
                ['-C', str(temporary), 'checkout', '--detach', 'FETCH_HEAD'],
            ]:
                subprocess.run(['git', *args], check=True, capture_output=True)
            temporary.replace(destination)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    head = subprocess.check_output(['git', '-C', str(destination), 'rev-parse', 'HEAD'], text=True).strip()
    if head != source['commit']:
        raise RuntimeError('Existing source has another revision. Preserve your changes and use a fresh directory.')
    subprocess.run(['git', '-C', str(destination), 'diff', '--quiet', 'HEAD'], check=True)
    reference = safe_path(destination, source['reference_file'])
    if hashlib.sha256(reference.read_bytes()).hexdigest() != source['reference_sha256']:
        raise RuntimeError('Upstream synthetic reference hash mismatch')
    print('verified source and reference', head)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backend', choices=['kaedetai', 'mms'])
    parser.add_argument('--download', action='store_true', help='Fetch files after reviewing README licenses')
    parser.add_argument('--source-only', action='store_true', help='With kaedetai --download: fetch pinned source/reference only, no weights')
    args = parser.parse_args()
    if args.source_only and (args.backend != 'kaedetai' or not args.download):
        parser.error('--source-only requires kaedetai --download')
    manifest = json.loads((ROOT / 'source-manifest.json').read_text())
    selected = [r for r in manifest['files'] if r['destination'].startswith(args.backend + '/')]
    if args.download and args.backend == 'kaedetai':
        prepare_source(manifest['upstream'])
        if args.source_only:
            return
    for row in selected:
        if args.download:
            download(row)
        else:
            target = safe_path(ROOT, row['destination'])
            if not target.is_file() or not verify(target, row):
                raise SystemExit('Missing or mismatched: ' + row['destination'] + '. Review licenses, then use --download.')
            print('verified', row['destination'])


if __name__ == '__main__':
    main()
