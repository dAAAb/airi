"""Loopback OpenAI-compatible ASR26 service for AIRI's microphone provider.

Each request is one audio segment, not a streaming decoder. The model remains in
memory. PyAV decoding and MLX inference happen in worker threads.
"""
import os
from pathlib import Path
import runpy
import tempfile
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.concurrency import run_in_threadpool

MODEL_ID = 'breeze-asr-26-mlx'
MODEL_SOURCE = 'RayyTien/Breeze-ASR-26-mlx-4bit'
ALLOWED_ORIGINS = ('http://127.0.0.1:5174', 'http://localhost:5174', 'http://127.0.0.1:17900')
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_REQUEST_BYTES = MAX_FILE_BYTES + 64 * 1024
MAX_AUDIO_SECONDS = 120
ROOT = Path(__file__).resolve().parent


class RequestSizeLimit:
    """Bound the entire multipart body, including requests without Content-Length."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        length = headers.get(b'content-length')
        if length is not None:
            try:
                too_large = int(length) > MAX_REQUEST_BYTES
            except ValueError:
                too_large = True
            if too_large:
                return await JSONResponse({'detail': 'Audio upload exceeds the 25 MiB limit'}, status_code=413)(scope, receive, send)
        total = 0

        async def bounded_receive():
            nonlocal total
            message = await receive()
            if message['type'] == 'http.request':
                total += len(message.get('body', b''))
                if total > MAX_REQUEST_BYTES:
                    raise HTTPException(413, 'Audio upload exceeds the 25 MiB limit')
            return message

        return await self.app(scope, bounded_receive, send)


def decode_audio_file(path):
    import av
    import numpy as np
    try:
        # PyAV wheels include their codec libraries. A binary input stream
        # avoids depending on a system FFmpeg executable in the Mac app.
        chunks = []
        samples = 0
        deadline = time.monotonic() + 30
        with path.open('rb') as source, av.open(source, options={'protocol_whitelist': 'pipe'}) as container:
            resampler = av.AudioResampler(format='fltp', layout='mono', rate=16000)
            for frame in container.decode(audio=0):
                if time.monotonic() > deadline:
                    raise HTTPException(422, 'Audio decoding timed out')
                for output in resampler.resample(frame):
                    chunk = output.to_ndarray().reshape(-1)
                    samples += len(chunk)
                    if samples > MAX_AUDIO_SECONDS * 16000:
                        raise HTTPException(413, 'Audio must be at most 120 seconds')
                    chunks.append(chunk)
            for output in resampler.resample(None):
                chunks.append(output.to_ndarray().reshape(-1))
        audio = np.concatenate(chunks).astype(np.float32, copy=False) if chunks else np.array([], dtype=np.float32)
    except (av.error.FFmpegError, ValueError, OSError, IndexError):
        raise HTTPException(422, 'Cannot decode this audio. Use a valid WebM, WAV, MP3, or M4A file.') from None
    duration = len(audio) / 16000
    if not len(audio) or not np.isfinite(audio).all():
        raise HTTPException(422, 'Audio is empty or invalid')
    if duration > MAX_AUDIO_SECONDS:
        raise HTTPException(413, 'Audio must be at most 120 seconds')
    return audio, duration


class ASR26Engine:
    def __init__(self):
        self.lock = threading.Lock()
        self.model = None
        self.compatibility = None
        self.load_seconds = None

    def ensure_loaded(self):
        with self.lock:
            self._load()

    def _load(self):
        if self.model is not None:
            return
        for key in ('HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE', 'HF_HUB_DISABLE_TELEMETRY'):
            os.environ[key] = '1'
        os.environ['TOKENIZERS_PARALLELISM'] = 'false'
        import mlx.core as mx
        from mlx_audio.stt.utils import load
        model_dir = Path(os.environ.get('BREEZE_ASR26_MODEL_DIR', ROOT / 'model')).expanduser().resolve(strict=True)
        started = time.perf_counter()
        model = load(str(model_dir), strict=True)
        install = runpy.run_path(str(ROOT / 'whisper-compat.py'))['install_whisper_no_speech_compat']
        self.compatibility = install(model)
        mx.synchronize()
        self.load_seconds = time.perf_counter() - started
        self.model = model

    def transcribe(self, path):
        import mlx.core as mx
        audio, duration = decode_audio_file(path)
        with self.lock:
            self._load()
            started = time.perf_counter()
            result = self.model.generate(audio, language='zh', task='transcribe', temperature=0.0,
                return_timestamps=False, word_timestamps=False, condition_on_previous_text=False, verbose=None)
            mx.synchronize()
            elapsed = time.perf_counter() - started
        return {'text': result.text, 'duration': duration, 'inference_seconds': elapsed}


def create_app(engine=None):
    active_engine = engine or ASR26Engine()

    @asynccontextmanager
    async def lifespan(app):
        await run_in_threadpool(active_engine.ensure_loaded)
        yield

    app = FastAPI(title='Breeze-ASR-26 MLX local transcription', version='1.0.0', lifespan=lifespan)
    app.add_middleware(RequestSizeLimit)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])
    app.add_middleware(CORSMiddleware, allow_origins=list(ALLOWED_ORIGINS),
        allow_methods=['GET', 'POST', 'OPTIONS'], allow_headers=['Content-Type', 'Authorization'],
        expose_headers=['X-Inference-Seconds', 'X-Audio-Seconds', 'X-ASR-Model'])

    @app.middleware('http')
    async def require_local_origin(request: Request, call_next):
        origin = request.headers.get('origin')
        if request.method == 'POST' and origin is not None and origin not in ALLOWED_ORIGINS:
            return JSONResponse({'detail': 'Origin is not allowed'}, status_code=403)
        return await call_next(request)

    @app.get('/health')
    def health():
        return {'status': 'ok', 'model': MODEL_ID, 'source': MODEL_SOURCE, 'provider': 'mlx',
            'mode': 'audio segments, not streaming decoding', 'max_audio_seconds': MAX_AUDIO_SECONDS,
            'tokenizer_compatibility': active_engine.compatibility}

    @app.get('/v1/models')
    def models():
        return {'object': 'list', 'data': [{'id': MODEL_ID, 'object': 'model', 'created': 0,
            'owned_by': 'MediaTek-Research / RayyTien (MLX conversion)'}]}

    @app.post('/v1/audio/transcriptions')
    async def transcribe(file: UploadFile = File(...), model: str = Form(MODEL_ID),
            response_format: str = Form('json'), language: str | None = Form(None),
            temperature: float = Form(0.0)):
        try:
            if model != MODEL_ID:
                raise HTTPException(400, f'Select model {MODEL_ID}')
            if response_format not in ('json', 'text', 'verbose_json'):
                raise HTTPException(400, 'Supported response formats: json, text, verbose_json')
            if language not in (None, '', 'zh', 'zh-TW', 'zh-CN', 'nan'):
                raise HTTPException(400, 'This classroom configuration decodes language zh; use zh for Mandarin or Taigi input')
            if temperature != 0.0:
                raise HTTPException(400, 'This verified classroom configuration requires temperature 0')
            with tempfile.TemporaryDirectory(prefix='airi-asr26-') as temporary:
                path = Path(temporary) / 'audio.bin'
                total = 0
                with path.open('wb') as target:
                    while chunk := await file.read(1024 * 1024):
                        total += len(chunk)
                        if total > MAX_FILE_BYTES:
                            raise HTTPException(413, 'Audio upload exceeds the 25 MiB limit')
                        target.write(chunk)
                if not total:
                    raise HTTPException(422, 'Audio file is empty')
                result = await run_in_threadpool(active_engine.transcribe, path)
            headers = {'X-Inference-Seconds': f'{result["inference_seconds"]:.6f}',
                'X-Audio-Seconds': f'{result["duration"]:.6f}', 'X-ASR-Model': MODEL_ID}
            if response_format == 'text':
                return PlainTextResponse(result['text'], headers=headers)
            if response_format == 'verbose_json':
                return JSONResponse({'task': 'transcribe', 'language': 'chinese',
                    'duration': result['duration'], 'text': result['text']}, headers=headers)
            return JSONResponse({'text': result['text']}, headers=headers)
        finally:
            await file.close()

    return app


app = create_app()
