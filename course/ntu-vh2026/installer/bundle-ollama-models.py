"""Copy only the selected pinned, public classroom models into an offline payload.

No account keys, unrelated models, chat data, or Ollama settings are copied.
APFS clones save build space while producing normal, independently writable files.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

MODELS = {
    'qwen': ('registry.ollama.ai/library/qwen3.5/0.8b',
             'de63045f29755d4721c09d54c9b45c2dadb644f4fd7d604d4cac90d96049971c',
             'de63045f29755d4721c09d54c9b45c2dadb644f4fd7d604d4cac90d96049971c'),
    'sarc-taigi': ('hf.co/Speech-AI-Research-Center/SARC-Taigi-LLM-12b-GGUF/Q4_K_M',
                   '4e3a8b383ad5f06ea445a62699b93505c052afbf93c066a3848125ed6173142a',
                   '66544e32e46623d914413577b2b353c853d071612f7304792b817d924554930b'),
    'gemma4': ('registry.ollama.ai/library/gemma4/12b-it-qat',
              '2577ea3d73f81c16a6b1c1c4721371a99631c13edcee2a4cd248e37671b6e693',
              '38044be4f923e5a55264ed7df4eaac2676651a905f735197c504045140c02bd3'),
}


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def copy_verified(source, destination, expected, clone):
    if digest(source) != expected:
        raise ValueError(f'Unexpected model file: {source.name}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if digest(destination) != expected:
            raise ValueError(f'Destination exists with another checksum: {destination.name}')
        return
    if clone and sys.platform == 'darwin':
        # cp -c creates an APFS clone, not a symlink or shared writable hard link.
        subprocess.run(['/bin/cp', '-c', str(source), str(destination)], check=True)
    else:
        if shutil.disk_usage(destination.parent).free < source.stat().st_size + 5 * 1024 ** 3:
            raise RuntimeError('Leave at least 5 GiB free while building')
        shutil.copy2(source, destination)


def bundle(source, target, clone=False, models=None):
    report = []
    selected = list(MODELS) if models is None else list(dict.fromkeys(models))
    if not selected or any(key not in MODELS for key in selected):
        raise ValueError('Select known classroom models')
    for key in selected:
        relative, expected, model_digest = MODELS[key]
        manifest_path = source / 'manifests' / relative
        raw = manifest_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError(f'{key} manifest differs from the tested model')
        manifest = json.loads(raw)
        for item in [manifest['config'], *manifest['layers']]:
            identifier = item['digest']
            if not identifier.startswith('sha256:') or len(identifier) != 71:
                raise ValueError('Invalid blob identifier')
            expected_blob = identifier.removeprefix('sha256:')
            if any(char not in '0123456789abcdef' for char in expected_blob):
                raise ValueError('Invalid blob digest')
            name = identifier.replace(':', '-')
            blob = source / 'blobs' / name
            if blob.stat().st_size != item['size']:
                raise ValueError(f'{key} blob size differs')
            copy_verified(blob, target / 'blobs' / name, expected_blob, clone)
        copy_verified(manifest_path, target / 'manifests' / relative, expected, clone)
        report.append({'id': key, 'path': relative, 'manifest_sha256': expected, 'ollama_model_digest': model_digest,
                       'bytes': sum(row['size'] for row in [manifest['config'], *manifest['layers']])})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Existing Ollama model store')
    parser.add_argument('--destination', type=Path, required=True, help='App Resources/payload/ollama')
    parser.add_argument('--apfs-clone', action='store_true')
    parser.add_argument('--models', nargs='+', choices=sorted(MODELS), help='Defaults to all pinned models; use qwen for Lite')
    args = parser.parse_args()
    source = args.source.expanduser().resolve(strict=True)
    destination = args.destination.expanduser().resolve()
    if destination == source or destination.is_relative_to(source):
        raise ValueError('The app payload must be outside the original model store')
    report = bundle(source, destination, args.apfs_clone, args.models)
    manifest = destination / 'classroom-manifest.json'
    previous = json.loads(manifest.read_text()) if manifest.is_file() else []
    merged = {row['id']: row for row in previous if row['id'] in MODELS}
    merged.update({row['id']: row for row in report})
    manifest.write_text(json.dumps(list(merged.values()), indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
