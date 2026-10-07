"""Check interrupted and mismatched downloads without using the network."""
import hashlib
import json
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

main = runpy.run_path(str(Path(__file__).with_name('prepare-fixtures.py')))['main']
SOURCE = b'verified-source'
manifest = {'fixtures': [{'id': 'sample', 'filename': 'sample.wav', 'source_url': 'https://example.org/sample.wav', 'sha256': hashlib.sha256(SOURCE).hexdigest()}]}
references = {'fixtures': [{'id': 'sample', 'prepared_path': 'audio16k/sample.wav'}]}
original_read_text = Path.read_text


def fixture_text(path, *args, **kwargs):
    if path.name == 'audio-sources.json':
        return json.dumps(manifest)
    if path.name == 'fixture-references.json':
        return json.dumps(references)
    return original_read_text(path, *args, **kwargs)


def fake_ffmpeg(command, **kwargs):
    Path(command[-1]).write_bytes(b'prepared-wave')


class FixtureDownloadTests(unittest.TestCase):
    def run_download(self, folder, callback):
        with patch('sys.argv', ['prepare-fixtures.py', '--download', '--output', str(folder)]), \
                patch.object(Path, 'read_text', fixture_text), \
                patch('shutil.which', return_value='ffmpeg'), \
                patch('urllib.request.urlretrieve', side_effect=callback), \
                patch('subprocess.run', side_effect=fake_ffmpeg):
            main()

    def test_bad_existing_file_is_replaced_after_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'originals').mkdir()
            source = folder / 'originals/sample.wav'
            source.write_bytes(b'partial')
            self.run_download(folder, lambda url, path: Path(path).write_bytes(SOURCE))
            self.assertEqual(source.read_bytes(), SOURCE)
            self.assertTrue((folder / 'fixtures.json').exists())

    def test_hash_mismatch_does_not_replace_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'originals').mkdir()
            source = folder / 'originals/sample.wav'
            source.write_bytes(b'old')
            with self.assertRaises(ValueError):
                self.run_download(folder, lambda url, path: Path(path).write_bytes(b'changed'))
            self.assertEqual(source.read_bytes(), b'old')
            self.assertFalse(source.with_suffix('.wav.partial').exists())

    def test_interrupted_download_cleans_partial_file(self):
        def interrupt(url, path):
            Path(path).write_bytes(b'incomplete')
            raise OSError('interrupted download')
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            with self.assertRaises(OSError):
                self.run_download(folder, interrupt)
            self.assertFalse((folder / 'originals/sample.wav').exists())
            self.assertFalse((folder / 'originals/sample.wav.partial').exists())


if __name__ == '__main__':
    unittest.main()
