"""Create a Developer ID signed copy without changing the source application.

The source bundle contains Python extensions outside standard nested-code paths.
Sign every Mach-O explicitly, then enclosing bundles, then the outer application.
Notarization and release uploads are separate steps.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile


MACH_MAGICS = {
    b'\xce\xfa\xed\xfe': '<', b'\xcf\xfa\xed\xfe': '<',
    b'\xfe\xed\xfa\xce': '>', b'\xfe\xed\xfa\xcf': '>',
}
FAT_MAGICS = {
    b'\xca\xfe\xba\xbe': ('>', 20), b'\xbe\xba\xfe\xca': ('<', 20),
    b'\xca\xfe\xba\xbf': ('>', 32), b'\xbf\xba\xfe\xca': ('<', 32),
}
JIT_ENTITLEMENTS = {
    'com.apple.security.cs.allow-jit': True,
    'com.apple.security.cs.allow-unsigned-executable-memory': True,
}
NOTARIZATION_MARKER = 'Verify the stapled ticket or release attestation'


def mach_types(path):
    """Read Mach-O file types, including every architecture in a universal file."""
    if path.is_symlink() or not path.is_file():
        return set()
    with path.open('rb') as stream:
        header = stream.read(16)
        magic = header[:4]
        if magic in MACH_MAGICS and len(header) == 16:
            return {struct.unpack(MACH_MAGICS[magic] + 'I', header[12:16])[0]}
        if magic not in FAT_MAGICS or len(header) < 8:
            return set()
        endian, stride = FAT_MAGICS[magic]
        count = struct.unpack(endian + 'I', header[4:8])[0]
        if not 1 <= count <= 32:
            raise ValueError(f'Invalid universal Mach-O architecture count: {path}')
        types = set()
        for index in range(count):
            stream.seek(8 + stride * index)
            entry = stream.read(stride)
            if len(entry) != stride:
                raise ValueError(f'Truncated universal Mach-O: {path}')
            width = 8 if stride == 32 else 4
            offset = struct.unpack(endian + ('Q' if width == 8 else 'I'), entry[8:8 + width])[0]
            stream.seek(offset)
            inner = stream.read(16)
            if inner[:4] not in MACH_MAGICS or len(inner) != 16:
                raise ValueError(f'Invalid universal Mach-O slice: {path}')
            types.add(struct.unpack(MACH_MAGICS[inner[:4]] + 'I', inner[12:16])[0])
        return types


def inventory(app):
    files, bundles = [], []
    for directory, children, names in os.walk(app, followlinks=False):
        current = Path(directory)
        children[:] = sorted(name for name in children if not (current / name).is_symlink())
        if current != app and current.suffix in ('.app', '.framework', '.xpc', '.bundle'):
            if any((current / name).is_file() for name in ('Contents/Info.plist', 'Resources/Info.plist', 'Info.plist')):
                bundles.append(current)
        for name in sorted(names):
            path = current / name
            types = mach_types(path)
            if types:
                files.append((path, types))
    bundles.sort(key=lambda item: (-len(item.parts), str(item)))
    return files, bundles


def entitlements_for(path, app):
    relative = path.relative_to(app)
    if path == app or relative.parts[:2] == ('Contents', 'MacOS'):
        return {**JIT_ENTITLEMENTS, 'com.apple.security.device.audio-input': True}
    if 'Electron Helper' in str(relative):
        return JIT_ENTITLEMENTS.copy()
    if relative.parts[:3] == ('Contents', 'Resources', 'runtimes'):
        if path.parent.name == 'bin' and path.name.startswith('python'):
            return JIT_ENTITLEMENTS.copy()
    return {}


def signing_command(path, identity, executable, entitlements_path=None):
    command = ['/usr/bin/codesign', '--force', '--sign', identity, '--timestamp']
    if executable:
        command.extend(['--options', 'runtime'])
    if entitlements_path:
        command.extend(['--entitlements', str(entitlements_path)])
    return [*command, str(path)]


def validate_paths(source, output, resume=False):
    source = source.resolve(strict=True)
    output = output.absolute()
    if source.suffix != '.app' or not (source / 'Contents/Info.plist').is_file():
        raise ValueError('Source must be an existing macOS application bundle')
    if output.suffix != '.app' or output.is_symlink():
        raise ValueError('Output must be a real .app path, not a symlink')
    if output.resolve().is_relative_to(source) or source.is_relative_to(output.resolve()):
        raise ValueError('Source and output must be separate application bundles')
    if resume:
        if not (output / 'Contents/Info.plist').is_file():
            raise ValueError('Resume needs an existing prepared application copy')
        source_info = json.loads((source / 'Contents/Resources/build-info.json').read_text())
        output_info = json.loads((output / 'Contents/Resources/build-info.json').read_text())
        if output_info.get('signing') != 'developer-id' or output_info.get('notarization') != NOTARIZATION_MARKER:
            raise ValueError('Output is not a copy prepared by this signing workflow')
        omitted = {'signing', 'notarized', 'notarization'}
        if {key: value for key, value in source_info.items() if key not in omitted} != {
                key: value for key, value in output_info.items() if key not in omitted}:
            raise ValueError('Prepared copy metadata does not match the source build')
        if (source / 'Contents/Info.plist').read_bytes() != (output / 'Contents/Info.plist').read_bytes():
            raise ValueError('Prepared copy application identity does not match the source')
    elif output.exists():
        raise ValueError('Output must be a new .app path')
    return source, output


def developer_identity(requested, listing):
    for digest, name in re.findall(r'([0-9A-Fa-f]{40})\s+"([^"]+)"', listing):
        if requested in (digest, name) and name.startswith('Developer ID Application: '):
            return digest
    raise ValueError('The selected identity is not a valid Developer ID Application identity')


def remove_interrupted_signing_temps(source, output):
    """Remove recognized codesign scratch files from a stopped, prepared copy."""
    removed = []
    for directory, children, names in os.walk(output, followlinks=False):
        current = Path(directory)
        children[:] = [name for name in children if not (current / name).is_symlink()]
        for name in names:
            if not name.endswith('.cstemp'):
                continue
            scratch = current / name
            relative = scratch.relative_to(output)
            source_scratch = source / relative
            if source_scratch.exists() or source_scratch.is_symlink():
                continue
            target = scratch.with_name(name[:-len('.cstemp')])
            source_target = source / target.relative_to(output)
            if scratch.is_symlink() or not scratch.is_file() or not mach_types(target) or not mach_types(source_target):
                raise ValueError(f'Unrecognized signing scratch file, retained for inspection: {relative}')
            scratch.unlink()
            removed.append(str(relative))
    return removed


def sign_native_files(files, sign, workers, progress=None):
    """Parallelize separate files while keeping hardlinked aliases serial."""
    if not 1 <= workers <= 8:
        raise ValueError('Use between 1 and 8 signing workers')
    groups = {}
    for path, types in files:
        stat = path.stat()
        groups.setdefault((stat.st_dev, stat.st_ino), []).append((path, types))

    def sign_group(group):
        for path, types in group:
            sign(path, 2 in types)
        return len(group)

    pool = ThreadPoolExecutor(max_workers=workers)
    futures = []
    try:
        futures = [pool.submit(sign_group, group) for group in groups.values()]
        completed = 0
        for future in as_completed(futures):
            completed += future.result()
            if progress:
                progress(completed, len(files))
    except BaseException:
        for future in futures:
            future.cancel()
        raise
    finally:
        pool.shutdown(wait=True, cancel_futures=True)


def sign_copy(source, output, identity, workers=4, resume=False):
    source, output = validate_paths(source, output, resume)
    listing = subprocess.run(['/usr/bin/security', 'find-identity', '-v', '-p', 'codesigning'],
                             check=True, capture_output=True, text=True)
    identity = developer_identity(identity, listing.stdout)
    if resume:
        removed = remove_interrupted_signing_temps(source, output)
        if removed:
            print(f'Removed interrupted signing scratch files: {len(removed)}', flush=True)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        size = sum(path.stat().st_size for path in source.rglob('*') if path.is_file() and not path.is_symlink())
        if shutil.disk_usage(output.parent).free < size + 5 * 1024 ** 3:
            raise RuntimeError('Leave room for the application copy and 5 GiB of free space')
        subprocess.run(['/usr/bin/ditto', str(source), str(output)], check=True)
        metadata_path = output / 'Contents/Resources/build-info.json'
        metadata = json.loads(metadata_path.read_text())
        # Notarization is an external ticket. Never edit sealed resources after signing.
        metadata.pop('notarized', None)
        metadata.update(signing='developer-id', notarization=NOTARIZATION_MARKER)
        metadata_path.write_text(json.dumps(metadata, indent=2) + '\n')
    subprocess.run([sys.executable, str(Path(__file__).with_name('sanitize-source-archives.py')),
                    '--resources', str(output / 'Contents/Resources')], check=True, stdout=subprocess.DEVNULL)
    files, bundles = inventory(output)
    if not files:
        raise ValueError('No Mach-O code was found')
    with tempfile.TemporaryDirectory(prefix='airi-sign-') as temporary:
        entitlement_paths = {}
        for name, entitlements in (
                ('jit', JIT_ENTITLEMENTS),
                ('main', {**JIT_ENTITLEMENTS, 'com.apple.security.device.audio-input': True})):
            path = Path(temporary) / f'{name}.plist'
            path.write_bytes(plistlib.dumps(entitlements, fmt=plistlib.FMT_XML))
            entitlement_paths[tuple(sorted(entitlements.items()))] = path

        def sign(path, executable):
            entitlements = entitlements_for(path, output) if executable else {}
            subprocess.run(signing_command(path, identity, executable,
                entitlement_paths.get(tuple(sorted(entitlements.items())))),
                check=True, stdout=subprocess.DEVNULL)

        def progress(completed, total):
            if completed % 25 == 0 or completed == total:
                print(f'Signed native code: {completed}/{total}', flush=True)

        sign_native_files(files, sign, workers, progress)
        for bundle in bundles:
            sign(bundle, bundle.suffix in ('.app', '.xpc'))
        sign(output, True)
    subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(output)], check=True)
    # The app check treats Resources as data. Verify each embedded runtime too.
    for path, _ in files:
        subprocess.run(['/usr/bin/codesign', '--verify', '--strict', str(path)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return {'app': str(output), 'native_files': len(files), 'nested_bundles': len(bundles),
            'signing': 'developer-id', 'notarized': False, 'verified': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--identity', help='Developer ID Application certificate SHA-1 or exact name')
    parser.add_argument('--audit-only', action='store_true')
    parser.add_argument('--workers', type=int, choices=range(1, 9), default=4)
    parser.add_argument('--resume-existing-copy', action='store_true',
                        help='Re-sign an interrupted prepared copy. Stop the earlier signing process first.')
    args = parser.parse_args()
    if args.audit_only:
        files, bundles = inventory(args.source.resolve(strict=True))
        print(json.dumps({'native_files': len(files), 'executables': sum(2 in types for _, types in files),
                          'nested_bundles': len(bundles)}, indent=2))
        return
    if sys.platform != 'darwin':
        parser.error('Developer ID signing requires macOS')
    if not args.output or not args.identity or args.identity == '-':
        parser.error('Signing needs a new --output path and a Developer ID --identity')
    result = sign_copy(args.source, args.output, args.identity, args.workers, args.resume_existing_copy)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
