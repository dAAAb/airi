"""Stage the public pinned manifest; optionally download verified speech weights.

Ollama's model store is prepared separately with bundle-ollama-models.py.
The desktop builder sets the offline flag only for a complete full app.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.request
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent


def confined(root, relative):
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Invalid payload path')
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError('Payload path escapes its destination')
    return resolved


def validate(manifest):
    paths = set()
    for row in manifest['files']:
        confined(Path('/payload'), row['path'])
        if row['path'] in paths:
            raise ValueError('Repeated payload path')
        paths.add(row['path'])
        parsed = urlsplit(row['url'])
        pinned_hf = parsed.hostname == 'huggingface.co' and re.search(r'/resolve/[0-9a-f]{40}/', parsed.path)
        pinned_motion_meta = (row['model'] == 'motiongpt' and parsed.hostname == 'raw.githubusercontent.com'
                              and re.fullmatch(r'/OpenMotionLab/MotionGPT/[0-9a-f]{40}/assets/meta/(mean|std)\.npy', parsed.path))
        if parsed.scheme != 'https' or not (pinned_hf or pinned_motion_meta):
            raise ValueError('Model downloads require a pinned, allowlisted HTTPS revision')
        if row['model'] not in ('asr26', 'kaedetai', 'kokoro', 'motiongpt') or type(row['bytes']) is not int or row['bytes'] < 1:
            raise ValueError('Invalid model or file size')
        if not re.fullmatch(r'[0-9a-f]{64}', row['sha256']):
            raise ValueError('Invalid SHA256')
    for row in manifest['services']:
        confined(Path('/resources'), row['executable'])


def verified(path, row):
    if not path.is_file() or path.stat().st_size != row['bytes']:
        return False
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest() == row['sha256']


class TLSRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme != 'https':
            raise ValueError('Refusing a non-HTTPS redirect')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(row, root):
    target = confined(root, row['path'])
    if verified(target, row):
        return 'verified'
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        opener = urllib.request.build_opener(TLSRedirect())
        with opener.open(row['url'], timeout=60) as response, tempfile.NamedTemporaryFile(dir=target.parent, prefix=target.name+'.', suffix='.partial', delete=False) as output:
            temporary = Path(output.name)
            size = 0
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > row['bytes']:
                    raise ValueError('Download exceeds its pinned size')
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if not verified(temporary, row):
            raise ValueError('Downloaded checksum differs from the pinned release')
        temporary.replace(target)
        return 'downloaded'
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resources', type=Path, default=ROOT/'resources')
    parser.add_argument('--download-speech', action='store_true', help='Download about 2.72 GB, after reviewing the model licenses')
    parser.add_argument('--verify-speech', action='store_true', help='Verify all speech files without network access')
    args = parser.parse_args()
    manifest = json.loads((ROOT/'model-manifest.json').read_text())
    validate(manifest)
    args.resources.mkdir(parents=True, exist_ok=True)
    for row in manifest['files']:
        # Download-only research weights belong in each user's data directory,
        # never in the public installer payload, even when preparing a Full app.
        if row['model'] in manifest.get('download_only_models', []):
            continue
        if args.download_speech:
            print(download(row, args.resources/'payload'), row['path'])
        elif args.verify_speech:
            if not verified(confined(args.resources/'payload', row['path']), row):
                raise ValueError('Missing or mismatched payload: '+row['path'])
            print('verified', row['path'])
    target = args.resources/'payload-manifest.json'
    with tempfile.NamedTemporaryFile(mode='w', dir=args.resources, prefix='payload-manifest.', suffix='.partial', delete=False) as output:
        temporary = Path(output.name)
        json.dump(manifest, output, ensure_ascii=False, indent=2)
        output.write('\n')
    try:
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    print('Staged payload-manifest.json (offline=false; full builder sets offline=true)')


if __name__ == '__main__':
    main()
