"""Remove installation-specific Python metadata from a copied standalone tree."""
from pathlib import Path
import struct
import subprocess


def relocate(runtime, original_base, version):
    original = str(original_base.resolve())
    # Standalone CPython already resolves its runtime prefix from the executable.
    # uv rewrites build-time sysconfig strings during installation. Rebind those
    # strings to sys.base_prefix rather than preserving the development machine.
    for config in runtime.glob(f'lib/python{version}/_sysconfigdata*.py'):
        source = config.read_text()
        if original in source:
            source = source.replace(original, '/AIRI_RELOCATABLE_PYTHON')
            source += '\nimport sys as _airi_sys\n'
            source += 'build_time_vars = {key: value.replace("/AIRI_RELOCATABLE_PYTHON", _airi_sys.base_prefix) if isinstance(value, str) else value for key, value in build_time_vars.items()}\n'
            config.write_text(source)
    # CLI wrappers are not used by the app, but must not expose a home prefix.
    for command in (runtime/'bin').iterdir():
        if command.is_symlink() or not command.is_file():
            continue
        data = command.read_bytes()
        if data.startswith(b'#!') and original.encode() in data:
            lines = data.split(b'\n', 1)
            command.write_bytes(f'#!/usr/bin/env python{version}\n'.encode()+lines[1].replace(original.encode(), b'/AIRI_RELOCATABLE_PYTHON'))
    library = runtime/f'lib/libpython{version}.dylib'
    data = bytearray(library.read_bytes())
    if data[:4] != b'\xcf\xfa\xed\xfe':
        raise RuntimeError('Expected Apple Silicon thin Mach-O libpython')
    count = struct.unpack_from('<I', data, 16)[0]
    offset = 32
    changed = False
    for _ in range(count):
        command, size = struct.unpack_from('<II', data, offset)
        if command == 0xd:  # LC_ID_DYLIB, not a dependency load command.
            location = struct.unpack_from('<I', data, offset+8)[0]
            value = f'@rpath/libpython{version}.dylib'.encode()+b'\0'
            if len(value) > size-location:
                raise RuntimeError('Install ID does not fit in the existing command')
            data[offset+location:offset+size] = value.ljust(size-location, b'\0')
            changed = True
        offset += size
    if not changed:
        raise RuntimeError('Missing libpython install ID')
    library.write_bytes(data)
    subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', str(library)], check=True)
    subprocess.run(['/usr/bin/codesign', '--verify', str(library)], check=True)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('runtime', type=Path)
    parser.add_argument('original_base', type=Path)
    parser.add_argument('version')
    args = parser.parse_args()
    relocate(args.runtime, args.original_base, args.version)
