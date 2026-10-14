"""Test signing inventory and command policy without a signing identity."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile
import threading
import time
import unittest


SPEC = importlib.util.spec_from_file_location('sign_macos', Path(__file__).with_name('sign-macos.py'))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def macho(file_type=2):
    return b'\xcf\xfa\xed\xfe' + struct.pack('<III', 0x100000c, 0, file_type)


class SigningTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.app = self.root / 'Source.app'
        (self.app / 'Contents').mkdir(parents=True)
        (self.app / 'Contents/Info.plist').write_text('fixture')

    def tearDown(self):
        self.temporary.cleanup()

    def test_universal_detects_every_architecture(self):
        path = self.root / 'fat'
        header = b'\xca\xfe\xba\xbe' + struct.pack('>I', 2)
        entries = struct.pack('>IIIII', 0x1000007, 3, 48, 16, 0)
        entries += struct.pack('>IIIII', 0x100000c, 0, 64, 16, 0)
        path.write_bytes(header + entries + macho(2) + macho(6))
        self.assertEqual(MODULE.mach_types(path), {2, 6})

    def test_inventory_reads_resources_and_skips_symlinks(self):
        runtime = self.app / 'Contents/Resources/runtimes/python/bin/python3.12'
        runtime.parent.mkdir(parents=True)
        runtime.write_bytes(macho())
        runtime.with_name('python3').symlink_to(runtime.name)
        helper = self.app / 'Contents/Frameworks/Helper.app'
        framework = helper / 'Contents/Frameworks/Inner.framework'
        for bundle in (helper, framework):
            (bundle / 'Contents').mkdir(parents=True, exist_ok=True)
            (bundle / 'Contents/Info.plist').write_text('fixture')
        files, bundles = MODULE.inventory(self.app)
        self.assertEqual(files, [(runtime, {2})])
        self.assertEqual(bundles, [framework, helper])

    def test_commands_do_not_deep_sign_or_entitle_libraries(self):
        command = MODULE.signing_command(Path('/tmp/lib.so'), 'identity', False)
        self.assertNotIn('--deep', command)
        self.assertNotIn('--options', command)
        self.assertNotIn('--entitlements', command)
        self.assertIn('--timestamp', command)
        executable = MODULE.signing_command(Path('/tmp/python'), 'identity', True)
        self.assertIn('runtime', executable)

    def test_entitlements_are_restricted_to_jit_hosts(self):
        python = self.app / 'Contents/Resources/runtimes/asr/bin/python3.12'
        library = self.app / 'Contents/Resources/runtimes/asr/lib/test.so'
        self.assertTrue(MODULE.entitlements_for(python, self.app)['com.apple.security.cs.allow-jit'])
        self.assertNotIn('com.apple.security.device.audio-input', MODULE.entitlements_for(python, self.app))
        self.assertEqual(MODULE.entitlements_for(library, self.app), {})
        self.assertTrue(MODULE.entitlements_for(self.app, self.app)['com.apple.security.device.audio-input'])

    def test_source_or_nested_output_is_rejected(self):
        for output in (self.app, self.app / 'Nested.app'):
            with self.assertRaises(ValueError):
                MODULE.validate_paths(self.app, output)

    def test_only_developer_id_application_is_accepted(self):
        digest = 'A' * 40
        listing = f'1) {digest} "Developer ID Application: Test (TEAM)"'
        self.assertEqual(MODULE.developer_identity(digest, listing), digest)
        with self.assertRaises(ValueError):
            MODULE.developer_identity(digest, listing.replace('Developer ID Application:', 'Apple Development:'))

    def test_resume_requires_matching_prepared_copy(self):
        resources = self.app / 'Contents/Resources'
        resources.mkdir()
        source_info = {'version': '0.4.3', 'app_id': 'test', 'signing': 'ad-hoc', 'notarized': False}
        (resources / 'build-info.json').write_text(json.dumps(source_info))
        output = self.root / 'Copy.app'
        shutil.copytree(self.app, output)
        with self.assertRaises(ValueError):
            MODULE.validate_paths(self.app, output, resume=True)
        output_info = {**source_info, 'signing': 'developer-id', 'notarization': MODULE.NOTARIZATION_MARKER}
        destination = output / 'Contents/Resources/build-info.json'
        destination.write_text(json.dumps(output_info))
        self.assertEqual(MODULE.validate_paths(self.app, output, resume=True), (self.app.resolve(), output))
        output_info['version'] = '0.4.4'
        destination.write_text(json.dumps(output_info))
        with self.assertRaises(ValueError):
            MODULE.validate_paths(self.app, output, resume=True)
        with self.assertRaises(ValueError):
            MODULE.validate_paths(self.app, self.app, resume=True)

    def test_parallel_signing_is_bounded_and_hardlinks_are_serial(self):
        files = []
        for index in range(12):
            path = self.root / str(index)
            path.write_bytes(macho())
            files.append((path, {2}))
        alias = self.root / 'alias'
        os.link(files[0][0], alias)
        files.append((alias, {2}))
        active = set()
        peak = 0
        calls = []
        lock = threading.Lock()

        def sign(path, executable):
            nonlocal peak
            inode = path.stat().st_ino
            with lock:
                self.assertNotIn(inode, active)
                active.add(inode)
                peak = max(peak, len(active))
                calls.append(path)
            time.sleep(0.02)
            with lock:
                active.remove(inode)

        MODULE.sign_native_files(files, sign, 4)
        self.assertGreater(peak, 1)
        self.assertLessEqual(peak, 4)
        self.assertEqual(len(calls), len(files))
        self.assertFalse(active)

    def test_resume_removes_only_source_absent_codesign_scratch(self):
        original = self.app / 'Contents/test.so'
        original.write_bytes(macho(6))
        legitimate = self.app / 'Contents/kept.cstemp'
        legitimate.write_text('source resource')
        output = self.root / 'Copy.app'
        shutil.copytree(self.app, output)
        stale = output / 'Contents/test.so.cstemp'
        stale.write_bytes(b'interrupted output')
        removed = MODULE.remove_interrupted_signing_temps(self.app, output)
        self.assertEqual(removed, ['Contents/test.so.cstemp'])
        self.assertFalse(stale.exists())
        self.assertTrue((output / 'Contents/kept.cstemp').exists())
        self.assertTrue(original.exists())

    def test_resume_retains_unrecognized_or_symlink_scratch(self):
        output = self.root / 'Copy.app'
        shutil.copytree(self.app, output)
        stale = output / 'Contents/missing.so.cstemp'
        stale.write_text('unrecognized')
        with self.assertRaises(ValueError):
            MODULE.remove_interrupted_signing_temps(self.app, output)
        self.assertTrue(stale.exists())
        stale.unlink()
        source_target = self.app / 'Contents/test.so'
        source_target.write_bytes(macho(6))
        shutil.copy2(source_target, output / 'Contents/test.so')
        link = output / 'Contents/test.so.cstemp'
        link.symlink_to('test.so')
        with self.assertRaises(ValueError):
            MODULE.remove_interrupted_signing_temps(self.app, output)
        self.assertTrue(link.is_symlink())

    def test_parallel_failure_waits_for_running_jobs_and_propagates(self):
        files = []
        for index in range(20):
            path = self.root / str(index)
            path.write_bytes(macho())
            files.append((path, {2}))
        active = 0
        lock = threading.Lock()

        def sign(path, executable):
            nonlocal active
            if path.name == '0':
                raise RuntimeError('fixture signing failure')
            with lock:
                active += 1
            time.sleep(0.02)
            with lock:
                active -= 1

        with self.assertRaisesRegex(RuntimeError, 'fixture signing failure'):
            MODULE.sign_native_files(files, sign, 4)
        self.assertEqual(active, 0)


if __name__ == '__main__':
    unittest.main()
