"""Create a small Mac downloader for the fixed NTU classroom GitHub release.

The generated .command needs only macOS system utilities, not Python or Xcode.
Hashes and filenames are embedded from the finished multipart manifest.
"""
import argparse
import json
import re
import shlex
import stat
import zipfile
from pathlib import Path

RELEASE_URL = 'https://github.com/dAAAb/airi/releases/download/v0.1.0-ntu2026-local'
DEFAULT_RELEASE_TAG = 'v0.1.0-ntu2026-local'
MARGIN_BYTES = 2 * 1024**3


def release_url(tag):
    if not isinstance(tag, str) or not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+-ntu2026-local', tag):
        raise ValueError('Expected a versioned NTU classroom release tag')
    return f'https://github.com/dAAAb/airi/releases/download/{tag}'


def validate_manifest(value, prefix):
    if not isinstance(prefix, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,100}', prefix):
        raise ValueError('Expected a simple release filename prefix')
    if not isinstance(value, dict):
        raise ValueError('Expected a manifest object')
    app = value.get('app')
    if not isinstance(app, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _-]{0,100}\.app', app):
        raise ValueError('Expected a plain .app basename')
    parts = value.get('parts')
    if not isinstance(parts, list) or not 1 <= len(parts) <= 999:
        raise ValueError('Expected 1 to 999 parts')
    for index, row in enumerate(parts, 1):
        if not isinstance(row, dict) or row.get('name') != f'{prefix}.tar.gz.part-{index:03d}':
            raise ValueError('Part names must be contiguous from 001 and match the prefix')
        if type(row.get('bytes')) is not int or not 0 < row['bytes'] <= 1800000000:
            raise ValueError('Expected a positive part size below the GitHub asset limit')
        if not isinstance(row.get('sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', row['sha256']):
            raise ValueError('Expected a lowercase SHA256 digest')
    return {'app': app, 'parts': parts}


def render_command(manifest, prefix, unpacked_bytes, release_tag=DEFAULT_RELEASE_TAG):
    manifest = validate_manifest(manifest, prefix)
    if type(unpacked_bytes) is not int or unpacked_bytes <= 0:
        raise ValueError('Expected the positive unpacked app size')
    parts = manifest['parts']
    if unpacked_bytes + sum(row['bytes'] for row in parts) + MARGIN_BYTES >= 2**63:
        raise ValueError('Combined sizes exceed the shell integer range')
    names = ' '.join(shlex.quote(row['name']) for row in parts)
    hashes = ' '.join(shlex.quote(row['sha256']) for row in parts)
    sizes = ' '.join(str(row['bytes']) for row in parts)
    template = Path(__file__).with_name('download-installer-template.zsh').read_text()
    values = {
        '@@PREFIX@@': shlex.quote(prefix), '@@APP@@': shlex.quote(manifest['app']),
        '@@URL@@': shlex.quote(release_url(release_tag)), '@@NAMES@@': names,
        '@@HASHES@@': hashes, '@@SIZES@@': sizes,
        '@@UNPACKED@@': str(unpacked_bytes), '@@MARGIN@@': str(MARGIN_BYTES),
        '@@TOTAL@@': str(sum(row['bytes'] for row in parts)),
    }
    for key, value in values.items():
        template = template.replace(key, value)
    return template


def generate(manifest_path, output, unpacked_bytes, release_tag=DEFAULT_RELEASE_TAG):
    if not manifest_path.name.endswith('-parts.json'):
        raise ValueError('Expected <prefix>-parts.json')
    prefix = manifest_path.name.removesuffix('-parts.json')
    manifest = validate_manifest(json.loads(manifest_path.read_text()), prefix)
    command = render_command(manifest, prefix, unpacked_bytes, release_tag)
    output.mkdir(parents=True, exist_ok=True)
    command_path = output / f'Download-{prefix}.command'
    zip_path = output / f'{prefix}-Downloader.zip'
    if command_path.exists() or zip_path.exists():
        raise FileExistsError('Refusing to replace an existing downloader')
    readme = (
        '下載這個小 ZIP 後解壓，雙擊 Download-*.command。\n'
        '請把解壓後的安裝器資料夾放到有足夠空間的磁碟再執行。\n'
        '程式會顯示所需空間，從固定 GitHub release 下載缺少的分片，支援續傳。\n'
        '每片 SHA256 通過後才解壓 App。成功下載的分片保留在安裝器資料夾內，可離線搬運。\n'
        'Full／Lite App 已包含對應模型。Thin App 開啟後仍需選取下載模型。\n'
        'App 使用 ad-hoc 簽章，未經 Apple notarization。此程式不改 Gatekeeper。\n'
        '若 macOS 阻擋，請依系統提示自行決定是否允許，勿使用來路不明的繞過指令。\n\n'
        f'Release: {release_url(release_tag)}\n'
        f'Archive parts: {sum(row["bytes"] for row in manifest["parts"])} bytes\n'
        f'Unpacked app: {unpacked_bytes} bytes\n'
        f'Free-space margin: {MARGIN_BYTES} bytes\n'
    )
    command_path.write_text(command)
    command_path.chmod(0o755)
    folder = f'{prefix}-InstallerDownload'
    entries = [(command_path.name, command.encode(), 0o755),
               ('READ-ME.txt', readme.encode(), 0o644),
               (manifest_path.name, (json.dumps(manifest, indent=2) + '\n').encode(), 0o644)]
    with zipfile.ZipFile(zip_path, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data, mode in entries:
            entry = zipfile.ZipInfo(f'{folder}/{name}')
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | mode) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data)
    return command_path, zip_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--unpacked-bytes', type=int, required=True)
    parser.add_argument('--release-tag', default=DEFAULT_RELEASE_TAG)
    args = parser.parse_args()
    for path in generate(args.manifest, args.output, args.unpacked_bytes, args.release_tag):
        print(path)


if __name__ == '__main__':
    main()
