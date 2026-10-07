"""Read Mach-O load commands without Xcode. Audit relative runtime bundles."""
import argparse
import json
import os
from pathlib import Path
import struct


def load_paths(data, start=0):
    magic = data[start:start+4]
    if magic in (b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf'):
        count = struct.unpack_from('>I', data, start+4)[0]
        wide = magic[-1] == 0xbf
        for i in range(count):
            offset = struct.unpack_from('>Q' if wide else '>I', data,
                start+8+i*(32 if wide else 20)+8)[0]
            yield from load_paths(data, offset)
        return
    if magic not in (b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf'):
        return
    endian = '<' if magic == b'\xcf\xfa\xed\xfe' else '>'
    count = struct.unpack_from(endian+'I', data, start+16)[0]
    offset = start+32
    for _ in range(count):
        command, size = struct.unpack_from(endian+'II', data, offset)
        if size < 8 or offset+size > len(data):
            raise ValueError('Invalid Mach-O load command')
        if command & 0x7fffffff in (0xc, 0xd, 0x18, 0x1f, 0x20, 0x1c):
            location = struct.unpack_from(endian+'I', data, offset+8)[0]
            yield command, data[offset+location:offset+size].split(b'\0')[0].decode()
        offset += size


def audit(root):
    issues, count, metadata = [], 0, []
    names = {p.name for p in root.rglob('*') if p.is_file()}
    for path in root.rglob('*'):
        if path.is_symlink():
            if os.path.isabs(os.readlink(path)) or not path.resolve().is_relative_to(root.resolve()):
                issues.append({'file': str(path.relative_to(root)), 'error': 'External or absolute symlink'})
            continue
        if not path.is_file():
            continue
        with path.open('rb') as source:
            magic = source.read(4)
        if magic not in (b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf'):
            continue
        count += 1
        for command, value in load_paths(path.read_bytes()):
            # LC_ID_DYLIB names the binary itself. LC_RPATH adds a search
            # directory. Neither is a dependency that must exist at that path.
            if command & 0x7fffffff in (0xd, 0x1c):
                if value.startswith('/') and not value.startswith(('/usr/lib', '/System/Library/')):
                    metadata.append({'file': str(path.relative_to(root)),
                                     'kind': 'install-id' if command & 0x7fffffff == 0xd else 'search-path',
                                     'value': value.replace(str(Path.home()), '<home>')})
                continue
            if value.startswith(('/usr/lib/', '/System/Library/')):
                continue
            if value.startswith('/'):
                issues.append({'file': str(path.relative_to(root)), 'dependency': value,
                               'error': 'Absolute non-system loader path'})
            elif value.startswith('@loader_path/'):
                target = path.parent/value.removeprefix('@loader_path/')
                if not target.exists():
                    issues.append({'file': str(path.relative_to(root)), 'dependency': value,
                                   'error': 'Missing loader-relative file'})
            elif value.startswith('@rpath/') and command & 0x7fffffff != 0xd:
                # Runtime import tests verify the actual search chain. This
                # static check ensures the dependency is present in the tree.
                if Path(value).name not in names:
                    issues.append({'file': str(path.relative_to(root)), 'dependency': value,
                                   'error': 'Rpath dependency absent from runtime'})
    return {'native_files': count, 'issues': issues, 'build_metadata': metadata,
            'scope': 'Static load paths plus separately recorded imports. Not a codesign/notarization check.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = audit(args.root)
    report = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(report+'\n')
    print(report)
    raise SystemExit(bool(result['issues']))
