"""Installer trust boundaries without downloading weights or starting engines."""
import hashlib
import importlib.util
import io
import json
import os
import shutil
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

    def ollama_fixture(self, offline=True):
        content = b'model'
        digest = hashlib.sha256(content).hexdigest()
        model = {'config': {'digest': 'sha256:' + digest, 'size': len(content)}, 'layers': []}
        raw = json.dumps(model).encode()
        root = self.resources / 'payload/ollama' if offline else self.app.data / 'ollama'
        (root / 'manifests/test').mkdir(parents=True)
        (root / 'blobs').mkdir()
        (root / 'manifests/test/model').write_bytes(raw)
        blob = root / 'blobs' / ('sha256-' + digest)
        blob.write_bytes(content)
        row = manager.CATALOG['gemma4']
        record = {'id': row['id'], 'path': 'test/model',
                  'manifest_sha256': hashlib.sha256(raw).hexdigest(), 'ollama_model_digest': row['digest']}
        (self.resources / 'payload-manifest.json').write_text(json.dumps({
            'offline': offline, 'files': [], 'ollama_models': [record]}))
        return row, record, blob

    def http_get(self, path):
        class Connection:
            response = bytearray()

            def makefile(self, *_args):
                return io.BytesIO(f'GET {path} HTTP/1.0\r\nHost: 127.0.0.1:{manager.PORT}\r\n\r\n'.encode())

            def sendall(self, data):
                self.response.extend(data)

        connection = Connection()
        manager.make_handler(self.app)(connection, ('127.0.0.1', 12345), Mock())
        headers, body = bytes(connection.response).split(b'\r\n\r\n', 1)
        return headers, body

    def test_static_json_keeps_original_utf8_bytes_and_content_length(self):
        root = self.resources / 'web/assets'
        root.mkdir(parents=True)
        content = '{\n  "name": "本機角色", "count": 3\n}\n'.encode()
        (root / 'model-config.json').write_bytes(content)
        headers, body = self.http_get('/assets/model-config.json')
        self.assertTrue(headers.startswith(b'HTTP/1.0 200'))
        self.assertIn(b'Content-Type: application/json', headers)
        self.assertIn(f'Content-Length: {len(content)}'.encode(), headers)
        self.assertEqual(body, content)

    def test_api_objects_still_serialize_as_json(self):
        headers, body = self.http_get('/api/bootstrap')
        self.assertTrue(headers.startswith(b'HTTP/1.0 200'))
        self.assertIn(b'Content-Type: application/json', headers)
        self.assertEqual(json.loads(body), {'token': self.app.token, 'origin': manager.ORIGIN})

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

    def motion_fixture(self):
        item = {**self.item(), 'model': 'motiongpt', 'path': 'motiongpt/weights.tar'}
        (self.resources / 'payload-manifest.json').write_text(json.dumps({
            'offline': True, 'download_only_models': ['motiongpt'], 'files': [item], 'services': []}))
        return item

    def test_optional_motion_download_never_writes_signed_resources(self):
        item = self.motion_fixture()
        with patch.object(manager.urllib.request, 'urlopen', return_value=io.BytesIO(b'model')) as download:
            self.app.install_file(item)
        download.assert_called_once()
        self.assertEqual(self.app.payload_path(item['path']).read_bytes(), b'model')
        self.assertTrue(self.app.payload_path(item['path']).is_relative_to(self.app.data))
        self.assertFalse((self.resources / 'payload').exists())

    def test_download_only_policy_does_not_weaken_offline_speech_integrity(self):
        self.motion_fixture()
        with patch.object(manager.urllib.request, 'urlopen', side_effect=AssertionError('offline speech must not fetch')):
            with self.assertRaisesRegex(RuntimeError, 'Reinstall'):
                self.app.install_file(self.item())

    def test_existing_optional_weights_are_verified_without_downloading(self):
        item = self.motion_fixture()
        target = self.app.payload_path(item['path'])
        target.parent.mkdir(parents=True)
        target.write_bytes(b'model')
        with patch.object(manager.urllib.request, 'urlopen', side_effect=AssertionError('already verified')):
            self.app.install_file(item)

    def test_motion_service_uses_user_payload_and_remains_unstarted_when_unselected(self):
        item = self.motion_fixture()
        executable = self.resources / 'runtime/python'
        executable.parent.mkdir()
        executable.write_bytes(b'fixture')
        service = {'id': 'motiongpt', 'requires': ['motiongpt'], 'executable': 'runtime/python',
                   'args': [], 'env': {'MODEL_DIR': '{payload}/motiongpt'}, 'port': 17905, 'health': '/health'}
        (self.resources / 'payload-manifest.json').write_text(json.dumps({
            'offline': True, 'download_only_models': ['motiongpt'], 'files': [item], 'services': [service]}))
        with patch.object(self.app, 'spawn') as spawn:
            self.app._launch_services()
            spawn.assert_not_called()
        self.app.selected = ['motiongpt']
        self.app.processes['motiongpt'] = Mock(poll=lambda: None)
        with patch.object(self.app, 'spawn') as spawn, patch.object(manager, 'request_json', return_value={'ready': True}):
            self.app._launch_services()
            self.assertEqual(spawn.call_args.args[2]['MODEL_DIR'], str(self.app.data / 'payload/motiongpt'))

    def test_bootstrap_exposes_motion_only_for_selected_optional_model(self):
        _, body = self.http_get('/api/airi-config')
        self.assertIsNone(json.loads(body)['motion'])
        self.app.selected = ['motiongpt']
        _, body = self.http_get('/api/airi-config')
        self.assertEqual(json.loads(body)['motion'], 'http://127.0.0.1:17905')

    def test_ollama_payload_requires_actual_blob_integrity(self):
        row, _record, blob = self.ollama_fixture()
        self.app.verify_bundled_ollama(row)
        blob.write_bytes(b'wrong')
        with patch.object(self.app, 'ollama_models', side_effect=AssertionError('API digest is not sufficient')):
            with self.assertRaisesRegex(RuntimeError, 'damaged'):
                self.app.install_ollama(row)

    def test_bundled_runtime_uses_manifest_digest_without_claiming_verification(self):
        row, record, _blob = self.ollama_fixture()
        tags = [{'name': row['model'], 'digest': record['manifest_sha256']}]
        self.assertNotEqual(record['manifest_sha256'], row['digest'])
        with patch.object(self.app, 'ollama_models', return_value=tags), \
             patch.object(manager.urllib.request, 'urlopen', side_effect=AssertionError('network')):
            status = next(item for item in self.app.status()['catalog'] if item['id'] == row['id'])
            self.assertTrue(status['installed'])
            self.assertFalse(status['verified'])
            self.app.selected = [row['id']]
            self.app.prepare_ollama_store()
            with patch.object(self.app, 'ensure_ollama'):
                self.app.install()
        self.assertEqual(self.app.job['state'], 'ready')
        self.assertEqual(self.app.verified, {row['id']})

    def test_ollama_metadata_writes_leave_signed_resources_unchanged(self):
        row, _record, source_blob = self.ollama_fixture()
        self.app.selected = [row['id']]
        executable = self.resources / 'runtimes/ollama/ollama'
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b'fixture')
        before = {str(path.relative_to(self.resources)): manager.hash_file(path)
                  for path in self.resources.rglob('*') if path.is_file()}

        def fake_ollama(_name, _args, env, port):
            self.assertEqual(port, 12434)
            store = Path(env['OLLAMA_MODELS'])
            self.assertEqual(store, self.app.data / 'ollama')
            cache = store / 'metadata/model.json'
            cache.parent.mkdir()
            cache.write_text('{"ollama_version":"fixture"}')
            self.app.processes['ollama'] = Mock(poll=lambda: None)

        with patch.object(self.app, 'spawn', side_effect=fake_ollama), \
             patch.object(manager, 'request_json', return_value={'version': 'fixture'}):
            self.app.ensure_ollama()
        after = {str(path.relative_to(self.resources)): manager.hash_file(path)
                 for path in self.resources.rglob('*') if path.is_file()}
        self.assertEqual(before, after)
        target_blob = self.app.data / 'ollama/blobs' / source_blob.name
        self.assertNotEqual(source_blob.stat().st_ino, target_blob.stat().st_ino)
        self.assertEqual(target_blob.stat().st_nlink, 1)
        self.assertFalse(target_blob.is_symlink())

    def test_verified_store_is_reused_by_another_release_without_copying(self):
        row, _record, source_blob = self.ollama_fixture()
        self.app.selected = [row['id']]
        self.app.prepare_ollama_store()
        target = self.app.data / 'ollama/blobs' / source_blob.name
        first_inode = target.stat().st_ino
        custom = self.app.data / 'ollama/custom-user-file'
        custom.write_text('preserve')
        next_resources = self.resources.with_name('next-release')
        shutil.copytree(self.resources, next_resources)
        next_app = manager.LocalManager(self.app.data, next_resources)
        next_app.selected = [row['id']]
        with patch.object(manager.shutil, 'copyfile', side_effect=AssertionError('do not recopy valid models')), \
             patch.object(manager.ctypes, 'CDLL', side_effect=AssertionError('do not reclone valid models')):
            next_app.prepare_ollama_store()
        self.assertEqual(target.stat().st_ino, first_inode)
        self.assertEqual(custom.read_text(), 'preserve')

    def test_corrupt_private_copy_is_repaired_without_mutating_bundle(self):
        row, _record, source_blob = self.ollama_fixture()
        self.app.selected = [row['id']]
        self.app.prepare_ollama_store()
        target = self.app.data / 'ollama/blobs' / source_blob.name
        target.write_bytes(b'wrong')
        self.app.prepare_ollama_store()
        self.assertEqual(target.read_bytes(), b'model')
        self.assertEqual(source_blob.read_bytes(), b'model')

    def test_prior_hardlinked_copy_is_replaced_with_independent_file(self):
        row, _record, source_blob = self.ollama_fixture()
        self.app.selected = [row['id']]
        target = self.app.data / 'ollama/blobs' / source_blob.name
        target.parent.mkdir(parents=True)
        os.link(source_blob, target)
        self.app.prepare_ollama_store()
        self.assertNotEqual(source_blob.stat().st_ino, target.stat().st_ino)
        target.write_bytes(b'wrong')
        self.assertEqual(source_blob.read_bytes(), b'model')

    def test_unselected_sarc_is_not_seeded(self):
        row, _record, _blob = self.ollama_fixture()
        self.app.selected = [row['id']]
        manifest_path = self.resources / 'payload-manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['ollama_models'].append({'id': 'sarc-taigi', 'path': 'unselected/sarc',
            'manifest_sha256': '0' * 64, 'ollama_model_digest': manager.CATALOG['sarc-taigi']['digest']})
        manifest_path.write_text(json.dumps(manifest))
        with patch.object(self.app, 'verify_bundled_ollama', wraps=self.app.verify_bundled_ollama) as verify:
            self.app.prepare_ollama_store()
        verify.assert_called_once_with(row)
        self.assertFalse((self.app.data / 'ollama/manifests/unselected').exists())

    def test_offline_runtime_checks_private_copy_even_with_valid_api_digest(self):
        row, record, source_blob = self.ollama_fixture()
        self.app.selected = [row['id']]
        self.app.prepare_ollama_store()
        (self.app.data / 'ollama/blobs' / source_blob.name).write_bytes(b'wrong')
        with patch.object(self.app, 'ollama_models', return_value=[{'name': row['model'], 'digest': record['manifest_sha256']}]), \
             patch.object(manager.urllib.request, 'urlopen', side_effect=AssertionError('network')):
            with self.assertRaisesRegex(RuntimeError, 'damaged'):
                self.app.install_ollama(row)

    def test_private_model_store_cannot_link_back_into_signed_app(self):
        row, _record, _blob = self.ollama_fixture()
        self.app.selected = [row['id']]
        (self.app.data / 'ollama').symlink_to(self.resources / 'payload/ollama', target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'escapes'):
            self.app.prepare_ollama_store()

    def test_copy_fallback_reserves_space_and_removes_temporary_file(self):
        row, _record, _blob = self.ollama_fixture()
        self.app.selected = [row['id']]
        with patch.object(manager.sys, 'platform', 'fixture-no-clone'), \
             patch.object(manager.shutil, 'disk_usage', return_value=Mock(free=manager.OLLAMA_COPY_RESERVE + 1)), \
             patch.object(manager.shutil, 'copyfile', side_effect=AssertionError('insufficient space')):
            with self.assertRaisesRegex(RuntimeError, 'Not enough space'):
                self.app.prepare_ollama_store()
        self.assertEqual(list((self.app.data / 'ollama').rglob('.airi-model-*')), [])

    def test_seed_copies_only_pinned_files_and_verifies_copy_fallback(self):
        row, _record, blob = self.ollama_fixture()
        self.app.selected = [row['id']]
        metadata = self.resources / 'payload/ollama/metadata'
        metadata.mkdir()
        (metadata / 'private-cache.json').write_text('{}')
        with patch.object(manager.sys, 'platform', 'fixture-no-clone'), \
             patch.object(manager.shutil, 'disk_usage', return_value=Mock(free=30 * 1024 ** 3)):
            self.app.prepare_ollama_store()
        self.assertFalse((self.app.data / 'ollama/metadata').exists())
        self.assertEqual((self.app.data / 'ollama/blobs' / blob.name).read_bytes(), b'model')

    def test_failed_copy_checksum_keeps_previous_private_file(self):
        row, _record, blob = self.ollama_fixture()
        self.app.selected = [row['id']]
        target = self.app.data / 'ollama/blobs' / blob.name
        target.parent.mkdir(parents=True)
        target.write_bytes(b'old')
        with patch.object(manager.sys, 'platform', 'fixture-no-clone'), \
             patch.object(manager.shutil, 'disk_usage', return_value=Mock(free=30 * 1024 ** 3)), \
             patch.object(manager.shutil, 'copyfile', side_effect=lambda _source, dest: dest.write_bytes(b'bad')):
            with self.assertRaisesRegex(RuntimeError, 'checksum'):
                self.app.prepare_ollama_store()
        self.assertEqual(target.read_bytes(), b'old')
        self.assertEqual(list(target.parent.glob('.airi-model-*')), [])

    def test_bundled_runtime_rejects_external_api_digest_and_unknown_digest(self):
        row, _record, _blob = self.ollama_fixture()
        for digest in (row['digest'], '0' * 64):
            with self.subTest(digest=digest), \
                 patch.object(self.app, 'ollama_models', return_value=[{'name': row['model'], 'digest': digest}]), \
                 patch.object(manager.urllib.request, 'urlopen', side_effect=AssertionError('network')):
                with self.assertRaisesRegex(RuntimeError, 'does not match'):
                    self.app.install_ollama(row)

    def test_existing_runtime_accepts_both_pinned_representations_but_no_unknown_digest(self):
        row, record, _blob = self.ollama_fixture()
        self.app.mode = 'existing'
        with patch.object(manager.urllib.request, 'urlopen', side_effect=AssertionError('network')):
            for digest, valid in ((row['digest'], True), (record['manifest_sha256'], True), ('0' * 64, False)):
                with self.subTest(digest=digest), \
                     patch.object(self.app, 'ollama_models', return_value=[{'name': row['model'], 'digest': digest}]):
                    status = next(item for item in self.app.status()['catalog'] if item['id'] == row['id'])
                    self.assertEqual(status['installed'], valid)
                    if valid:
                        self.app.install_ollama(row)
                    else:
                        with self.assertRaisesRegex(RuntimeError, 'does not match'):
                            self.app.install_ollama(row)

    def test_thin_existing_runtime_accepts_both_pins_without_accessing_private_store(self):
        row, record, _blob = self.ollama_fixture(offline=False)
        self.app.mode = 'existing'
        with patch.object(self.app, 'verify_ollama_store', side_effect=AssertionError('do not inspect external model store')), \
             patch.object(manager.urllib.request, 'urlopen', side_effect=AssertionError('already installed')):
            for digest in (row['digest'], record['manifest_sha256']):
                with self.subTest(digest=digest), \
                     patch.object(self.app, 'ollama_models', return_value=[{'name': row['model'], 'digest': digest}]):
                    self.app.install_ollama(row)

    def test_external_alternate_digest_requires_trusted_release_metadata(self):
        row, record, _blob = self.ollama_fixture(offline=False)
        self.app.mode = 'existing'
        record['ollama_model_digest'] = '0' * 64
        (self.resources / 'payload-manifest.json').write_text(json.dumps({'offline': False, 'ollama_models': [record]}))
        with patch.object(self.app, 'ollama_models', side_effect=AssertionError('metadata must be checked before API')):
            with self.assertRaisesRegex(RuntimeError, 'metadata is missing'):
                self.app.install_ollama(row)

    def test_corrupted_manifest_never_reaches_api_digest_check(self):
        row, _record, _blob = self.ollama_fixture()
        (self.resources / 'payload/ollama/manifests/test/model').write_text('{}')
        with patch.object(self.app, 'ollama_models', side_effect=AssertionError('API digest is not sufficient')):
            with self.assertRaisesRegex(RuntimeError, 'manifest is damaged'):
                self.app.install_ollama(row)

    def test_manifest_metadata_must_still_match_catalog_identity(self):
        row, record, _blob = self.ollama_fixture()
        record['ollama_model_digest'] = '0' * 64
        (self.resources / 'payload-manifest.json').write_text(json.dumps({'offline': True, 'ollama_models': [record]}))
        with patch.object(self.app, 'ollama_models', side_effect=AssertionError('metadata must be checked first')):
            with self.assertRaisesRegex(RuntimeError, 'metadata is missing'):
                self.app.install_ollama(row)

    def test_thin_bundled_runtime_checks_downloaded_store_before_reusing(self):
        row, record, blob = self.ollama_fixture(offline=False)
        tags = [{'name': row['model'], 'digest': record['manifest_sha256']}]
        with patch.object(self.app, 'ollama_models', return_value=tags), \
             patch.object(manager.urllib.request, 'urlopen', side_effect=AssertionError('network')):
            self.app.install_ollama(row)
            blob.write_bytes(b'wrong')
            with self.assertRaisesRegex(RuntimeError, 'damaged'):
                self.app.install_ollama(row)

    def test_thin_bundled_download_uses_private_port_and_verifies_files(self):
        row, record, blob = self.ollama_fixture(offline=False)
        tags = [{'name': row['model'], 'digest': record['manifest_sha256']}]
        with patch.object(self.app, 'ollama_models', side_effect=[[], tags]), \
             patch.object(manager.shutil, 'disk_usage', return_value=Mock(free=30 * 1024 ** 3)), \
             patch.object(manager.urllib.request, 'urlopen', return_value=io.BytesIO(b'{"status":"success"}\n')) as fetch:
            self.app.install_ollama(row)
        self.assertEqual(fetch.call_args.args[0].full_url, manager.OLLAMA_URLS['bundled'] + '/api/pull')
        blob.write_bytes(b'wrong')
        with patch.object(self.app, 'ollama_models', side_effect=[[], tags]), \
             patch.object(manager.shutil, 'disk_usage', return_value=Mock(free=30 * 1024 ** 3)), \
             patch.object(manager.urllib.request, 'urlopen', return_value=io.BytesIO(b'{"status":"success"}\n')):
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
             patch.object(self.app, 'prepare_ollama_store', side_effect=AssertionError('do not modify external mode')), \
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
