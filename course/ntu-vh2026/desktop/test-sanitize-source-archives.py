"""Verify source-preserving archive filtering without changing an application."""
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('sanitize_sources', Path(__file__).with_name('sanitize-source-archives.py'))
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
NATIVE = b'\xcf\xfa\xed\xfe' + bytes(60)
NATIVE_NAME = 'example/MEX/test.mexmaci64'


def make_archive(path, extra_native=False, format=tarfile.PAX_FORMAT):
    with path.open('wb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode='w', format=format, pax_headers={'comment': 'upstream revision'}) as tar:
            entries = [(NATIVE_NAME, NATIVE), ('example/MEX/test.c', b'int main() { return 0; }\n'),
                       ('example/LICENSE', b'Original author license\n')]
            if extra_native:
                entries.append(('example/unexpected.so', NATIVE))
            for name, data in entries:
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = 0o640
                info.uid = 42
                info.gid = 43
                info.uname = 'author'
                info.gname = 'group'
                info.mtime = 123456789
                tar.addfile(info, io.BytesIO(data))
            link = tarfile.TarInfo('example/license-link')
            link.type = tarfile.SYMTYPE
            link.linkname = 'LICENSE'
            tar.addfile(link)


class SanitizerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / 'source.tar.gz'
        make_archive(self.source)
        self.original = self.source.read_bytes()
        self.digest = hashlib.sha256(self.original).hexdigest()
        self.exclusions = {NATIVE_NAME: hashlib.sha256(NATIVE).hexdigest()}

    def tearDown(self):
        self.temporary.cleanup()

    def repack(self, destination):
        return M.repack_archive(self.source, destination, self.digest, self.exclusions)

    def test_contents_metadata_order_and_original_are_preserved(self):
        destination = self.root / 'filtered.tar.gz'
        report = self.repack(destination)
        expected = [row for row in M.archive_members(self.source) if row['name'] != NATIVE_NAME]
        self.assertEqual(M.archive_members(destination), expected)
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(report['retained_members'], 3)
        self.assertEqual(report['excluded_members'][0]['path'], NATIVE_NAME)

    def test_output_is_reproducible_and_gzip_time_is_zero(self):
        first, second = self.root / 'a.gz', self.root / 'b.gz'
        self.repack(first)
        self.repack(second)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(first.read_bytes()[4:8], bytes(4))
        self.assertEqual(first.read_bytes()[3] & 8, 0)

    def test_unpinned_archive_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'pinned SHA256'):
            M.repack_archive(self.source, self.root / 'bad.gz', '0' * 64, self.exclusions)

    def test_gnu_header_checksum_is_not_source_metadata(self):
        make_archive(self.source, format=tarfile.GNU_FORMAT)
        digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        report = M.repack_archive(self.source, self.root / 'converted.gz', digest, self.exclusions)
        self.assertEqual(report['retained_members'], 3)

    def test_source_or_unknown_native_member_is_never_silently_removed(self):
        with self.assertRaisesRegex(ValueError, 'compiled Mach-O'):
            M.repack_archive(self.source, self.root / 'bad.gz', self.digest,
                             {'example/MEX/test.c': hashlib.sha256(b'int main() { return 0; }\n').hexdigest()})
        make_archive(self.source, extra_native=True)
        digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, 'unexpected Mach-O'):
            M.repack_archive(self.source, self.root / 'bad2.gz', digest, self.exclusions)

    def test_preparation_is_idempotent_and_manifest_hashes_are_truthful(self):
        resources = self.root / 'Resources'
        licenses = resources / 'licenses'
        sources = licenses / 'source'
        sources.mkdir(parents=True)
        archive = sources / M.ARCHIVE_NAME
        archive.write_bytes(self.original)
        record = {'file': 'source/' + M.ARCHIVE_NAME, 'source': M.UPSTREAM_URL,
                  'sha256': self.digest, 'bytes': len(self.original)}
        manifest = licenses / 'upstream-source-manifest.json'
        manifest.write_text(json.dumps([record]))
        (licenses / 'THIRD-PARTY-NOTICES.md').write_text('Original notices\n')
        first = M.sanitize_resources(resources, self.digest, self.exclusions)
        before = {path.relative_to(licenses): path.read_bytes() for path in licenses.rglob('*') if path.is_file()}
        second = M.sanitize_resources(resources, self.digest, self.exclusions)
        after = {path.relative_to(licenses): path.read_bytes() for path in licenses.rglob('*') if path.is_file()}
        self.assertTrue(first['changed'])
        self.assertFalse(second['changed'])
        self.assertEqual(before, after)
        result = json.loads(manifest.read_text())[0]
        self.assertEqual(result['sha256'], hashlib.sha256(archive.read_bytes()).hexdigest())
        self.assertEqual(result['upstream_sha256'], self.digest)
        self.assertIn(result['sha256'], (sources / 'README.md').read_text())
        self.assertTrue((licenses / 'THIRD-PARTY-NOTICES.md').read_text().startswith('Original notices'))


if __name__ == '__main__':
    unittest.main()
