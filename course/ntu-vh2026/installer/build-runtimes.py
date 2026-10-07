"""Assemble standalone Apple Silicon Python runtimes from verified local inputs.

Do not copy a virtualenv executable. Copy an actual standalone CPython tree,
then the matching CPython ABI's wheels. Model weights are a separate payload.
"""
import argparse
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess


def clone(source, destination):
    destination.mkdir(parents=True, exist_ok=True)
    subprocess.run(['/bin/cp', '-cR', str(source.resolve())+'/.', str(destination)], check=True)


def build(base, environment, destination, version):
    if destination.exists():
        raise RuntimeError('Refusing to overwrite an existing runtime: ' + str(destination))
    clone(base, destination)
    site = destination / f'lib/python{version}/site-packages'
    if environment is not None:
        clone(environment/f'lib/python{version}/site-packages', site)
    # Virtualenv bootstrap and bytecode are tied to the development checkout.
    for name in ('_virtualenv.pth', '_virtualenv.py'):
        (site/name).unlink(missing_ok=True)
    for cache in destination.rglob('__pycache__'):
        if cache.is_dir():
            shutil.rmtree(cache)
    for file in destination.rglob('*.pyc'):
        file.unlink()
    for link in destination.rglob('*'):
        if link.is_symlink() and os.path.isabs(os.readlink(link)):
            target = link.resolve()
            if not target.is_relative_to(base.resolve()):
                raise RuntimeError('External absolute runtime symlink: ' + str(link.relative_to(destination)))
            relocated = destination / target.relative_to(base.resolve())
            link.unlink()
            link.symlink_to(os.path.relpath(relocated, link.parent))
    for pth in site.glob('*.pth'):
        if '/Users/' in pth.read_text() or '/home/' in pth.read_text():
            raise RuntimeError('Nonportable path in ' + pth.name)
    runpy.run_path(str(Path(__file__).with_name('relocate-python.py')))['relocate'](destination, base, version)
    executable = destination/f'bin/python{version}'
    result = subprocess.check_output([str(executable), '-I', '-B', '-c',
        'import sys,ssl,json;print(json.dumps({"prefix":sys.prefix,"version":sys.version,"ssl":ssl.OPENSSL_VERSION}))'], text=True)
    return {'runtime': destination.name, 'version': version, 'relocated_startup': json.loads(result)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('python311', 'python312', 'asr-env', 'taigi-env', 'kokoro-env', 'taibun-env', 'destination'):
        parser.add_argument('--'+key, type=Path, required=True)
    args = parser.parse_args()
    out = args.destination.resolve()
    reports = []
    for name, base, env, version in [
        ('python', args.python312, None, '3.12'),
        ('asr', args.python312, args.asr_env, '3.12'),
        ('taigi', args.python311, args.taigi_env, '3.11'),
        ('kokoro', args.python312, args.kokoro_env, '3.12'),
    ]:
        reports.append(build(base, env, out/name, version))
    # Taibun itself is pure Python. Its msgpack dependency already exists in
    # the Torch runtime with the correct CPython 3.11 ABI.
    taibun_site = args.taibun_env/'lib/python3.12/site-packages'
    target_site = out/'taigi/lib/python3.11/site-packages'
    for source in taibun_site.glob('taibun*'):
        if source.is_dir():
            clone(source, target_site/source.name)
    # PyAV bundles libav and replaces the development machine's ffmpeg CLI.
    kokoro_site = out/'kokoro/lib/python3.12/site-packages'
    asr_site = out/'asr/lib/python3.12/site-packages'
    for source in kokoro_site.glob('av*'):
        if source.is_dir() and (source.name == 'av' or source.name.startswith(('av-', 'av.libs'))):
            clone(source, asr_site/source.name)
    for cache in out.rglob('__pycache__'):
        if cache.is_dir():
            shutil.rmtree(cache)
    # No developer absolute prefixes appear in the public report.
    for report in reports:
        report['relocated_startup']['prefix'] = 'runtimes/' + report['runtime']
    (out/'runtime-build-report.json').write_text(json.dumps(reports, indent=2)+'\n')
    print(json.dumps(reports, indent=2))


if __name__ == '__main__':
    main()
