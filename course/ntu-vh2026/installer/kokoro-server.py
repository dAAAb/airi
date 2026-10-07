"""Small offline Chinese Kokoro adapter. No FastAPI application checkout needed."""
import asyncio
from contextlib import asynccontextmanager
import io
import os
from pathlib import Path
import threading
import time

for key in ('HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE', 'HF_HUB_DISABLE_TELEMETRY'):
    os.environ[key] = '1'

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
import numpy as np
import soundfile as sf
import torch
from kokoro import KModel, KPipeline

MODEL_DIR = Path(os.environ['AIRI_KOKORO_MODELS_DIR']).resolve()
lock = threading.Lock()
pipeline = None


@asynccontextmanager
async def lifespan(app):
    global pipeline
    torch.set_num_threads(4)
    model = KModel(repo_id='hexgrad/Kokoro-82M', config=str(MODEL_DIR/'config.json'),
                   model=str(MODEL_DIR/'kokoro-v1_0.pth')).to('cpu').eval()
    pipeline = KPipeline(lang_code='z', repo_id='hexgrad/Kokoro-82M', model=model, device='cpu')
    yield


app = FastAPI(lifespan=lifespan)


class Speech(BaseModel):
    input: str = Field(min_length=1, max_length=400)
    model: str = 'kokoro'
    voice: str = 'zf_xiaobei'
    response_format: str = 'mp3'
    speed: float = Field(default=1.0, ge=.5, le=2.0)


@app.get('/health')
def health():
    return {'ready': pipeline is not None, 'model': 'kokoro', 'language': 'Mandarin Chinese'}


@app.get('/v1/models')
def models():
    return {'data': [{'id': 'kokoro', 'owned_by': 'kokoro', 'object': 'model'}], 'object': 'list'}


def generate(request):
    started = time.perf_counter()
    with lock, torch.inference_mode():
        chunks = [audio.cpu().numpy() for _, _, audio in pipeline(request.input,
            voice=str(MODEL_DIR/'voices/zf_xiaobei.pt'), speed=request.speed) if audio is not None]
    if not chunks:
        raise RuntimeError('No speech was generated')
    audio = np.concatenate(chunks)
    if not audio.size or not np.isfinite(audio).all():
        raise RuntimeError('Invalid audio')
    buffer = io.BytesIO()
    if request.response_format == 'pcm':
        payload = (np.clip(audio, -1, 1)*32767).astype('<i2').tobytes()
        mime = 'application/octet-stream'
    else:
        mp3 = request.response_format == 'mp3'
        sf.write(buffer, audio, 24000, format='MP3' if mp3 else 'WAV',
                 subtype='MPEG_LAYER_III' if mp3 else 'PCM_16')
        payload, mime = buffer.getvalue(), 'audio/mpeg' if mp3 else 'audio/wav'
    return Response(payload, media_type=mime, headers={'Cache-Control': 'no-store',
        'X-Audio-Seconds': str(len(audio)/24000),
        'X-Inference-Seconds': str(time.perf_counter()-started)})


@app.post('/v1/audio/speech')
async def speech(request: Speech):
    if request.model != 'kokoro' or request.voice != 'zf_xiaobei':
        raise HTTPException(422, 'Use model kokoro and voice zf_xiaobei')
    if request.response_format not in ('wav', 'mp3', 'pcm'):
        raise HTTPException(422, 'Use wav, mp3 or pcm')
    if pipeline is None:
        raise HTTPException(503, 'Kokoro is loading')
    return await asyncio.to_thread(generate, request)


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=int(os.environ.get('AIRI_KOKORO_PORT', '18880')), access_log=False)
