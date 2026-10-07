"""Check packaging boundaries using tiny fixtures, without launching an app."""
import importlib.util
import hashlib
import json
from pathlib import Path
import plistlib
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('build_app', Path(__file__).with_name('build-app.py'))
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name in ('runtimes/python/bin/python3', 'runtimes/ollama/ollama', 'web/index.html', 'installer/manager.py',
                     'web/local-models/onnx-community/silero-vad/onnx/model.onnx',
                     'web/local-assets/onnx/ort-wasm-simd-threaded.wasm'):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'x')
        self.manifest = {
            'offline': True,
            'services': [{'id': 'asr26', 'executable': 'runtimes/python/bin/python3'}],
            'files': [{'model': 'asr26', 'path': 'asr26/model.bin', 'bytes': 1, 'sha256': 'a' * 64, 'url': 'https://huggingface.co/example'}],
        }
        self.write_manifest()

    def tearDown(self):
        self.temp.cleanup()

    def write_manifest(self):
        (self.root / 'payload-manifest.json').write_text(json.dumps(self.manifest))

    def test_thin_sets_download_mode_without_requiring_model_bytes(self):
        result = builder.validate_resources(self.root, 'thin')
        self.assertFalse(result['offline'])

    def test_full_rejects_missing_payload(self):
        with self.assertRaisesRegex(ValueError, 'Offline payload'):
            builder.validate_resources(self.root, 'full')

    def test_manifest_cannot_escape_resources(self):
        self.manifest['services'][0]['executable'] = '../python'
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, 'inside Resources'):
            builder.validate_resources(self.root, 'thin')

    def test_external_runtime_symlink_is_not_portable(self):
        link = self.root / 'runtimes/bad-python'
        link.symlink_to('/usr/bin/python3')
        with self.assertRaisesRegex(ValueError, 'Non-portable symlink'):
            builder.validate_resources(self.root, 'thin')

    def test_thin_requires_download_source(self):
        self.manifest['files'][0]['url'] = 'http://example.com/model.bin'
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, 'HTTPS'):
            builder.validate_resources(self.root, 'thin')

    def test_rebrand_renames_main_binary_so_electron_detects_a_packaged_app(self):
        app = self.root / 'Example.app'
        binary = app / 'Contents/MacOS/Electron'
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b'example executable')
        binary.chmod(0o755)
        info = app / 'Contents/Info.plist'
        info.write_bytes(plistlib.dumps({'CFBundleExecutable': 'Electron',
                                        'CFBundleIdentifier': 'com.github.Electron'}))
        builder.rebrand(app)
        values = plistlib.loads(info.read_bytes())
        self.assertEqual(values['CFBundleExecutable'], 'AIRI Local')
        self.assertEqual(values['CFBundleIdentifier'], builder.APP_ID)
        self.assertFalse(binary.exists())
        self.assertEqual(binary.with_name('AIRI Local').read_bytes(), b'example executable')
        self.assertEqual(binary.with_name('AIRI Local').stat().st_mode & 0o777, 0o755)
        builder.rebrand(app)  # A final refresh must not break an already branded app.

    def test_lite_manifest_removes_large_models_and_taigi_service(self):
        source = {
            'files': [{'model': key} for key in ('asr26', 'kokoro', 'kaedetai')],
            'ollama_models': [{'id': key} for key in ('qwen', 'sarc-taigi', 'gemma4')],
            'services': [{'id': key, 'requires': [key]} for key in ('asr26', 'kokoro', 'kaedetai')]
                        + [{'id': 'hub', 'requires': []}],
        }
        lite = builder.select_manifest(source, 'lite')
        self.assertEqual(lite['available_models'], ['qwen', 'asr26', 'kokoro'])
        self.assertEqual(lite['default_models'], lite['available_models'])
        self.assertEqual([item['id'] for item in lite['ollama_models']], ['qwen'])
        self.assertEqual([item['id'] for item in lite['services']], ['asr26', 'kokoro', 'hub'])
        self.assertTrue(lite['offline'])
        self.assertEqual(len(source['ollama_models']), 3)  # Original full manifest stays intact.
        full = builder.select_manifest(source, 'full')
        self.assertEqual(len(full['available_models']), 6)
        self.assertNotIn('qwen', full['default_models'])
        thin = builder.select_manifest(source, 'thin')
        self.assertFalse(thin['offline'])
        self.assertEqual(thin['default_models'], ['qwen', 'asr26', 'kokoro'])

    def test_lite_copies_only_blobs_referenced_by_qwen(self):
        source = self.root / 'model-source'
        blobs = source / 'ollama/blobs'
        blobs.mkdir(parents=True)
        content = b'Qwen fixture'
        digest = hashlib.sha256(content).hexdigest()
        (blobs / ('sha256-' + digest)).write_bytes(content)
        (blobs / ('sha256-' + 'b' * 64)).write_bytes(b'unrelated huge-model fixture')
        record = {'config': {'digest': 'sha256:' + digest, 'size': len(content)}, 'layers': []}
        raw = json.dumps(record).encode()
        relative = 'registry.ollama.ai/library/qwen3.5/0.8b'
        model = source / 'ollama/manifests' / relative
        model.parent.mkdir(parents=True)
        model.write_bytes(raw)
        manifest = {'files': [], 'ollama_models': [{'id': 'qwen', 'path': relative,
                    'manifest_sha256': hashlib.sha256(raw).hexdigest()}]}
        target = self.root / 'lite-payload'
        builder.copy_lite_payload(source, target, manifest)
        self.assertEqual([item.name for item in (target / 'ollama/blobs').iterdir()], ['sha256-' + digest])
        self.assertEqual((target / 'ollama/manifests' / relative).read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
