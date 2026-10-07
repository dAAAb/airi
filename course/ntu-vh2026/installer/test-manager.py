"""Installer trust boundaries without downloading weights or starting engines."""
import hashlib
import importlib.util
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('manager', Path(__file__).with_name('manager.py'))
manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manager)


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.resources = root / 'resources'
        self.resources.mkdir()
        self.app = manager.LocalManager(root / 'data', self.resources)

    def item(self, content=b'model'):
        return {'model': 'kokoro', 'path': 'kokoro/model.bin', 'bytes': len(content),
                'sha256': hashlib.sha256(content).hexdigest(),
                'url': 'https://huggingface.co/test/model/resolve/fixed/model.bin'}

    def test_paths_cannot_escape_even_through_symlinks(self):
        for value in ('../secret', '/etc/passwd'):
            with self.assertRaises(ValueError):
                manager.confined(self.resources, value)
        (self.resources / 'escape').symlink_to(self.resources.parent, target_is_directory=True)
        with self.assertRaises(ValueError):
            manager.confined(self.resources, 'escape/secret')

    def test_http_cannot_choose_arbitrary_model_or_mode(self):
        for body in ({'models': ['shell:rm']}, {'models': ['kokoro'], 'ollama_mode': 'https://evil'},
                     {'models': '__class__'}, {'models': []}):
            with self.assertRaises(ValueError):
                self.app.start_job(body)

    def test_download_requires_specific_license_selection(self):
        with self.assertRaises(ValueError):
            self.app.start_job({'models': ['sarc-taigi'], 'accepted_licenses': ['kokoro']})

    def test_verified_offline_file_never_fetches(self):
        item = self.item()
        destination = self.resources / 'payload' / item['path']
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b'model')
        with patch.object(manager.urllib.request, 'urlopen', side_effect=AssertionError('network')):
            self.app.install_file(item)
        self.assertFalse((self.app.data / 'payload').exists())

    def test_damaged_offline_file_never_downloads_or_marks_ready(self):
        (self.resources / 'payload-manifest.json').write_text(json.dumps({'offline': True}))
        item = self.item()
        path = self.resources / 'payload' / item['path']
        path.parent.mkdir(parents=True)
        path.write_bytes(b'wrong')
        with patch.object(manager.urllib.request, 'urlopen', side_effect=AssertionError('network')):
            with self.assertRaisesRegex(RuntimeError, 'Reinstall'):
                self.app.install_file(item)
        self.assertFalse((self.app.data / 'payload').exists())

    def test_offline_file_cannot_fall_back_to_previous_thin_download(self):
        (self.resources / 'payload-manifest.json').write_text(json.dumps({'offline': True}))
        item = self.item()
        path = self.app.data / 'payload' / item['path']
        path.parent.mkdir(parents=True)
        path.write_bytes(b'model')
        with patch.object(manager.urllib.request, 'urlopen', side_effect=AssertionError('network')):
            with self.assertRaisesRegex(RuntimeError, 'Reinstall'):
                self.app.install_file(item)

    def test_ollama_payload_requires_actual_blob_integrity(self):
        content = b'model'
        digest = hashlib.sha256(content).hexdigest()
        model = {'config': {'digest': 'sha256:' + digest, 'size': len(content)}, 'layers': []}
        raw = json.dumps(model).encode()
        root = self.resources / 'payload/ollama'
        (root / 'manifests/test').mkdir(parents=True)
        (root / 'blobs').mkdir()
        (root / 'manifests/test/model').write_bytes(raw)
        blob = root / 'blobs' / ('sha256-' + digest)
        blob.write_bytes(content)
        row = manager.CATALOG['gemma4']
        metadata = {'offline': True, 'ollama_models': [{'id': 'gemma4', 'path': 'test/model',
            'manifest_sha256': hashlib.sha256(raw).hexdigest(), 'ollama_model_digest': row['digest']}]}
        (self.resources / 'payload-manifest.json').write_text(json.dumps(metadata))
        self.app.verify_bundled_ollama(row)
        blob.write_bytes(b'wrong')
        with patch.object(self.app, 'ollama_models', side_effect=AssertionError('API digest is not sufficient')):
            with self.assertRaisesRegex(RuntimeError, 'damaged'):
                self.app.install_ollama(row)

    def test_checksum_failure_never_promotes_partial_file(self):
        with patch.object(manager.urllib.request, 'urlopen', return_value=io.BytesIO(b'wrong')):
            with self.assertRaises(ValueError):
                self.app.install_file(self.item())
        self.assertFalse((self.app.data / 'payload/kokoro/model.bin').exists())
        self.assertFalse((self.app.data / 'payload/kokoro/model.bin.partial').exists())

    def test_download_is_atomic_and_size_bounded(self):
        with patch.object(manager.urllib.request, 'urlopen', return_value=io.BytesIO(b'model')):
            self.app.install_file(self.item())
        self.assertEqual((self.app.data / 'payload/kokoro/model.bin').read_bytes(), b'model')
        item = self.item(b'different')
        with patch.object(manager.urllib.request, 'urlopen', return_value=io.BytesIO(b'too many bytes')):
            with self.assertRaises(ValueError):
                self.app.install_file(item)
        self.assertEqual((self.app.data / 'payload/kokoro/model.bin').read_bytes(), b'model')

    def test_arbitrary_url_is_rejected_before_network(self):
        item = self.item()
        item['url'] = 'http://169.254.169.254/latest/meta-data/'
        with patch.object(manager.urllib.request, 'urlopen', side_effect=AssertionError('network')):
            with self.assertRaises(ValueError):
                self.app.install_file(item)

    def test_only_verified_selections_can_start_services(self):
        self.app.selected = ['kokoro']
        self.app.job['state'] = 'ready'
        with self.assertRaises(RuntimeError):
            self.app.start_services()

    def test_existing_ollama_is_never_spawned_or_stopped(self):
        self.app.mode = 'existing'
        with patch.object(manager, 'request_json', return_value={'version': 'test'}), \
             patch.object(manager.subprocess, 'Popen', side_effect=AssertionError('spawn')):
            self.app.ensure_ollama()
            self.app.close()
        self.assertEqual(self.app.processes, {})

    def test_lite_catalog_defaults_and_selection_are_allowlisted(self):
        keys = ['qwen', 'asr26', 'kokoro']
        (self.resources / 'payload-manifest.json').write_text(json.dumps({
            'files': [], 'services': [], 'offline': True,
            'available_models': keys, 'default_models': keys}))
        with patch.object(self.app, 'ollama_models', return_value=[]):
            status = self.app.status()
        self.assertEqual([row['id'] for row in status['catalog']], keys)
        self.assertEqual(status['default_models'], keys)
        with self.assertRaises(ValueError):
            self.app.start_job({'models': ['kaedetai']})
        with patch.object(manager.threading, 'Thread') as worker:
            self.app.start_job({'models': keys})
        self.assertEqual(self.app.selected, keys)
        worker.return_value.start.assert_called_once()

    def test_close_serializes_with_inflight_spawn_and_rejects_future_children(self):
        entered, release = threading.Event(), threading.Event()
        process = Mock(pid=424242)
        process.poll.return_value = None
        def create_child(*_args, **_kwargs):
            entered.set()
            if not release.wait(timeout=2):
                raise AssertionError('test did not release spawn')
            return process
        probe = Mock()
        probe.connect_ex.return_value = 1
        probe.__enter__ = Mock(return_value=probe)
        probe.__exit__ = Mock(return_value=False)
        with patch.object(manager.socket, 'socket', return_value=probe), \
             patch.object(manager.subprocess, 'Popen', side_effect=create_child) as popen, \
             patch.object(manager.os, 'killpg') as killpg:
            spawn = threading.Thread(target=self.app.spawn, args=('test', ['test'], {}, 12345))
            spawn.start()
            self.assertTrue(entered.wait(timeout=2))
            closing = threading.Thread(target=self.app.close)
            closing.start()
            release.set()
            spawn.join(timeout=2)
            closing.join(timeout=2)
            self.assertFalse(spawn.is_alive() or closing.is_alive())
            self.assertTrue(self.app.closing)
            killpg.assert_called_once_with(process.pid, manager.signal.SIGTERM)
            with self.assertRaises(InterruptedError):
                self.app.spawn('late', ['test'], {}, 12346)
            self.assertEqual(popen.call_count, 1)

    def test_canceled_startup_cannot_launch_later_services(self):
        self.app.selected = ['kokoro']
        self.app.stop_event.set()
        (self.resources / 'payload-manifest.json').write_text(json.dumps({
            'services': [{'id': 'kokoro', 'requires': ['kokoro']}]}))
        with patch.object(self.app, 'spawn', side_effect=AssertionError('late child')):
            with self.assertRaises(InterruptedError):
                self.app._launch_services()

    def test_incomplete_source_package_is_not_marked_installed(self):
        with patch.object(self.app, 'ollama_models', return_value=[]):
            status = self.app.status()
        self.assertFalse(status['packaged'])
        self.assertTrue(all(not row['installed'] for row in status['catalog']))


if __name__ == '__main__':
    unittest.main()
