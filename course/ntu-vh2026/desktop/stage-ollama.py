"""Stage the pinned official Ollama CLI distribution, with its original libraries."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
VERSION = '0.35.1'
URL = f'https://github.com/ollama/ollama/releases/download/v{VERSION}/ollama-darwin.tgz'
SHA256 = '3137dbf28948ee844e0fb3e584d9b5de6879d73d9f0cb7eff3ad64930601d307'
LICENSE_URL = f'https://raw.githubusercontent.com/ollama/ollama/v{VERSION}/LICENSE'
LICENSE_SHA256 = '5934ed2ce0d15154bcdb9c85203210abac0da4314af34081e36df4599f90b226'


def fetch_verified(url, target, digest):
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == digest:
        return
    partial = target.with_suffix(target.suffix + '.partial')
    try:
        subprocess.run(['/usr/bin/curl', '-q', '-fL', '--retry', '2', '--connect-timeout', '15',
                        '--max-time', '600', url, '-o', str(partial)], check=True)
        if hashlib.sha256(partial.read_bytes()).hexdigest() != digest:
            raise ValueError('Official Ollama download checksum mismatch')
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, default=ROOT.parent / 'installer/resources/runtimes/ollama')
    args = parser.parse_args()
    cache = ROOT / '.cache'
    cache.mkdir(exist_ok=True)
    if shutil.disk_usage(cache).free < 6 * 1024 ** 3:
        raise SystemExit('Keep at least 6 GiB free before staging Ollama.')
    archive = cache / f'ollama-darwin-{VERSION}.tgz'
    fetch_verified(URL, archive, SHA256)
    license_file = cache / f'OLLAMA-LICENSE-{VERSION}'
    fetch_verified(LICENSE_URL, license_file, LICENSE_SHA256)
    if args.destination.exists():
        raise SystemExit('Destination already exists. Preserve or remove the previous staging directory explicitly.')
    args.destination.mkdir(parents=True)
    subprocess.run(['/usr/bin/tar', '-xzf', str(archive), '-C', str(args.destination)], check=True)
    if not (args.destination / 'ollama').is_file():
        candidate = args.destination / 'bin/ollama'
        if not candidate.is_file():
            raise RuntimeError('Official archive did not contain the expected Ollama executable')
        (args.destination / 'ollama').symlink_to('bin/ollama')
    shutil.copy2(license_file, args.destination / 'OLLAMA-LICENSE')
    (args.destination / 'runtime-source.json').write_text(json.dumps({
        'name': 'Ollama', 'version': VERSION, 'url': URL, 'sha256': SHA256,
        'license_url': LICENSE_URL, 'license_sha256': LICENSE_SHA256,
        'source': f'https://github.com/ollama/ollama/tree/v{VERSION}',
    }, indent=2) + '\n')
    print(args.destination.resolve())


if __name__ == '__main__':
    main()
