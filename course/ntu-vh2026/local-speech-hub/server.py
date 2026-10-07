"""Fixed loopback speech routes for two AIRI character cards.

No input or generated audio is written to disk. Errors never trigger a fallback
between languages. Upstream redirects are returned without being followed.
"""
import asyncio
from datetime import datetime, timezone
import json
import logging
import os
import time
from typing import Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, Response

ORIGINS = ('http://127.0.0.1:5174', 'http://localhost:5174', 'http://127.0.0.1:17900')
MAX_BODY = 4096
DESKTOP_MODE = os.environ.get('AIRI_DESKTOP_MODE') == '1'
ROUTES = {
    'kokoro': (f'http://127.0.0.1:{18880 if DESKTOP_MODE else 8880}/v1/audio/speech', 'zf_xiaobei'),
    'taigi-hanzi': (f'http://127.0.0.1:{18883 if DESKTOP_MODE else 8883}/v1/audio/speech', 'taigi-demo-reference'),
}
ALLOWED_FIELDS = {'model', 'input', 'voice', 'response_format', 'speed'}
completion_logger = logging.getLogger('local-speech-hub.completion')
completion_logger.setLevel(logging.INFO)
completion_logger.propagate = False
if not completion_logger.handlers:
    completion_logger.addHandler(logging.StreamHandler())


def create_app(upstream_transport: Optional[httpx.AsyncBaseTransport] = None):
    app = FastAPI(title='Local classroom speech hub', docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost'])
    app.add_middleware(CORSMiddleware, allow_origins=list(ORIGINS),
        allow_methods=['GET', 'POST', 'OPTIONS'], allow_headers=['Content-Type', 'Authorization'],
        expose_headers=['X-Audio-Seconds', 'X-Inference-Seconds', 'X-Synthesis-Seconds', 'X-Speech-Hub-Model'])

    @app.middleware('http')
    async def local_origin(request: Request, call_next):
        if request.method == 'POST' and request.headers.get('origin') not in (None, *ORIGINS):
            return JSONResponse({'detail': 'Origin is not allowed'}, status_code=403)
        return await call_next(request)

    @app.get('/health')
    async def health():
        return {'status': 'ok', 'models': list(ROUTES), 'scope': 'Fixed local routing; this is not a backend readiness check'}

    @app.get('/v1/models')
    async def models():
        return {'object': 'list', 'data': [
            {'id': model, 'object': 'model', 'created': 0, 'owned_by': 'local-classroom'} for model in ROUTES]}

    @app.get('/v1/audio/voices')
    async def voices():
        return {'voices': [voice for _, voice in ROUTES.values()]}

    @app.get('/v1/voices')
    async def voice_details():
        return {'voices': [
            {'id': 'zf_xiaobei', 'name': 'Kokoro 中文', 'languages': [{'code': 'zh', 'title': '中文'}]},
            {'id': 'taigi-demo-reference', 'name': 'KaedeTai 台語', 'languages': [{'code': 'nan', 'title': '台語'}]},
        ]}

    @app.post('/v1/audio/speech')
    async def speech(request: Request):
        started = time.perf_counter()
        if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
            return JSONResponse({'detail': 'Send application/json'}, status_code=415)
        length = request.headers.get('content-length')
        if length is not None:
            try:
                declared = int(length)
            except ValueError:
                return JSONResponse({'detail': 'Invalid Content-Length'}, status_code=400)
            if declared < 0 or declared > MAX_BODY:
                return JSONResponse({'detail': 'Speech JSON is limited to 4096 bytes'}, status_code=413)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_BODY:
                return JSONResponse({'detail': 'Speech JSON is limited to 4096 bytes'}, status_code=413)
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeError):
            return JSONResponse({'detail': 'Invalid JSON'}, status_code=400)
        if not isinstance(payload, dict):
            return JSONResponse({'detail': 'JSON object required'}, status_code=400)
        if set(payload) - ALLOWED_FIELDS:
            return JSONResponse({'detail': 'Only model, input, voice, response_format, and speed are accepted'}, status_code=400)
        model = payload.get('model')
        if not isinstance(model, str) or model not in ROUTES:
            return JSONResponse({'detail': 'Select model kokoro or taigi-hanzi'}, status_code=400)
        url, voice = ROUTES[model]
        if payload.get('voice') != voice:
            return JSONResponse({'detail': f'Model {model} requires voice {voice}'}, status_code=400)
        if not isinstance(payload.get('input'), str) or not payload['input'].strip():
            return JSONResponse({'detail': 'Non-empty input text is required'}, status_code=400)

        def completion(status, size):
            # Only allowlisted IDs and numeric completion metadata are logged.
            # Never log the payload, utterance, response body, IP, or headers.
            completion_logger.info(json.dumps({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'route': '/v1/audio/speech', 'model': model, 'voice': voice,
                'status': status, 'duration_ms': round((time.perf_counter() - started) * 1000),
                'bytes': size,
            }, separators=(',', ':')))

        try:
            async with asyncio.timeout(60):
                async with httpx.AsyncClient(transport=upstream_transport, trust_env=False,
                        follow_redirects=False, timeout=httpx.Timeout(60, connect=5)) as client:
                    upstream = await client.post(url, content=bytes(body), headers={'Content-Type': 'application/json'})
        except (TimeoutError, httpx.TimeoutException):
            response = JSONResponse({'detail': f'Local speech service timed out for {model}'}, status_code=504)
            completion(504, len(response.body))
            return response
        except httpx.RequestError:
            response = JSONResponse({'detail': f'Local speech service is unavailable for {model}'}, status_code=502)
            completion(502, len(response.body))
            return response
        # Preserve the backend's status and body, including its error messages.
        headers = {'Content-Type': upstream.headers.get('content-type', 'application/octet-stream'),
            'Cache-Control': 'no-store', 'X-Speech-Hub-Model': model}
        for header in ('X-Audio-Seconds', 'X-Inference-Seconds', 'X-Synthesis-Seconds'):
            if header in upstream.headers:
                headers[header] = upstream.headers[header]
        completion(upstream.status_code, len(upstream.content))
        return Response(upstream.content, status_code=upstream.status_code, headers=headers)

    return app


app = create_app()
