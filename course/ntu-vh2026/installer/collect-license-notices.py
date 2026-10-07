"""Collect upstream notices and source archives for the tested Mac runtime.

Run during release preparation, never from the HTTP installer. Downloaded source
is archived and inspected as data. No upstream setup or build script is executed.
"""
import argparse
import ast
import concurrent.futures
import hashlib
import json
import re
import subprocess
import tarfile
import tempfile
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NOTICES = [
    ('gemma-terms.txt', 'https://ai.google.dev/gemma/terms'),
    ('gemma-prohibited-use-policy.txt', 'https://ai.google.dev/gemma/prohibited_use_policy'),
    ('Apache-2.0.txt', 'https://www.apache.org/licenses/LICENSE-2.0.txt'),
    ('sarc-model-card.md', 'https://huggingface.co/Speech-AI-Research-Center/SARC-Taigi-LLM-12b-GGUF/raw/main/README.md'),
    ('gemma4-model-card.md', 'https://huggingface.co/google/gemma-4-12B-it/raw/main/README.md'),
    ('qwen-model-card.md', 'https://huggingface.co/Qwen/Qwen3.5-0.8B/raw/main/README.md'),
    ('qwen-Apache-2.0.txt', 'https://huggingface.co/Qwen/Qwen3.5-0.8B/raw/main/LICENSE'),
    ('breeze-asr26-model-card.md', 'https://huggingface.co/MediaTek-Research/Breeze-ASR-26/raw/main/README.md'),
    ('breeze-asr26-mlx-model-card.md', 'https://huggingface.co/RayyTien/Breeze-ASR-26-mlx-4bit/raw/main/README.md'),
    ('kokoro-model-card.md', 'https://huggingface.co/hexgrad/Kokoro-82M/raw/main/README.md'),
    ('kokoro-voices.md', 'https://huggingface.co/hexgrad/Kokoro-82M/raw/main/VOICES.md'),
    ('kaedetai-model-card.md', 'https://huggingface.co/KaedeTai/gpt-sovits-tw/raw/fa251907be54b63277377a96a23377fd7f00e323/README.md'),
    ('kaedetai-MIT.txt', 'https://raw.githubusercontent.com/KaedeTai/GPT-SoVITS/81959852f75c972a0a78364f8ea6b14133a11f4a/LICENSE'),
    ('gpt-sovits-base-model-card.md', 'https://huggingface.co/lj1995/GPT-SoVITS/raw/main/README.md'),
    ('chinese-hubert-base-model-card.md', 'https://huggingface.co/TencentGameMate/chinese-hubert-base/raw/main/README.md'),
    ('eres2net-model-card.md', 'https://modelscope.cn/api/v1/models/iic/speech_eres2netv2w24s4ep4_sv_zh-cn_16k-common/repo?Revision=master&FilePath=README.md'),
    ('3d-speaker-Apache-2.0.txt', 'https://raw.githubusercontent.com/modelscope/3D-Speaker/main/LICENSE'),
    ('taibun-MIT.txt', 'https://raw.githubusercontent.com/andreihar/taibun/main/LICENSE'),
    ('taibun-model-card.md', 'https://raw.githubusercontent.com/andreihar/taibun/main/README.md'),
    ('CC-BY-SA-4.0.txt', 'https://creativecommons.org/licenses/by-sa/4.0/legalcode.txt'),
    ('ollama-MIT.txt', 'https://raw.githubusercontent.com/ollama/ollama/v0.35.1/LICENSE'),
    ('GPL-3.0.txt', 'https://www.gnu.org/licenses/gpl-3.0.txt'),
    ('GPL-2.0.txt', 'https://www.gnu.org/licenses/old-licenses/gpl-2.0.txt'),
    ('LGPL-3.0.txt', 'https://www.gnu.org/licenses/lgpl-3.0.txt'),
    ('LGPL-2.1.txt', 'https://www.gnu.org/licenses/old-licenses/lgpl-2.1.txt'),
    ('espeakng-loader-MIT.txt', 'https://raw.githubusercontent.com/thewh1teagle/espeakng-loader/main/LICENSE'),
    ('MIT-standard.txt', 'https://raw.githubusercontent.com/spdx/license-list-data/main/text/MIT.txt'),
    ('CC-BY-3.0.txt', 'https://creativecommons.org/licenses/by/3.0/legalcode.txt'),
    ('CC-BY-4.0.txt', 'https://creativecommons.org/licenses/by/4.0/legalcode.txt'),
    ('libsndfile-mac-build.sh.txt', 'https://raw.githubusercontent.com/bastibe/libsndfile-binaries/a3e6f9769d0c7e91d2d036cf0fdbe5b4bbf18b87/mac_build.sh'),
    ('libsndfile-darwin.cmake.txt', 'https://raw.githubusercontent.com/bastibe/libsndfile-binaries/a3e6f9769d0c7e91d2d036cf0fdbe5b4bbf18b87/darwin.cmake'),
    ('libsndfile-binary-README.md', 'https://raw.githubusercontent.com/bastibe/libsndfile-binaries/a3e6f9769d0c7e91d2d036cf0fdbe5b4bbf18b87/README.md'),
]


class ArticleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_article = False
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == 'article':
            self.in_article = True
        if tag in ('script', 'style', 'svg'):
            self.skip += 1
        if self.in_article and not self.skip:
            if tag in ('p', 'li', 'h1', 'h2', 'h3', 'br'):
                self.parts.append('\n\n')
            if tag == 'a':
                href = dict(attrs).get('href', '')
                if href.startswith('https://'):
                    self.parts.append(f' [{href}] ')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'svg') and self.skip:
            self.skip -= 1
        if tag == 'article':
            self.in_article = False
        if self.in_article and tag in ('p', 'li', 'h1', 'h2', 'h3'):
            self.parts.append('\n\n')

    def handle_data(self, data):
        if self.in_article and not self.skip:
            self.parts.append(re.sub(r'\s+', ' ', data))


def collect_notice(name, url, output):
    if name not in ('gemma-terms.txt', 'gemma-prohibited-use-policy.txt'):
        return download(url, output / name)
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary) / 'source.html'
        original = download(url, source)
        parser = ArticleText()
        parser.feed(source.read_text())
        text = re.sub(r'\n\s*\n(?:\s*\n)+', '\n\n', ''.join(parser.parts)).strip()
        if len(text) < 1500:
            raise ValueError(f'Incomplete legal article: {name}')
        target = output / name
        target.write_text(f'Official source: {url}\nRetrieved: 2026-10-07\n\n{text}\n')
        return {'file': name, 'source': url, 'source_html_sha256': original['sha256'],
                'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'bytes': target.stat().st_size}


def download(url, target, expected=None):
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.is_file():
        temporary = target.with_name(target.name + '.partial')
        subprocess.run(['curl', '--fail', '--location', '--silent', '--show-error',
                        '--max-time', '90', '--max-filesize', '104857600',
                        '--retry', '2', url, '-o', str(temporary)], check=True)
        temporary.replace(target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if expected and digest != expected:
        raise ValueError(f'SHA-256 mismatch: {target.name}')
    return {'file': target.name, 'source': url, 'sha256': digest, 'bytes': target.stat().st_size}


def pypi_source(name, version, output):
    metadata = output / f'{name}-{version}.pypi.json'
    download(f'https://pypi.org/pypi/{name}/{version}/json', metadata)
    data = json.loads(metadata.read_text())
    source = next((row for row in data['urls'] if row['packagetype'] == 'sdist'), None)
    if source is None:
        raise ValueError(f'No source distribution is published for {name} {version}')
    return download(source['url'], output / source['filename'], source['digests']['sha256'])


def recipe_sources(recipe):
    # Parse literal URL/hash fields without executing the downloaded Python.
    with tarfile.open(recipe) as archive:
        text = archive.extractfile('pyav-ffmpeg-9.0.2-1/scripts/pkg.py').read().decode()
    names = {'lamer', 'opus', 'dav1d', 'libsvtav1', 'vpx', 'png', 'webp', 'libvmaf', 'x264', 'x265', 'ffmpeg'}
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'Package':
            row = {arg.arg: arg.value.value for arg in node.keywords
                   if isinstance(arg.value, ast.Constant) and isinstance(arg.value.value, str)}
            if row.get('name') in names:
                yield row


def extract_notices(source, output):
    """Copy only small notice text members. Never extract paths from an archive."""
    if not tarfile.is_tarfile(source):
        return
    with tarfile.open(source) as archive:
        count = 0
        for member in archive.getmembers():
            name = Path(member.name).name.lower()
            if not member.isfile() or member.size > 200_000:
                continue
            if name.startswith(('license', 'licence', 'copying', 'copyright', 'notice')):
                content = archive.extractfile(member).read()
                target = output / f'{source.name}.{count:03d}.{Path(member.name).name}.txt'
                target.write_bytes(content)
                count += 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'resources/licenses')
    parser.add_argument('--notices-only', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    records, errors = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        work = {pool.submit(collect_notice, name, url, output): name for name, url in NOTICES}
        for future in concurrent.futures.as_completed(work):
            try:
                records.append(future.result())
            except Exception as error:
                errors.append({'file': work[future], 'error': str(error)})
    (output / 'NOTICE-Gemma.txt').write_text(
        'SARC-Taigi-LLM-12b is a Gemma 3 derivative.\n'
        'Gemma is provided under and subject to the Gemma Terms of Use found at ai.google.dev/gemma/terms\n'
        'The full terms and prohibited-use policy accompany this file.\n'
        'Gemma 4 is separately distributed under Apache License 2.0.\n')
    if not args.notices_only:
        sources = output / 'source'
        sources.mkdir(exist_ok=True)
        recipe = sources / 'pyav-ffmpeg-9.0.2-1.tar.gz'
        recipe_record = download('https://github.com/PyAV-Org/pyav-ffmpeg/archive/refs/tags/9.0.2-1.tar.gz', recipe)
        recipe_record['file'] = 'source/' + recipe_record['file']
        records.append(recipe_record)
        archives = [(row['source_url'], sources / (row.get('source_filename') or row['source_url'].rsplit('/', 1)[-1]), row['sha256'])
                    for row in recipe_sources(recipe)]
        archives += [
            ('https://github.com/espeak-ng/espeak-ng/archive/refs/tags/1.52.0.tar.gz', sources / 'espeak-ng-1.52.0.tar.gz', None),
            ('https://github.com/thewh1teagle/espeakng-loader/archive/146599e29be31bf17d99f0bcb7dbb2f92aef3d95.tar.gz', sources / 'espeakng-loader-0.2.4-146599e.tar.gz', None),
            ('https://github.com/libsndfile/libsndfile/releases/download/1.2.2/libsndfile-1.2.2.tar.xz', sources / 'libsndfile-1.2.2.tar.xz', None),
            ('https://downloads.xiph.org/releases/ogg/libogg-1.3.5.tar.gz', sources / 'libogg-1.3.5.tar.gz', None),
            ('https://downloads.xiph.org/releases/vorbis/libvorbis-1.3.7.tar.gz', sources / 'libvorbis-1.3.7.tar.gz', None),
            ('https://downloads.xiph.org/releases/flac/flac-1.4.3.tar.xz', sources / 'flac-1.4.3.tar.xz', None),
            ('https://downloads.xiph.org/releases/opus/opus-1.4.tar.gz', sources / 'opus-1.4.tar.gz', None),
            ('https://downloads.sourceforge.net/project/mpg123/mpg123/1.32.3/mpg123-1.32.3.tar.bz2', sources / 'mpg123-1.32.3.tar.bz2', None),
            ('https://downloads.sourceforge.net/project/lame/lame/3.100/lame-3.100.tar.gz', sources / 'lame-3.100.tar.gz', None),
        ]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            work = {pool.submit(download, url, target, sha): target.name for url, target, sha in archives}
            for name, version in [('av', '19.0.1'), ('phonemizer-fork', '3.3.2'), ('soundfile', '0.13.0')]:
                work[pool.submit(pypi_source, name, version, sources)] = f'{name}-{version}'
            for future in concurrent.futures.as_completed(work):
                try:
                    row = future.result()
                    row['file'] = 'source/' + row['file']
                    records.append(row)
                except Exception as error:
                    errors.append({'file': work[future], 'error': str(error)})
        extracted = output / 'source-notices'
        extracted.mkdir(exist_ok=True)
        for row in records:
            if row['file'].startswith('source/'):
                extract_notices(output / row['file'], extracted)
    (output / 'upstream-source-manifest.json').write_text(json.dumps(sorted(records, key=lambda row: row['file']), ensure_ascii=False, indent=2) + '\n')
    (output / 'collection-errors.json').write_text(json.dumps(errors, ensure_ascii=False, indent=2) + '\n')
    (output / 'THIRD-PARTY-NOTICES.md').write_text((ROOT / 'THIRD-PARTY-NOTICES.md').read_text())
    # Only our earlier generated pages are removed. Runtime serves legal text, never third-party scripts.
    for name in ('gemma-terms.html', 'gemma-prohibited-use-policy.html'):
        (output / name).unlink(missing_ok=True)
    print(json.dumps({'recorded': len(records), 'errors': errors}, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
