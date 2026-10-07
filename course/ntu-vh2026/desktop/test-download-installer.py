"""Run generated downloaders against tiny local fixtures and a fake curl."""
import copy
import gzip
import hashlib
import importlib.util
import io
import json
import os
import shlex
import stat
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

spec = importlib.util.spec_from_file_location('downloader', Path(__file__).with_name('generate-download-installer.py'))
downloader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(downloader)


class DownloadInstallerTests(unittest.TestCase):
    def test_release_version_stays_on_fixed_repository(self):
        self.assertEqual(downloader.release_url('v0.2.0-ntu2026-local'),
                         'https://github.com/dAAAb/airi/releases/download/v0.2.0-ntu2026-local')
        for value in ('https://example.com', '../v0.2.0-ntu2026-local', 'v0.2.0-ntu2026-local?a=b', None):
            with self.assertRaises(ValueError):
                downloader.release_url(value)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = self.root / 'fixture'
        self.fixture.mkdir()
        self.prefix = 'AIRI-Test-arm64'
        self.app = 'AIRI Local Full.app'
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode='w') as tar:
            data = b'tiny app fixture, not a real executable'
            item = tarfile.TarInfo(self.app + '/Contents/fixture.txt')
            item.size = len(data)
            tar.addfile(item, io.BytesIO(data))
        packed = gzip.compress(archive.getvalue(), mtime=0)
        cut = len(packed) // 2
        self.manifest = {'app': self.app, 'parts': []}
        for index, data in enumerate([packed[:cut], packed[cut:]], 1):
            name = f'{self.prefix}.tar.gz.part-{index:03d}'
            (self.fixture / name).write_bytes(data)
            self.manifest['parts'].append({'name': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
        self.installer = self.root / 'installer'
        self.installer.mkdir()
        self.parts = self.installer / (self.prefix + '-parts')
        self.parts.mkdir()
        self.bin = self.root / 'fake-bin'
        self.bin.mkdir()
        self.fake_curl = self.fake('curl', '''#!/usr/bin/env python3
import os, sys
from pathlib import Path
args = sys.argv[1:]
assert args[args.index('--continue-at') + 1] == '-'
url = args[-1]
assert url.startswith('https://github.com/dAAAb/airi/releases/download/v0.1.0-ntu2026-local/')
with open(os.environ['CURL_LOG'], 'a') as log: log.write(url + '\\n')
source = Path(os.environ['FIXTURE_DIR']) / url.rsplit('/', 1)[1]
content = source.read_bytes()
if os.environ.get('CORRUPT') == '1': content = b'!' + content[1:]
target = Path(args[args.index('--output') + 1])
offset = target.stat().st_size if target.exists() else 0
with target.open('ab') as out: out.write(content[offset:])
''')
        self.fake_sign = self.fake('codesign', '''#!/bin/sh
printf '%s\\n' "$*" >> "$SIGN_LOG"
''')
        self.fake_open = self.fake('open', '''#!/bin/sh
printf '%s\\n' "$*" >> "$OPEN_LOG"
''')
        self.env = dict(os.environ, FIXTURE_DIR=str(self.fixture), CURL_LOG=str(self.root / 'curl.log'),
                        SIGN_LOG=str(self.root / 'sign.log'), OPEN_LOG=str(self.root / 'open.log'))

    def fake(self, name, source):
        path = self.bin / name
        path.write_text(source)
        path.chmod(0o755)
        return path

    def run_installer(self, *, corrupt=False, no_space=False):
        source = downloader.render_command(self.manifest, self.prefix, 1024)
        # Dependency substitution exists only in the test copy. Production
        # commands use fixed macOS tool paths and expose no executable override.
        for original, replacement in [('/usr/bin/curl', self.fake_curl),
                                      ('/usr/bin/codesign', self.fake_sign), ('/usr/bin/open', self.fake_open)]:
            source = source.replace(original, shlex.quote(str(replacement)))
        if no_space:
            df = self.fake('df', '#!/bin/sh\nprintf "Filesystem 1024-blocks Used Available Capacity Mounted on\\nfixture 1 1 0 100%% /\\n"\n')
            source = source.replace('/bin/df', shlex.quote(str(df)))
        script = self.installer / f'Download-{self.prefix}.command'
        script.write_text(source)
        return subprocess.run(['/bin/zsh', str(script)], env=dict(self.env, CORRUPT='1' if corrupt else '0'),
                              text=True, capture_output=True, timeout=20)

    def test_downloads_missing_parts_verifies_then_extracts(self):
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len((self.root / 'curl.log').read_text().splitlines()), 2)
        self.assertEqual(len(list(self.installer.glob('AIRI-unpacked.*/' + self.app + '/Contents/fixture.txt'))), 1)
        self.assertTrue((self.root / 'sign.log').exists())
        self.assertTrue((self.root / 'open.log').exists())
        for row in self.manifest['parts']:
            self.assertEqual((self.parts / row['name']).read_bytes(), (self.fixture / row['name']).read_bytes())

    def test_verified_existing_part_is_not_downloaded_again(self):
        first = self.manifest['parts'][0]
        (self.parts / first['name']).write_bytes((self.fixture / first['name']).read_bytes())
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = (self.root / 'curl.log').read_text().splitlines()
        self.assertEqual(calls, [downloader.RELEASE_URL + '/' + self.manifest['parts'][1]['name']])

    def test_partial_download_resumes_and_matches_hash(self):
        first = self.manifest['parts'][0]
        original = (self.fixture / first['name']).read_bytes()
        (self.parts / (first['name'] + '.partial')).write_bytes(original[:7])
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.parts / first['name']).read_bytes(), original)

    def test_wrong_hash_never_extracts_or_verifies_signature(self):
        result = self.run_installer(corrupt=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SHA256', result.stderr)
        self.assertFalse(list(self.installer.glob('AIRI-unpacked.*')))
        self.assertFalse((self.root / 'sign.log').exists())
        self.assertFalse((self.root / 'open.log').exists())

    def test_complete_verified_partial_is_promoted_without_download(self):
        for row in self.manifest['parts']:
            (self.parts / (row['name'] + '.partial')).write_bytes((self.fixture / row['name']).read_bytes())
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / 'curl.log').exists())

    def test_complete_damaged_partial_stops_without_download(self):
        row = self.manifest['parts'][0]
        (self.parts / (row['name'] + '.partial')).write_bytes(b'!' * row['bytes'])
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SHA256', result.stderr)
        self.assertFalse((self.root / 'curl.log').exists())
        self.assertFalse(list(self.installer.glob('AIRI-unpacked.*')))

    def test_low_disk_space_stops_before_download(self):
        result = self.run_installer(no_space=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('磁碟空間不足', result.stderr)
        self.assertFalse((self.root / 'curl.log').exists())

    def test_symlink_part_is_rejected_without_writes(self):
        first = self.manifest['parts'][0]
        (self.parts / first['name']).symlink_to(self.fixture / first['name'])
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / 'curl.log').exists())

    def test_manifest_rejects_paths_injection_holes_and_invalid_hashes(self):
        for prefix in ('../x', 'x;echo', 'x\n', '-x'):
            with self.assertRaises(ValueError):
                downloader.validate_manifest(self.manifest, prefix)
        for key, value in [('name', self.prefix + '.tar.gz.part-003'), ('bytes', 0), ('bytes', True),
                           ('bytes', 1800000001), ('sha256', 'wrong'), ('sha256', 'A' * 64)]:
            invalid = copy.deepcopy(self.manifest)
            invalid['parts'][0][key] = value
            with self.assertRaises(ValueError):
                downloader.validate_manifest(invalid, self.prefix)
        for app in ('../Bad.app', '/tmp/Bad.app', 'Bad$(id).app', 'Bad\n.app'):
            invalid = dict(self.manifest, app=app)
            with self.assertRaises(ValueError):
                downloader.validate_manifest(invalid, self.prefix)

    def test_zip_preserves_executable_mode_and_fixed_release(self):
        path = self.root / (self.prefix + '-parts.json')
        path.write_text(json.dumps(self.manifest))
        command, archive = downloader.generate(path, self.root / 'output', 1024)
        self.assertEqual(stat.S_IMODE(command.stat().st_mode), 0o755)
        self.assertIn(downloader.RELEASE_URL, command.read_text())
        with zipfile.ZipFile(archive) as bundle:
            entry = next(row for row in bundle.infolist() if row.filename.endswith('.command'))
            self.assertEqual(stat.S_IMODE(entry.external_attr >> 16), 0o755)
        with self.assertRaises(FileExistsError):
            downloader.generate(path, self.root / 'output', 1024)


if __name__ == '__main__':
    unittest.main()
