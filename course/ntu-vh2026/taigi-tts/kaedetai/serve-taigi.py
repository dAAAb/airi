"""Loopback-only experimental POJ/Tai-lo TTS adapter; not a translation service."""
import asyncio
from contextlib import asynccontextmanager
import importlib.util
import io
import json
import os
import runpy
from pathlib import Path
import shutil
import subprocess
import time
import unicodedata

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
import soundfile as sf

ROOT = Path(__file__).resolve().parent
TRANSLITERATOR = ROOT.parent
PORT, ORIGINS = runpy.run_path(str(ROOT.parent / 'loopback-config.py'))['configuration']()
TAIBUN_PYTHON = Path(os.environ.get('AIRI_TAIBUN_PYTHON', TRANSLITERATOR / '.venv-taibun/bin/python')).expanduser()
TAIBUN_SCRIPT = Path(os.environ.get('AIRI_TAIBUN_SCRIPT', TRANSLITERATOR / 'transliterate.py')).expanduser()
spec = importlib.util.spec_from_file_location('direct_taigi', ROOT / 'direct-taigi.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
engine = None
lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app):
    global engine
    engine = await asyncio.to_thread(module.TaigiEngine, os.environ.get('AIRI_TAIGI_DEVICE', 'cpu'))
    yield


app = FastAPI(title='Experimental KaedeTai Taiwan Hokkien TTS', lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]'])
app.add_middleware(CORSMiddleware,
    allow_origins=ORIGINS, allow_methods=['GET', 'POST'],
    allow_headers=['Content-Type', 'Authorization'],
    expose_headers=['X-Inference-Seconds', 'X-Audio-Seconds'])


@app.middleware('http')
async def check_origin(request: Request, call_next):
    if request.method == 'POST' and request.headers.get('origin') not in (None, *ORIGINS):
        return JSONResponse({'detail': 'Origin is not allowed'}, status_code=403)
    return await call_next(request)


class SpeechRequest(BaseModel):
    input: str = Field(min_length=1, max_length=400)
    model: str = 'kaedetai-taigi'
    voice: str = 'taigi-demo-reference'
    response_format: str = 'mp3'
    speed: float = 1.0


@app.get('/health')
def health():
    return {'ready': engine is not None, 'model': 'KaedeTai/gpt-sovits-tw',
            'language': 'Taiwanese Hokkien', 'input': 'tone-marked POJ/Tai-lo or Taiwanese Han characters',
            'device': str(engine.device) if engine else None,
            'reference': 'author-published synthetic demo', 'streaming': False}


@app.get('/v1/models')
def models():
    return {'object': 'list', 'data': [
        {'id': model, 'object': 'model', 'owned_by': 'KaedeTai + local adapter'}
        for model in ['kaedetai-taigi', 'taigi-hanzi']]}


@app.get('/v1/audio/voices')
def voices():
    return {'voices': ['taigi-demo-reference']}


@app.post('/v1/audio/speech')
async def speech(request: SpeechRequest):
    if request.model not in ['kaedetai-taigi', 'taigi-hanzi'] or request.voice != 'taigi-demo-reference':
        raise HTTPException(422, 'Select kaedetai-taigi or taigi-hanzi, and voice taigi-demo-reference')
    if request.response_format not in ['wav', 'mp3'] or request.speed != 1:
        raise HTTPException(422, 'This experimental adapter supports WAV/MP3 at speed 1 only')
    han_count = sum('CJK' in unicodedata.name(c, '') and 'IDEOGRAPH' in unicodedata.name(c, '') for c in request.input)
    if request.model == 'kaedetai-taigi' and han_count:
        raise HTTPException(422, 'Use tone-marked POJ/Tai-lo; select taigi-hanzi for Taiwanese Han characters')
    if han_count > 60:
        raise HTTPException(422, 'Split this experimental TTS input into utterances of 60 Han characters or fewer')
    if engine is None:
        raise HTTPException(503, 'Model is loading')
    try:
        await asyncio.wait_for(lock.acquire(), timeout=3)
    except TimeoutError:
        raise HTTPException(429, 'TTS is busy; retry after the current utterance finishes')
    try:
        start = time.perf_counter()
        text = request.input
        if request.model == 'taigi-hanzi':
            if not TAIBUN_PYTHON.is_file() or not TAIBUN_SCRIPT.is_file():
                raise HTTPException(503, 'Taibun runtime is missing. Install it or use the POJ model.')
            converted = await asyncio.to_thread(subprocess.run,
                [str(TAIBUN_PYTHON), str(TAIBUN_SCRIPT)],
                input=json.dumps({'text': text}, ensure_ascii=False), text=True,
                capture_output=True, timeout=15)
            try:
                conversion = json.loads(converted.stdout)
            except json.JSONDecodeError:
                raise RuntimeError('Taibun adapter did not return valid JSON')
            if converted.returncode or not conversion.get('ok'):
                raise ValueError(conversion.get('error', 'Taibun conversion failed'))
            text = conversion['poj']
        # The engine rejects any remaining CJK and any unknown G2P token.
        task = asyncio.create_task(asyncio.to_thread(engine.synthesize, text))
        try:
            wav, sample_rate, result = await asyncio.shield(task)
        except asyncio.CancelledError:
            # Keep the mutex while the CPU worker finishes after a disconnect.
            await task
            raise
        buffer = io.BytesIO()
        mp3 = request.response_format == 'mp3'
        sf.write(buffer, wav, sample_rate, format='MP3' if mp3 else 'WAV',
                 subtype='MPEG_LAYER_III' if mp3 else 'PCM_16')
        payload = buffer.getvalue()
        media_type = 'audio/mpeg' if mp3 else 'audio/wav'
        return Response(payload, media_type=media_type, headers={
            'X-Inference-Seconds': f'{time.perf_counter()-start:.3f}',
            'X-Audio-Seconds': f'{result["audio_seconds"]:.3f}',
            'Cache-Control': 'no-store'})
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))
    finally:
        lock.release()


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=PORT, access_log=False)
