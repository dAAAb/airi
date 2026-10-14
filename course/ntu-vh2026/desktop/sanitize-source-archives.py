"""Preserve bundled VMAF source while omitting unused precompiled Mac examples.

Only the pinned upstream archive is changed. Runtime code, source members,
license members, and unrelated compressed test fixtures are never removed.
Run before signing, or re-sign the outer app after applying this to a copy.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import tarfile
import tempfile

ARCHIVE_NAME = 'vmaf-3.2.1.tar.gz'
ORIGINAL_SHA256 = '5df7386911bc15fd1ca783132528748d219768ae4fc5f8e0b61184f041648092'
UPSTREAM_URL = 'https://github.com/Netflix/vmaf/archive/refs/tags/v3.2.1.tar.gz'
MACH_MAGICS = {b'\xce\xfa\xed\xfe', b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xce',
               b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca',
               b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca'}
EXCLUDED = {
    'vmaf-3.2.1/matlab/STMAD_2011_MatlabCode/ical_stat.mexmaci64': '8e089525485f680631bfeaf907474e7722a71fe489137a655babd67e25008d2a',
    'vmaf-3.2.1/matlab/STMAD_2011_MatlabCode/ical_std.mexmaci64': '8701babf30adc067d41fdde60daced5d3ed52ce2dd2dca2f84a16092453edd3f',
    'vmaf-3.2.1/matlab/strred/matlabPyrTools/MEX/Copy_of_corrDn.mexmac': '5850c80b492749cd8a44b09efd0544218517be7c3b65cd1f16e16261862e91de',
    'vmaf-3.2.1/matlab/strred/matlabPyrTools/MEX/corrDn.mexmac': '5850c80b492749cd8a44b09efd0544218517be7c3b65cd1f16e16261862e91de',
    'vmaf-3.2.1/matlab/strred/matlabPyrTools/MEX/histo.mexmac': 'd138458736dd4ee5ede0b35378a635c31198314d53b968c684a24dfb5d170f14',
    'vmaf-3.2.1/matlab/strred/matlabPyrTools/MEX/innerProd.mexmac': 'bc8dfb5a2758bec098a80c82b9adf5cfe0602a3d003a87f0143bb104de138602',
    'vmaf-3.2.1/matlab/strred/matlabPyrTools/MEX/pointOp.mexmac': 'b8d9c5a171279f68c8e8374042e1653e00c8ad97b39d9a19d077016102f26598',
    'vmaf-3.2.1/matlab/strred/matlabPyrTools/MEX/pointOp.o': 'a9b0cc83643d50c05cef5d85cf7d939fc7ab3b15341f0641a6069a17ea855faa',
    'vmaf-3.2.1/matlab/strred/matlabPyrTools/MEX/range2.mexmac': '490c537cd764edcccd0cdbc654c86eb1d6b3157d3199fde37189679627c69371',
    'vmaf-3.2.1/matlab/strred/matlabPyrTools/MEX/range2.o': '415275f68cda7b83c81b0da6a4ee5ad1556700e0ac2f30e637e2e29896b6851e',
    'vmaf-3.2.1/matlab/strred/matlabPyrTools/MEX/upConv.mexmac': '099d65008e18d6ff593a4fbf2c338ddd71ec42a7da81e17a3db97083f9a9b23e',
    'vmaf-3.2.1/matlab/strred/matlabPyrTools/MEX/upConv.o': 'a53b3c22321212bd91e18553b5e9a42143990cee4bfa8e7569d31a2bcddb86f4',
}
REASON = ('Unused precompiled MATLAB examples. AIRI uses the VMAF runtime library, '
          'not these example binaries. All source and license members are retained.')
NOTICE_MARKER = '## VMAF source archive preparation for macOS'
README_MARKER = '# Bundled upstream source archives'


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def archive_members(path):
    records = []
    seen = set()
    with tarfile.open(path, 'r:gz') as archive:
        for member in archive:
            if member.name in seen:
                raise ValueError('Duplicate archive members are not supported')
            seen.add(member.name)
            info = member.get_info()
            # Header checksums describe tar serialization, not retained file data.
            info.pop('chksum', None)
            info['type'] = member.type.decode('latin1')
            info['pax_headers'] = member.pax_headers
            info['devmajor'] = member.devmajor
            info['devminor'] = member.devminor
            if member.isfile():
                with archive.extractfile(member) as stream:
                    data = stream.read()
                info['content_sha256'] = digest_bytes(data)
                info['mach_o'] = data[:4] in MACH_MAGICS
            records.append(info)
    return records


def members_digest(records):
    return digest_bytes(json.dumps(records, sort_keys=True, separators=(',', ':')).encode())


def repack_archive(source, destination, expected_sha=ORIGINAL_SHA256, exclusions=EXCLUDED):
    original_bytes = source.read_bytes()
    if digest_bytes(original_bytes) != expected_sha:
        raise ValueError('The upstream VMAF archive differs from its pinned SHA256')
    original = archive_members(source)
    removed = [row for row in original if row['name'] in exclusions]
    if {row['name'] for row in removed} != set(exclusions):
        raise ValueError('The pinned precompiled example set is incomplete')
    if any(not row.get('mach_o') or row.get('content_sha256') != exclusions[row['name']] for row in removed):
        raise ValueError('A pinned example is not the expected compiled Mach-O file')
    retained = [row for row in original if row['name'] not in exclusions]
    if any(row.get('mach_o') for row in retained):
        raise ValueError('An unexpected Mach-O member needs review before repacking')
    with source.open('rb') as original_stream, tarfile.open(fileobj=original_stream, mode='r:gz') as archive:
        with destination.open('xb') as destination_stream:
            with gzip.GzipFile(filename='', mode='wb', fileobj=destination_stream, mtime=0, compresslevel=9) as compressed:
                with tarfile.open(fileobj=compressed, mode='w', format=tarfile.PAX_FORMAT,
                                  pax_headers=archive.pax_headers) as output:
                    for member in archive:
                        if member.name in exclusions:
                            continue
                        stream = archive.extractfile(member) if member.isfile() else None
                        try:
                            output.addfile(member, stream)
                        finally:
                            if stream:
                                stream.close()
    actual = archive_members(destination)
    if actual != retained:
        raise ValueError('Repacking changed retained source contents or tar metadata')
    return {'archive': f'source/{ARCHIVE_NAME}', 'upstream_url': UPSTREAM_URL,
            'original_sha256': expected_sha, 'original_bytes': len(original_bytes),
            'repacked_sha256': digest_bytes(destination.read_bytes()), 'repacked_bytes': destination.stat().st_size,
            'gzip_mtime': 0, 'gzip_filename': '', 'reason': REASON,
            'excluded_members': [{'path': row['name'], 'bytes': row['size'], 'sha256': row['content_sha256'],
                                  'reason': REASON} for row in removed],
            'retained_members': len(retained), 'retained_members_sha256': members_digest(retained),
            'preservation': 'Every retained member has identical content, metadata, and ordering.'}


def sanitize_resources(resources, expected_sha=ORIGINAL_SHA256, exclusions=EXCLUDED):
    licenses = resources / 'licenses'
    archive_path = licenses / 'source' / ARCHIVE_NAME
    if not archive_path.exists():
        return {'changed': False, 'reason': 'The pinned VMAF source archive is not present'}
    manifest_path = licenses / 'upstream-source-manifest.json'
    notice_path = licenses / 'THIRD-PARTY-NOTICES.md'
    record_path = licenses / 'source-exclusions.json'
    readme_path = licenses / 'source/README.md'
    for path in (archive_path, manifest_path, notice_path):
        if path.is_symlink() or not path.is_file():
            raise ValueError('Source preparation requires regular archive and notice files')
    records = json.loads(manifest_path.read_text())
    matches = [row for row in records if row.get('file') == f'source/{ARCHIVE_NAME}']
    if len(matches) != 1:
        raise ValueError('The VMAF archive needs exactly one source manifest record')
    row = matches[0]
    if row.get('source') != UPSTREAM_URL:
        raise ValueError('The upstream archive URL changed')
    if readme_path.exists() and not readme_path.read_text().startswith(README_MARKER):
        raise ValueError('An unrelated source README exists. It was not overwritten.')
    current_hash = digest_bytes(archive_path.read_bytes())
    with tempfile.TemporaryDirectory(prefix='.vmaf-preparation-', dir=licenses) as directory:
        temporary = Path(directory)
        replacement = temporary / ARCHIVE_NAME
        if current_hash == expected_sha:
            if row.get('sha256') != expected_sha and row.get('upstream_sha256') != expected_sha:
                raise ValueError('Source manifest hash does not match the pinned archive')
            report = repack_archive(archive_path, replacement, expected_sha, exclusions)
            changed = True
        else:
            if not record_path.is_file():
                raise ValueError('The archive is neither upstream nor a recorded prepared copy')
            report = json.loads(record_path.read_text())
            if report.get('original_sha256') != expected_sha or report.get('repacked_sha256') != current_hash:
                raise ValueError('Prepared source archive provenance does not match')
            if {item['path']: item['sha256'] for item in report.get('excluded_members', [])} != exclusions:
                raise ValueError('Prepared archive exclusion set does not match')
            retained = archive_members(archive_path)
            if members_digest(retained) != report.get('retained_members_sha256') or any(item.get('mach_o') for item in retained):
                raise ValueError('Prepared archive contents no longer match the preservation record')
            changed = False
        row.update(sha256=report['repacked_sha256'], bytes=report['repacked_bytes'],
                   upstream_sha256=report['original_sha256'], upstream_bytes=report['original_bytes'],
                   archive_variant='Original sources, without unused precompiled MATLAB examples',
                   modifications_manifest='source-exclusions.json')
        notices = notice_path.read_text()
        if NOTICE_MARKER not in notices:
            notices += ('\n\n' + NOTICE_MARKER + '\n\n'
                'The bundled VMAF source archive omits only unused precompiled MATLAB example binaries. '
                'All source and license members retain their contents and metadata. '
                'See source-exclusions.json for every omitted path, original and repacked archive hashes, '
                'and the retained-member verification. The source manifest sha256 describes the bundled '
                'archive. Its upstream_sha256 records the original download.\n')
        readme = (README_MARKER + '\n\n'
            'Archives retain upstream source and license material. VMAF has one documented packaging change: '
            'unused precompiled MATLAB examples are omitted for macOS notarization. No source member is removed.\n\n'
            f'VMAF upstream URL: {UPSTREAM_URL}\n'
            f'Original upstream SHA256: {report["original_sha256"]}\n'
            f'Bundled archive SHA256: {report["repacked_sha256"]}\n'
            f'Omitted compiled examples: {len(report["excluded_members"])}\n'
            f'Retained members: {report["retained_members"]}\n\n'
            'See ../source-exclusions.json for exact paths and per-file hashes. '
            'See ../upstream-source-manifest.json for the bundled archive sizes and hashes.\n')
        staged = {
            'source-exclusions.json': json.dumps(report, indent=2) + '\n',
            'upstream-source-manifest.json': json.dumps(records, ensure_ascii=False, indent=2) + '\n',
            'THIRD-PARTY-NOTICES.md': notices,
            'README.md': readme,
        }
        for name, text in staged.items():
            (temporary / name).write_text(text)
        # Write provenance first, so an interrupted replacement can be resumed.
        os.replace(temporary / 'source-exclusions.json', record_path)
        if changed:
            os.replace(replacement, archive_path)
        os.replace(temporary / 'upstream-source-manifest.json', manifest_path)
        os.replace(temporary / 'THIRD-PARTY-NOTICES.md', notice_path)
        os.replace(temporary / 'README.md', readme_path)
    return {'changed': changed, **report}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resources', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(sanitize_resources(args.resources.resolve(strict=True)), indent=2))


if __name__ == '__main__':
    main()
