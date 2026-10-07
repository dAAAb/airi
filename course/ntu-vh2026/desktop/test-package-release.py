"""Exercise multipart/installer ZIP mechanics with a small unsigned fixture.

Only codesign is mocked; tar, gzip, ditto, SHA256 and zsh syntax checks are real.
The built Mac apps are signed and checked separately before release.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SCRIPT = Path(__file__).with_name('package-release.py')
spec = importlib.util.spec_from_file_location('package_release', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PackagingTest(unittest.TestCase):
    def test_stream_parts_and_finder_installer_keep_content_and_permissions(self):
        original_run = subprocess.run

        def run_without_codesign(command, **kwargs):
            if Path(command[0]).name == 'codesign':
                return subprocess.CompletedProcess(command, 0)
            return original_run(command, **kwargs)

        with tempfile.TemporaryDirectory(prefix='airi-package-test-') as temporary:
            root = Path(temporary)
            app = root / 'AIRI Test.app'
            (app / 'Contents').mkdir(parents=True)
            payload = app / 'Contents' / 'test.bin'
            payload.write_bytes(bytes(range(256)) * 100)
            (app / 'Contents' / 'test-link').symlink_to('test.bin')
            output = root / 'release'
            with patch.object(sys, 'argv', ['package-release.py', str(app), '--output', str(output), '--prefix', 'AIRI-Test']), \
                    patch.object(module, 'PART_BYTES', 256), \
                    patch.object(module.subprocess, 'run', run_without_codesign):
                module.main()
            record = json.loads((output / 'AIRI-Test-parts.json').read_text())
            self.assertGreater(len(record['parts']), 1)
            combined = root / 'combined.tar.gz'
            with combined.open('wb') as target:
                for row in record['parts']:
                    data = (output / row['name']).read_bytes()
                    self.assertEqual(len(data), row['bytes'])
                    self.assertEqual(hashlib.sha256(data).hexdigest(), row['sha256'])
                    target.write(data)
            with tarfile.open(combined, 'r:gz') as archive:
                self.assertEqual(archive.extractfile('AIRI Test.app/Contents/test.bin').read(), payload.read_bytes())
                self.assertTrue(archive.getmember('AIRI Test.app/Contents/test-link').issym())
            command = output / 'Open-AIRI-Test.command'
            original_run(['/bin/zsh', '-n', str(command)], check=True)
            with zipfile.ZipFile(output / 'AIRI-Test-Installer.zip') as archive:
                info = archive.getinfo('AIRI-Test-Installer/Open-AIRI-Test.command')
                self.assertTrue((info.external_attr >> 16) & 0o111)
                self.assertIn('AIRI-Test-Installer/AIRI-Test.sha256', archive.namelist())


if __name__ == '__main__':
    unittest.main()
