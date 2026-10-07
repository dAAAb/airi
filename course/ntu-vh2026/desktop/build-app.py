"""Assemble a distinct Apple Silicon app from verified, prebuilt local resources.

Downloads are separate. This command never copies the user's browser profile,
Ollama keys, recordings, or arbitrary home directories.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
COURSE = ROOT.parent
APP_ID = 'ai.daaaab.airi-local-classroom'
MIN_FREE = 5 * 1024 ** 3
LITE_MODELS = ['qwen', 'asr26', 'kokoro']
FULL_DEFAULT_MODELS = ['sarc-taigi', 'gemma4', 'asr26', 'kokoro', 'kaedetai']
APP_VERSION = json.loads((ROOT / 'package.json').read_text())['version']


def reserve(path, additional=0):
    if shutil.disk_usage(path).free < MIN_FREE + additional:
        raise RuntimeError('Packaging stopped to preserve at least 5 GiB of free disk space.')


def clone_or_copy(source, target):
    source, target = Path(source), Path(target)
    reserve(target.parent)
    if sys.platform == 'darwin':
        libc = ctypes.CDLL(None, use_errno=True)
        clonefile = libc.clonefile
        clonefile.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        clonefile.restype = ctypes.c_int
        if clonefile(os.fsencode(source), os.fsencode(target), 0) == 0:
            shutil.copystat(source, target)
            return str(target)
    reserve(target.parent, source.stat().st_size)
    shutil.copy2(source, target)
    return str(target)


def copy_tree(source, target, ignore=None):
    shutil.copytree(source, target, symlinks=True, copy_function=clone_or_copy, ignore=ignore)


def check_internal_links(root):
    for item in root.rglob('*'):
        if item.is_symlink() and not item.resolve().is_relative_to(root.resolve()):
            raise ValueError(f'Non-portable symlink leaves Resources: {item.relative_to(root)}')


def check_relative(value):
    path = Path(value)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Manifest paths must stay inside Resources')
    return path


def select_manifest(source, mode):
    manifest = json.loads(json.dumps(source))
    all_models = {row['model'] for row in manifest['files']} | {row['id'] for row in manifest.get('ollama_models', [])}
    if mode == 'lite':
        if not set(LITE_MODELS).issubset(all_models):
            raise ValueError('Lite needs the pinned qwen, asr26, and kokoro payload records')
        allowed = set(LITE_MODELS)
        manifest['files'] = [row for row in manifest['files'] if row['model'] in allowed]
        manifest['ollama_models'] = [row for row in manifest['ollama_models'] if row['id'] in allowed]
        manifest['services'] = [row for row in manifest['services'] if set(row.get('requires', [])).issubset(allowed)]
        manifest['available_models'] = LITE_MODELS[:]
    else:
        manifest['available_models'] = sorted(all_models)
    manifest['default_models'] = (FULL_DEFAULT_MODELS if mode == 'full' else LITE_MODELS)[:]
    manifest['offline'] = mode != 'thin'
    return manifest


def copy_lite_payload(source, target, manifest):
    # Copy referenced files only. Copying the whole Ollama blobs directory would
    # silently add the two 12B models to the small package.
    for item in manifest['files']:
        relative = check_relative(item['path'])
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        clone_or_copy(source / relative, destination)
    for record in manifest['ollama_models']:
        relative = check_relative(record['path'])
        model_path = source / 'ollama/manifests' / relative
        raw = model_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != record['manifest_sha256']:
            raise ValueError('The Lite Ollama manifest differs from its pinned checksum')
        model = json.loads(raw)
        for item in [model['config'], *model['layers']]:
            digest = item['digest']
            if not digest.startswith('sha256:') or len(digest) != 71 or any(c not in '0123456789abcdef' for c in digest[7:]):
                raise ValueError('Invalid Lite Ollama blob identifier')
            blob = Path('ollama/blobs') / digest.replace(':', '-')
            destination = target / blob
            if (source / blob).stat().st_size != item['size']:
                raise ValueError('The Lite Ollama blob has an unexpected size')
            if not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                clone_or_copy(source / blob, destination)
        destination = target / 'ollama/manifests' / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        clone_or_copy(model_path, destination)
    (target / 'ollama/classroom-manifest.json').write_text(json.dumps(manifest['ollama_models'], indent=2) + '\n')


def validate_resources(resources, mode):
    manifest = json.loads((resources / 'payload-manifest.json').read_text())
    for entry in ('runtimes/python/bin/python3', 'runtimes/ollama/ollama', 'web/index.html', 'installer/manager.py',
                  'web/local-models/onnx-community/silero-vad/onnx/model.onnx',
                  'web/local-assets/onnx/ort-wasm-simd-threaded.wasm'):
        if not (resources / entry).is_file():
            raise ValueError(f'Missing app resource: {entry}')
    if not manifest.get('services') or not manifest.get('files'):
        raise ValueError('A model and service manifest is required for a usable installer')
    for service in manifest['services']:
        if not (resources / check_relative(service['executable'])).is_file():
            raise ValueError(f'Service runtime is missing: {service["id"]}')
    for item in manifest['files']:
        relative = check_relative(item['path'])
        if not isinstance(item['bytes'], int) or item['bytes'] < 0 or len(item['sha256']) != 64:
            raise ValueError('Each model file needs its fixed size and SHA256')
        if mode in ('full', 'lite'):
            model = resources / 'payload' / relative
            if not model.is_file() or model.stat().st_size != item['bytes']:
                raise ValueError(f'Offline payload is missing or incomplete: {relative}')
        elif not item.get('url', '').startswith('https://'):
            raise ValueError(f'Downloadable payload needs an HTTPS source: {relative}')
    if mode in ('full', 'lite') and not (resources / 'payload/ollama/blobs').is_dir():
        raise ValueError('The full app requires the separately exported Ollama model store')
    check_internal_links(resources)
    manifest['offline'] = mode != 'thin'
    (resources / 'payload-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


def remove_web_sourcemaps(web_root):
    # Source maps can contain the build machine's absolute paths. They are not
    # needed for the packaged UI and must not accompany a public Mac release.
    for source_map in Path(web_root).rglob('*.map'):
        if source_map.is_file():
            source_map.unlink()


def rebrand(app):
    icon = ROOT.parents[2] / 'apps/stage-tamagotchi/build/icon.icns'
    if icon.is_file():
        icon_target = app / 'Contents/Resources/airi-local.icns'
        icon_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(icon, icon_target)
    for plist in [app / 'Contents/Info.plist', *app.glob('Contents/Frameworks/*Helper*.app/Contents/Info.plist')]:
        values = plistlib.loads(plist.read_bytes())
        helper = plist != app / 'Contents/Info.plist'
        suffix = values.get('CFBundleIdentifier', '').removeprefix('com.github.Electron')
        values.update(CFBundleIdentifier=APP_ID + (suffix or '.helper') if helper else APP_ID,
                      CFBundleDisplayName='AIRI Local Helper' if helper else 'AIRI Local',
                      CFBundleName='AIRI Local Helper' if helper else 'AIRI Local')
        if not helper:
            executable = app / 'Contents/MacOS' / values['CFBundleExecutable']
            renamed = executable.with_name('AIRI Local')
            if executable != renamed:
                executable.rename(renamed)
            values.update(CFBundleShortVersionString=APP_VERSION, CFBundleVersion=APP_VERSION,
                          CFBundleExecutable='AIRI Local',
                          CFBundleIconFile='airi-local.icns' if icon.is_file() else values.get('CFBundleIconFile', 'electron.icns'),
                          NSMicrophoneUsageDescription='AIRI Local 使用麥克風，讓本機虛擬角色聽見你的國語或台語。',
                          NSHighResolutionCapable=True)
        plist.write_bytes(plistlib.dumps(values))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resources', type=Path, default=COURSE / 'installer/resources')
    parser.add_argument('--electron-app', type=Path, default=ROOT / '.cache/electron-43.4.1-arm64/Electron.app')
    parser.add_argument('--web', type=Path, default=ROOT.parents[2] / 'apps/stage-web/dist')
    parser.add_argument('--mode', choices=('thin', 'full', 'lite'), default='thin')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--sign-identity', default='-')
    parser.add_argument('--no-sign', action='store_true', help='For test fixtures only. Not a runnable release on Apple Silicon.')
    args = parser.parse_args()
    names = {'thin': 'AIRI Local.app', 'full': 'AIRI Local Full.app', 'lite': 'AIRI Local Lite.app'}
    output = args.output or ROOT / 'dist' / names[args.mode]
    if output.exists():
        raise SystemExit('Output already exists. Use a new output name to preserve the previous build.')
    if not args.electron_app.is_dir() or not (args.web / 'index.html').is_file():
        raise SystemExit('Run download-electron.py and build-web.sh before packaging.')
    if not args.resources.is_dir():
        raise SystemExit('Prepare portable runtimes and a payload-manifest.json first.')
    subprocess.run(['node', str(ROOT / 'build-native.mjs')], check=True)
    manifest = select_manifest(json.loads((args.resources / 'payload-manifest.json').read_text()), args.mode)
    output.parent.mkdir(parents=True, exist_ok=True)
    reserve(output.parent)
    copy_tree(args.electron_app, output)
    resources = output / 'Contents/Resources'
    for remove in ('default_app.asar', 'app.asar'):
        (resources / remove).unlink(missing_ok=True)
    app_source = resources / 'app'
    app_source.mkdir()
    for name in ('package.json', 'policy.cjs'):
        clone_or_copy(ROOT / name, app_source / name)
    for name in ('main.cjs', 'preload.cjs'):
        clone_or_copy(ROOT / '.compiled' / name, app_source / name)
    ignored = {'web', 'installer', 'app', '.DS_Store', '__pycache__', 'payload-manifest.json'}
    if args.mode == 'thin':
        ignored.add('payload')
    for item in args.resources.iterdir():
        if item.name in ignored or item.name.startswith('.'):
            continue
        if args.mode == 'lite' and item.name == 'upstream':
            continue
        if args.mode == 'lite' and item.name == 'runtimes':
            destination = resources / 'runtimes'
            destination.mkdir()
            for name in ('python', 'asr', 'kokoro', 'ollama'):
                copy_tree(item / name, destination / name)
            continue
        if args.mode == 'lite' and item.name == 'payload':
            copy_lite_payload(item, resources / 'payload', manifest)
            continue
        if item.is_dir():
            copy_tree(item, resources / item.name)
        else:
            clone_or_copy(item, resources / item.name)
    (resources / 'payload-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    copy_tree(args.web, resources / 'web')
    for name in ('local-models', 'local-assets'):
        source = args.resources / 'web' / name
        if source.is_dir():
            shutil.copytree(source, resources / 'web' / name, symlinks=True,
                            copy_function=clone_or_copy, dirs_exist_ok=True)
    # Match the workspace's pinned onnxruntime-web used by Transformers.js.
    onnx = ROOT.parents[2] / 'node_modules/.pnpm/onnxruntime-web@1.27.0/node_modules/onnxruntime-web'
    if not onnx.is_dir():
        raise ValueError('Install the pinned onnxruntime-web 1.27.0 before packaging VAD assets')
    onnx_target = resources / 'web/local-assets/onnx'
    onnx_target.mkdir(parents=True, exist_ok=True)
    for source in [*onnx.glob('dist/*.wasm'), *onnx.glob('dist/*.mjs'), onnx / 'LICENSE']:
        if source.is_file() and not (onnx_target / source.name).exists():
            clone_or_copy(source, onnx_target / source.name)
    remove_web_sourcemaps(resources / 'web')
    copy_tree(COURSE / 'installer', resources / 'installer',
              ignore=shutil.ignore_patterns('resources', '__pycache__', '*.pyc', '*.log', '.DS_Store'))
    course_source = resources / 'course/ntu-vh2026'
    course_source.mkdir(parents=True, exist_ok=True)
    for name in ('asr26', 'taigi-tts', 'local-speech-hub'):
        if args.mode == 'lite' and name == 'taigi-tts':
            continue
        copy_tree(COURSE / name, course_source / name,
                  ignore=shutil.ignore_patterns('.venv*', 'local', 'models', 'output', 'logs', '__pycache__', '*.pyc', '*.log', '*.pid'))
    notices = resources / 'notices'
    notices.mkdir(exist_ok=True)
    for name in ('LICENSE', 'LICENSES.chromium.html'):
        source = args.electron_app.parent / name
        if source.is_file():
            clone_or_copy(source, notices / f'Electron-{name}')
    manifest = validate_resources(resources, args.mode)
    rebrand(output)
    metadata = {'app_id': APP_ID, 'version': APP_VERSION, 'electron': '43.4.1',
                'architecture': 'arm64', 'flavor': args.mode, 'offline': manifest['offline'],
                'models': sorted({row['model'] for row in manifest['files']}
                                 | {row['id'] for row in manifest.get('ollama_models', [])}),
                'signing': 'unsigned' if args.no_sign else 'ad-hoc' if args.sign_identity == '-' else 'developer-id',
                'notarized': False}
    (resources / 'build-info.json').write_text(json.dumps(metadata, indent=2) + '\n')
    if not args.no_sign:
        subprocess.run(['/usr/bin/codesign', '--force', '--deep', '--sign', args.sign_identity,
                        '--entitlements', str(ROOT / 'entitlements.plist'), str(output)], check=True)
        subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(output)], check=True)
    reserve(output.parent)
    print(json.dumps({'app': str(output.resolve()), **metadata}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
