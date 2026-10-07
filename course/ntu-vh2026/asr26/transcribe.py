"""Offline Breeze-ASR-26 MLX file transcription with the verified token fix."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY"):
    os.environ[key] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import numpy as np
import mlx.core as mx
from mlx_audio.stt.utils import load
import runpy
compat = runpy.run_path(str(Path(__file__).with_name("whisper-compat.py")))
install_whisper_no_speech_compat = compat["install_whisper_no_speech_compat"]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path)
    parser.add_argument("--model-dir", type=Path, default=Path(__file__).resolve().parent / "model")
    parser.add_argument("--json", action="store_true", help="Print text and timing metadata as JSON")
    args = parser.parse_args()
    path = args.audio.expanduser().resolve(strict=True)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("Install ffmpeg and add it to PATH")
    raw = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(path),
        "-ac", "1", "-ar", "16000", "-f", "f32le", "pipe:1"],
        check=True, capture_output=True).stdout
    audio = np.frombuffer(raw, dtype="<f4").copy()
    if not len(audio) or not np.isfinite(audio).all():
        raise ValueError("Audio must be non-empty and contain finite samples")
    started = time.perf_counter()
    model = load(str(args.model_dir.expanduser().resolve(strict=True)), strict=True)
    compatibility = install_whisper_no_speech_compat(model)
    mx.synchronize()
    load_seconds = time.perf_counter() - started
    started = time.perf_counter()
    result = model.generate(audio, language="zh", task="transcribe", temperature=0.0,
        return_timestamps=False, word_timestamps=False, condition_on_previous_text=False, verbose=None)
    mx.synchronize()
    elapsed = time.perf_counter() - started
    report = {"text": result.text, "audio_seconds": len(audio) / 16000,
        "inference_seconds": elapsed, "load_seconds": load_seconds,
        "device": str(mx.default_device()), "model": "RayyTien/Breeze-ASR-26-mlx-4bit",
        "tokenizer_compatibility": compatibility,
        "note": "Taigi to Mandarin characters; English words may not be preserved. Offline inference; no upload."}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(result.text)
        print(f"Audio {report['audio_seconds']:.2f}s; inference {elapsed:.3f}s; model load {load_seconds:.3f}s", file=sys.stderr)

if __name__ == "__main__":
    main()
