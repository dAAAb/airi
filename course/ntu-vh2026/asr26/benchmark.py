"""Same 16 kHz mono PCM inputs; independent local ASR engines, fixed decoding.

Use the corresponding venv for --engine mlx or --engine base.
No remote audio upload; HF offline is enabled before model libraries load.
"""
import argparse
import hashlib
import json
import os
import platform
import resource
import subprocess
import time
import wave
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent.parent
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["DO_NOT_TRACK"] = "1"

def detect_hardware():
    def read_sysctl(key):
        try: return subprocess.check_output(["sysctl", "-n", key], text=True).strip()
        except (OSError, subprocess.CalledProcessError): return None
    ram = read_sysctl("hw.memsize")
    return {"chip": read_sysctl("machdep.cpu.brand_string") or platform.machine(), "physical_ram_bytes": int(ram) if ram else None}

def read_pcm(path):
    with wave.open(str(path)) as f:
        assert (f.getnchannels(), f.getframerate(), f.getsampwidth()) == (1, 16000, 2)
        return np.frombuffer(f.readframes(f.getnframes()), dtype="<i2").astype(np.float32) / 32768.0

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["mlx", "base"], required=True)
    parser.add_argument("--base-model-dir", type=Path, default=ROOT / "base-model", help="Optional externally obtained Whisper-base CTranslate2 directory")
    parser.add_argument("--manifest", type=Path, default=ROOT.parent / "local/fixtures.json")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--model-dir", type=Path, default=ROOT / "model")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--decode-mode", choices=["greedy", "timestamp-greedy", "fallback"], default="greedy")
    args = parser.parse_args()
    items = json.loads(args.manifest.read_text())["fixtures"]
    timestamps = args.decode_mode != "greedy"
    temperature = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0) if args.decode_mode == "fallback" else 0.0
    report = {"engine": args.engine, "timestamp": datetime.now(timezone.utc).isoformat(),
        "hardware": detect_hardware(),
        "platform": platform.platform(), "python": platform.python_version(), "offline": True,
        "decode": {"language": "zh", "task": "transcribe", "temperature": 0.0, "condition_on_previous_text": False,
                   "initial_prompt": None, "timestamps": False, "vad": False, "search": "greedy"},
        "scope": "Time includes mel preprocessing and complete decoding from preloaded 16k mono PCM; excludes file read, resampling, model download/load and audio capture. Different models/backends; not a pure MLX-vs-CPU speedup test.",
        "runs": []}
    report["decode"].update(mode=args.decode_mode, timestamps=timestamps, temperature=temperature)
    report["decode"]["search"] = "greedy with temperature fallback" if args.decode_mode == "fallback" else "greedy"
    if args.engine == "mlx":
        import mlx.core as mx
        from mlx_audio.stt.utils import load
        report["versions"] = {x: version(x) for x in ["mlx", "mlx-audio", "transformers"]}
        report["model"] = "RayyTien/Breeze-ASR-26-mlx-4bit"
        report["mlx_default_device"] = str(mx.default_device())
        started = time.perf_counter()
        model = load(str(args.model_dir.resolve()), strict=True)
        import runpy
        install_whisper_no_speech_compat = runpy.run_path(str(ROOT / "whisper-compat.py"))["install_whisper_no_speech_compat"]
        report["tokenizer_compatibility"] = install_whisper_no_speech_compat(model)
        mx.synchronize()
        report["model_load_seconds"] = time.perf_counter() - started
        report["loaded_mlx_bytes"] = mx.get_active_memory()
    else:
        from faster_whisper import WhisperModel
        report["versions"] = {x: version(x) for x in ["faster-whisper", "ctranslate2"]}
        report["model"] = "Systran/faster-whisper-base"
        report["compute"] = "cpu int8, 4 threads, beam=1, best_of=1"
        started = time.perf_counter()
        model = WhisperModel(str(args.base_model_dir.resolve()), device="cpu", compute_type="int8", cpu_threads=4, num_workers=1, local_files_only=True)
        report["model_load_seconds"] = time.perf_counter() - started
    print("MODEL_LOADED", json.dumps({k: v for k, v in report.items() if k != "runs"}, ensure_ascii=False), flush=True)
    output = args.output or ROOT.parent / "local/results" / f"{args.engine}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    for item in items:
        audio_path = args.manifest.parent / item["prepared_path"]
        audio = read_pcm(audio_path)
        for repeat in range(args.repeats):
            if args.engine == "mlx":
                mx.synchronize()
                mx.reset_peak_memory()
            started = time.perf_counter()
            if args.engine == "mlx":
                result = model.generate(audio, language="zh", task="transcribe", temperature=temperature,
                    return_timestamps=timestamps, word_timestamps=False, condition_on_previous_text=False, verbose=None)
                mx.synchronize()
                text = result.text
            else:
                segments, info = model.transcribe(audio, language="zh", task="transcribe", beam_size=1, best_of=1,
                    temperature=temperature, condition_on_previous_text=False, without_timestamps=not timestamps,
                    word_timestamps=False, vad_filter=False)
                text = "".join(s.text for s in segments)
            elapsed = time.perf_counter() - started
            row = {"id": item["id"], "category": item["category"], "repeat": repeat,
                "first_inference_in_process": len(report["runs"]) == 0,
                "duration_seconds": len(audio) / 16000, "inference_seconds": elapsed,
                "rtf": elapsed / (len(audio) / 16000), "text": text,
                "reference": item.get("reference"), "reference_type": item.get("reference_type"),
                "audio_sha256": hashlib.sha256(audio_path.read_bytes()).hexdigest(),
                "process_lifetime_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
            if args.engine == "mlx":
                row.update(mlx_peak_allocated_bytes=mx.get_peak_memory(), mlx_active_bytes=mx.get_active_memory(), mlx_cache_bytes=mx.get_cache_memory())
            report["runs"].append(row)
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
            print("RUN", json.dumps(row, ensure_ascii=False), flush=True)
    print("RESULT", output, flush=True)

if __name__ == "__main__":
    main()
