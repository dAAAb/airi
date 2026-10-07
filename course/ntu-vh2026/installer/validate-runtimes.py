"""Import native dependencies using each copied Python, isolated from user site."""
import argparse
import json
from pathlib import Path
import subprocess

PROBES = {
    'python': ('3.12', 'import ssl; details={"ssl":ssl.OPENSSL_VERSION}'),
    'asr': ('3.12', 'import mlx.core as mx,transformers,fastapi,av; details={"mlx":mx.__version__,"transformers":transformers.__version__,"av":av.__version__}'),
    'taigi': ('3.11', 'import torch,transformers,soundfile,taibun; details={"torch":torch.__version__,"transformers":transformers.__version__,"libsndfile":soundfile.__libsndfile_version__,"taibun_probe":taibun.Converter(system="POJ",sandhi="none").get("你好")}'),
    'kokoro': ('3.12', 'import torch,transformers,kokoro,soundfile,av; details={"torch":torch.__version__,"transformers":transformers.__version__,"kokoro":kokoro.__version__,"av":av.__version__,"mp3":soundfile.available_formats().get("MP3")}'),
}


def validate(root):
    rows = []
    for name, (version, body) in PROBES.items():
        runtime = root/name
        code = ('import sys,sysconfig,json;from pathlib import Path;' + body +
                ';assert Path(sysconfig.get_config_var("LIBDIR")).resolve().is_relative_to(Path(sys.prefix).resolve());'
                # Torch 2.8 imports its JIT instantiator, which creates a fresh
                # TemporaryDirectory for generated modules and adds that exact
                # directory to sys.path. This is not a build-machine dependency.
                'jit=sys.modules.get("torch.distributed.nn.jit.instantiator");'
                'jit_dir=Path(jit.INSTANTIATED_TEMPLATE_DIR_PATH).resolve() if jit else None;'
                'assert not jit or Path(jit.__file__).resolve().is_relative_to(Path(sys.prefix).resolve());'
                'assert all(not path or Path(path).resolve().is_relative_to(Path(sys.prefix).resolve()) or Path(path).resolve()==jit_dir for path in sys.path);'
                'details["generated_torch_jit_temporary_path"]=bool(jit_dir);'
                'print(json.dumps(details,ensure_ascii=False))')
        output = subprocess.check_output([str(runtime/f'bin/python{version}'), '-I', '-B', '-c', code], text=True)
        rows.append({'runtime': name, 'imports': json.loads(output)})
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    rows = validate(args.root.resolve())
    (args.root/'runtime-import-validation.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(rows, ensure_ascii=False, indent=2))
