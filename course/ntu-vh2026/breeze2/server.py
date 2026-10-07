"""Loopback-only Breeze2 VITS service with an OpenAI-style speech endpoint.

The official lexicon has no Latin words/digits. Reject those requests explicitly
instead of silently dropping them, as the native engine otherwise does.
"""
import io
import shutil
import re
import subprocess
import threading
import time
from pathlib import Path

import soundfile as sf
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from engine import create_tts

ROOT = Path(__file__).resolve().parent
MODEL = "breeze2-vits"
VOICE = "breeze2-zh-tw"
tts = None

def get_tts():
    global tts
    if tts is None:
        tts = create_tts()
    return tts
lock = threading.Lock()
app = FastAPI(title="Breeze2 VITS 本機語音", version="1.0.0")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
app.add_middleware(CORSMiddleware,
    allow_origins=["http://127.0.0.1:5174", "http://localhost:5174", "http://127.0.0.1:8881", "http://localhost:8881"],
    allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type", "Authorization"],
    expose_headers=["X-Synthesis-Seconds", "X-Audio-Seconds", "X-TTS-Model"])

class SpeechRequest(BaseModel):
    model: str = MODEL
    input: str = Field(min_length=1, max_length=1000)
    voice: str = VOICE
    response_format: str = "wav"
    speed: float = Field(default=1.0, ge=0.5, le=2.0)

@app.middleware("http")
async def require_local_origin(request: Request, call_next):
    origin = request.headers.get("origin")
    allowed = {"http://127.0.0.1:5174", "http://localhost:5174", "http://127.0.0.1:8881", "http://localhost:8881"}
    if request.method == "POST" and origin is not None and origin not in allowed:
        return Response("Origin is not allowed", status_code=403)
    return await call_next(request)

@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL, "engine": "sherpa-onnx", "provider": "cpu", "sample_rate": get_tts().sample_rate,
            "scope": "Traditional Chinese text; single voice; no English or digits in the stock lexicon"}

@app.get("/v1/models")
def models():
    return {"object": "list", "data": [{"id": MODEL, "object": "model", "created": 0, "owned_by": "MediaTek-Research"}]}

@app.get("/v1/audio/voices")
def voices():
    return {"voices": [VOICE]}

@app.get("/v1/voices")
def voice_objects():
    return {"voices": [{"id": VOICE, "name": "Breeze2 台灣華語", "languages": [{"code": "zh-TW", "title": "繁體中文"}]}]}

@app.post("/v1/audio/speech")
def speak(request: SpeechRequest):
    if request.model != MODEL:
        raise HTTPException(400, "請選擇模型 breeze2-vits")
    if request.voice not in (VOICE, "alloy"):
        raise HTTPException(400, "本模型只有一個聲線，請選 breeze2-zh-tw（alloy 為相容別名）")
    unsupported = list(dict.fromkeys(re.findall(r"[A-Za-z0-9]+", request.input)))
    if unsupported:
        raise HTTPException(422, {"message": "原版字典沒有英文詞與阿拉伯數字，會漏讀。請先改為中文文字再合成。", "unsupported": unsupported})
    if request.response_format not in ("wav", "mp3", "pcm", "flac"):
        raise HTTPException(400, "支援 wav、mp3、pcm、flac")
    started = time.perf_counter()
    with lock:
        generated = get_tts().generate(request.input, sid=0, speed=request.speed)
    if len(generated.samples) == 0:
        raise HTTPException(422, "沒有可合成的文字")
    synthesis_seconds = time.perf_counter() - started
    duration = len(generated.samples) / generated.sample_rate
    buf = io.BytesIO()
    sf.write(buf, generated.samples, generated.sample_rate, format="WAV", subtype="PCM_16")
    data, media_type = buf.getvalue(), "audio/wav"
    if request.response_format == "flac":
        buf = io.BytesIO()
        sf.write(buf, generated.samples, generated.sample_rate, format="FLAC")
        data, media_type = buf.getvalue(), "audio/flac"
    elif request.response_format in ("mp3", "pcm"):
        fmt = request.response_format
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise HTTPException(503, "此音訊格式需要本機 ffmpeg；請改用 wav")
        options = ["-f", "mp3"] if fmt == "mp3" else ["-ar", "24000", "-f", "s16le", "-acodec", "pcm_s16le"]
        encoded = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-i", "pipe:0", *options, "pipe:1"], input=data, capture_output=True, timeout=30)
        if encoded.returncode:
            raise HTTPException(500, "音訊格式轉換失敗")
        data, media_type = encoded.stdout, "audio/mpeg" if fmt == "mp3" else "application/octet-stream"
    print(f"speech chars={len(request.input)} seconds={synthesis_seconds:.3f} audio={duration:.3f} format={request.response_format}", flush=True)
    return Response(data, media_type=media_type, headers={"X-Synthesis-Seconds": f"{synthesis_seconds:.6f}", "X-Audio-Seconds": f"{duration:.6f}", "X-TTS-Model": MODEL})

@app.get("/", response_class=HTMLResponse)
def index():
    return "<h1>Breeze2 Taiwan Mandarin TTS</h1><p>Local classroom service. See README.zh-TW.md.</p>"
