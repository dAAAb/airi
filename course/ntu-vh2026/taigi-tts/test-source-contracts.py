"""No network, weights or GPU. Check safe downloads and local configuration."""
import hashlib
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
prepare = runpy.run_path(str(ROOT / 'prepare.py'))
config = runpy.run_path(str(ROOT / 'loopback-config.py'))['configuration']


class Contracts(unittest.TestCase):
    def test_paths_cannot_escape(self):
        for path in ['../outside', '/absolute', 'folder/../../escape', 'x\\y']:
            with self.assertRaises(ValueError):
                prepare['safe_path'](ROOT, path)

    def test_symlink_cannot_escape(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / 'link').symlink_to(root.parent)
            with self.assertRaises(ValueError):
                prepare['safe_path'](root, 'link/outside')

    def test_failed_download_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            old = root / 'model.bin'
            old.write_bytes(b'original')
            row = {'destination': 'model.bin', 'file': 'model.bin', 'repo': 'test/model',
                   'revision': 'a'*40, 'bytes': 4, 'sha256': hashlib.sha256(b'good').hexdigest()}
            def corrupt(args, **kwargs):
                Path(args[-1]).write_bytes(b'bad')
            with patch('subprocess.run', side_effect=corrupt), self.assertRaises(RuntimeError):
                prepare['download'](row, root)
            self.assertEqual(old.read_bytes(), b'original')
            self.assertEqual(list(root.glob('*.partial')), [])

    def test_installer_port(self):
        with patch.dict(os.environ, {'AIRI_TAIGI_PORT': '18883',
                'AIRI_TAIGI_ALLOWED_ORIGINS': 'http://127.0.0.1:17900'}, clear=True):
            self.assertEqual(config(), (18883, ['http://127.0.0.1:17900']))

    def test_remote_origins_rejected(self):
        for origin in ['https://localhost:5174', 'http://example.com', 'http://localhost/path',
                'http://user@localhost', 'file://local', 'http://localhost:99999', '*']:
            with patch.dict(os.environ, {'AIRI_TAIGI_ALLOWED_ORIGINS': origin}, clear=True):
                with self.assertRaises(ValueError):
                    config()


if __name__ == '__main__':
    unittest.main()
