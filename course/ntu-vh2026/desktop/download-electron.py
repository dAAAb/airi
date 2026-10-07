"""Download the pinned official Apple Silicon Electron archive and verify SHA256."""
import hashlib
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
VERSION = '43.4.1'
NAME = f'electron-v{VERSION}-darwin-arm64.zip'
URL = f'https://github.com/electron/electron/releases/download/v{VERSION}/{NAME}'
# Official v43.4.1 SHASUMS256.txt, checked 2026-10-07.
SHA256 = 'fe3cac8cbfd9ba1739fac6c69166cf30848741f93cbe251d800ae6ef7cebb64b'


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    cache = ROOT / '.cache'
    cache.mkdir(exist_ok=True)
    archive = cache / NAME
    if not archive.exists() or sha(archive) != SHA256:
        if shutil.disk_usage(cache).free < 6 * 1024 ** 3:
            raise SystemExit('Keep at least 6 GiB free before downloading Electron.')
        partial = archive.with_suffix('.zip.partial')
        try:
            # macOS curl uses the system CA setup. Never disable TLS verification.
            subprocess.run(['/usr/bin/curl', '-q', '-fL', '--retry', '2', '--connect-timeout', '15',
                            '--max-time', '600', URL, '-o', str(partial)], check=True)
            if sha(partial) != SHA256:
                raise ValueError('Electron archive SHA256 mismatch')
            partial.replace(archive)
        finally:
            partial.unlink(missing_ok=True)
    extracted = cache / f'electron-{VERSION}-arm64'
    if not (extracted / 'Electron.app').exists():
        extracted.mkdir(exist_ok=True)
        # ditto preserves framework symlinks and executable modes from this verified archive.
        subprocess.run(['/usr/bin/ditto', '-x', '-k', str(archive), str(extracted)], check=True)
    print(extracted / 'Electron.app')


if __name__ == '__main__':
    main()
