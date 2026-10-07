"""Download the recorded revision, then verify each file. No inference upload."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request


def verify(path, row):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return path.stat().st_size == row['bytes'] and digest.hexdigest() == row['sha256']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model', choices=['asr26', 'breeze2'])
    parser.add_argument('--download', action='store_true', help='Download missing or mismatched files')
    parser.add_argument('--model-dir', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent / args.model
    manifest = json.loads((root / 'model-manifest.json').read_text())
    destination = (args.model_dir or root / 'model').expanduser()
    for row in manifest['files']:
        if Path(row['file']).name != row['file']:
            raise ValueError('Manifest must contain flat filenames')
        target = destination / row['file']
        if target.exists() and verify(target, row):
            print('verified', row['file'])
            continue
        if not args.download:
            raise SystemExit(f'Missing or mismatched: {target}. Use --download after reviewing the model license.')
        destination.mkdir(parents=True, exist_ok=True)
        url = f"https://huggingface.co/{manifest['repo']}/resolve/{manifest['revision']}/{row['file']}"
        temporary = target.with_suffix(target.suffix + '.partial')
        urllib.request.urlretrieve(url, temporary)
        if not verify(temporary, row):
            temporary.unlink(missing_ok=True)
            raise RuntimeError(f'Integrity check failed: {row["file"]}')
        temporary.replace(target)
        print('downloaded and verified', row['file'])


if __name__ == '__main__':
    main()
