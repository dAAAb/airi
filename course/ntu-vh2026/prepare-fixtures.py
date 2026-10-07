"""Fetch public source files or use local copies, then prepare mono 16 kHz PCM."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true', help='Fetch source files after reviewing their terms')
    parser.add_argument('--source-dir', type=Path, help='Directory containing original files named in audio-sources.json')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent / 'local')
    args = parser.parse_args()
    if not args.download and args.source_dir is None:
        parser.error('Use --source-dir or explicitly opt in with --download')
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / 'sources/audio-sources.json').read_text())
    references = json.loads((root / 'sources/fixture-references.json').read_text())
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        parser.error('Install ffmpeg and add it to PATH')
    sources = args.source_dir or args.output / 'originals'
    sources.mkdir(parents=True, exist_ok=True)
    (args.output / 'audio16k').mkdir(parents=True, exist_ok=True)
    for row in manifest['fixtures']:
        path = sources / row['filename']
        source_matches = path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
        if not source_matches and args.download:
            url = row['source_url']
            if row['id'].startswith('ml2021'):
                with urllib.request.urlopen(url, timeout=60) as response:
                    meta = json.load(response)
                url = meta['rows'][0]['row']['audio'][0]['src']
            temporary = path.with_suffix(path.suffix + ".partial")
            try:
                urllib.request.urlretrieve(url, temporary)
                if hashlib.sha256(temporary.read_bytes()).hexdigest() != row["sha256"]:
                    raise ValueError(f'Source changed: {row["id"]}. Review the new source instead of reusing old results.')
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        if not path.exists():
            raise FileNotFoundError(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError(f'Source changed: {row["id"]}. Review the new source instead of reusing old results.')
        destination = args.output / 'audio16k' / (row['id'] + '.wav')
        subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-i', str(path), '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(destination)], check=True)
        fixture = next(x for x in references['fixtures'] if x['id'] == row['id'])
        fixture['prepared_sha256'] = hashlib.sha256(destination.read_bytes()).hexdigest()
        fixture['sha256_note'] = 'Original hash is pinned. Resampled WAV headers can differ with FFmpeg versions.'
        print('prepared', row['id'])
    (args.output / 'fixtures.json').write_text(json.dumps(references, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
