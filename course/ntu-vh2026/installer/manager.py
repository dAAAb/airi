"""Loopback-only, allowlisted model installer and process owner for AIRI Local.

The downloadable app supplies runtimes and a built AIRI site. The full app also
supplies the payload. This manager never installs arbitrary commands from HTTP.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
# Load only this bundled sibling, including when QA imports manager.py by path.
_decisions_spec = importlib.util.spec_from_file_location('airi_local_decisions', ROOT / 'decisions.py')
motion_decisions = importlib.util.module_from_spec(_decisions_spec)
_decisions_spec.loader.exec_module(motion_decisions)
COURSE = ROOT.parent
PORT = 17900
ORIGIN = f'http://127.0.0.1:{PORT}'
OLLAMA_URLS = {'bundled': 'http://127.0.0.1:12434', 'existing': 'http://127.0.0.1:11434'}
MODEL_ROWS = [
    {'id': 'qwen', 'title': '輕量意識與視覺 · Qwen 3.5 0.8B', 'bytes': 1322069277,
     'kind': 'ollama', 'model': 'qwen3.5:0.8b',
     'digest': 'de63045f29755d4721c09d54c9b45c2dadb644f4fd7d604d4cac90d96049971c', 'license': 'qwen'},
    {'id': 'sarc-taigi', 'title': '台語意識 · SARC 12B', 'bytes': 7300779224,
     'kind': 'ollama', 'model': 'hf.co/Speech-AI-Research-Center/SARC-Taigi-LLM-12b-GGUF:Q4_K_M',
     'digest': '66544e32e46623d914413577b2b353c853d071612f7304792b817d924554930b', 'license': 'gemma'},
    {'id': 'gemma4', 'title': '中文意識與視覺 · Gemma 4 12B', 'bytes': 7151003754,
     'kind': 'ollama', 'model': 'gemma4:12b-it-qat',
     'digest': '38044be4f923e5a55264ed7df4eaac2676651a905f735197c504045140c02bd3', 'license': 'gemma4'},
    {'id': 'asr26', 'title': '聽覺 · Breeze ASR-26 MLX', 'bytes': 991000000, 'kind': 'files', 'license': 'breeze-asr26'},
    {'id': 'kokoro', 'title': '中文聲音 · Kokoro 82M', 'bytes': 330000000, 'kind': 'files', 'license': 'kokoro'},
    {'id': 'kaedetai', 'title': '台語聲音 · KaedeTai', 'bytes': 1410000000, 'kind': 'files', 'license': 'kaedetai'},
    {'id': 'motiongpt', 'title': '選配動作 · MotionGPT Base（VRM）', 'bytes': 1335831259,
     'kind': 'files', 'license': 'motiongpt', 'optional': True},
]
CATALOG = {row['id']: row for row in MODEL_ROWS}


def request_json(url, data=None, timeout=5):
    payload = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def confined(root, relative):
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Invalid relative path')
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError('Path escapes the payload directory')
    return resolved


def hash_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


class LocalManager:
    def __init__(self, data_dir, resources):
        self.data = data_dir.expanduser().resolve()
        self.resources = resources.resolve()
        self.data.mkdir(parents=True, exist_ok=True)
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.job = {'state': 'idle', 'completed': 0, 'total': 0, 'model': None, 'message': ''}
        self.stop_event = threading.Event()
        self.processes = {}
        self.closing = False
        self.mode = 'bundled'
        self.selected = []
        self.verified = set()
        self.motion_decisions = motion_decisions.MotionDecisionClient()
        config = self.data / 'selection.json'
        if config.exists():
            saved = json.loads(config.read_text())
            self.mode = saved['ollama_mode'] if saved.get('ollama_mode') in OLLAMA_URLS else 'bundled'
            self.selected = [key for key in saved.get('models', []) if key in CATALOG]

    def update(self, **values):
        with self.lock:
            self.job.update(values)

    def manifest(self):
        path = self.resources / 'payload-manifest.json'
        return json.loads(path.read_text()) if path.exists() else {'files': [], 'services': []}

    def payload_path(self, relative):
        # An offline app reads immutable payload in Resources. Downloads live in
        # Application Support and never modify a signed .app bundle.
        if any(item['path'] == relative and item['model'] in self.download_only_models()
               for item in self.manifest().get('files', [])):
            return confined(self.data / 'payload', relative)
        bundled = confined(self.resources / 'payload', relative)
        return bundled if self.manifest().get('offline') or bundled.is_file() else confined(self.data / 'payload', relative)

    def download_only_models(self):
        # Supported packaging policy: optional research weights come directly
        # from the author. Offline speech/LLM payloads never fall back to downloads.
        return set(self.manifest().get('download_only_models', [])) & {'motiongpt'}

    def runtime(self, relative):
        result = confined(self.resources, relative)
        if not result.is_file():
            raise RuntimeError('App runtime is missing. Use a packaged AIRI Local app, not a source-only folder.')
        return result

    def ollama_models(self):
        try:
            return request_json(OLLAMA_URLS[self.mode] + '/api/tags')['models']
        except (OSError, ValueError, KeyError):
            return []

    def available_models(self):
        return [key for key in self.manifest().get('available_models', CATALOG) if key in CATALOG]

    def status(self):
        rows = []
        local = {row['name']: row for row in self.ollama_models()}
        manifest = self.manifest()
        for row in MODEL_ROWS:
            if row['id'] not in self.available_models():
                continue
            entry = dict(row)
            entry['download_only'] = row['id'] in self.download_only_models()
            if row['kind'] == 'ollama':
                try:
                    expected = self.expected_ollama_digests(row)
                    entry['installed'] = local.get(row['model'], {}).get('digest') in expected
                except RuntimeError:
                    entry['installed'] = False
            else:
                files = [item for item in manifest['files'] if item['model'] == row['id']]
                entry['installed'] = bool(files) and all(self.payload_path(item['path']).is_file()
                    and self.payload_path(item['path']).stat().st_size == item['bytes'] for item in files)
            entry['verified'] = row['id'] in self.verified
            rows.append(entry)
        with self.lock:
            job = dict(self.job)
        return {'catalog': rows, 'job': job, 'ollama_mode': self.mode,
                'selected': self.selected, 'offline': manifest.get('offline', False),
                'default_models': manifest.get('default_models', ['qwen', 'asr26', 'kokoro']),
                'available_models': self.available_models(), 'free_bytes': shutil.disk_usage(self.data).free,
                'packaged': (self.resources / 'payload-manifest.json').is_file(),
                'services': {name: process.poll() is None for name, process in list(self.processes.items())}}

    def spawn(self, name, args, env, port):
        with self.lock:
            if self.closing or self.stop_event.is_set():
                raise InterruptedError('AIRI is shutting down or this operation was canceled')
            if name in self.processes and self.processes[name].poll() is None:
                return
            with socket.socket() as probe:
                if probe.connect_ex(('127.0.0.1', port)) == 0:
                    raise RuntimeError(f'Port {port} is already in use. AIRI leaves that process untouched.')
            log_dir = self.data / 'logs'
            log_dir.mkdir(exist_ok=True)
            with (log_dir / f'{name}.log').open('ab') as log:
                self.processes[name] = subprocess.Popen(args, stdin=subprocess.DEVNULL,
                    stdout=log, stderr=log, env=env, cwd=self.resources, start_new_session=True)

    def ensure_ollama(self):
        if self.mode == 'existing':
            request_json(OLLAMA_URLS['existing'] + '/api/version')
            return
        binary = self.runtime('runtimes/ollama/ollama')
        env = dict(os.environ, OLLAMA_HOST='127.0.0.1:12434',
                   OLLAMA_MODELS=str(self.data / 'ollama'), OLLAMA_NO_CLOUD='1',
                   OLLAMA_ORIGINS=ORIGIN, OLLAMA_MAX_LOADED_MODELS='1',
                   OLLAMA_NUM_PARALLEL='1', OLLAMA_CONTEXT_LENGTH='4096')
        # Full packs supply a separate verified model store. Never write into or
        # share the user's ~/.ollama directory with the app-owned process.
        bundled_models = self.resources / 'payload/ollama'
        if bundled_models.is_dir():
            env['OLLAMA_MODELS'] = str(bundled_models)
        self.spawn('ollama', [str(binary), 'serve'], env, 12434)
        for _ in range(100):
            if self.processes['ollama'].poll() is not None:
                raise RuntimeError('Bundled Ollama stopped. See the local ollama log.')
            try:
                request_json(OLLAMA_URLS['bundled'] + '/api/version', timeout=1)
                return
            except OSError:
                time.sleep(.2)
        raise RuntimeError('Bundled Ollama did not become ready')

    def start_job(self, body):
        keys, mode = body.get('models'), body.get('ollama_mode', 'bundled')
        if not isinstance(keys, list) or not keys or any(not isinstance(key, str) or key not in self.available_models() for key in keys):
            raise ValueError('Choose known models')
        if mode not in OLLAMA_URLS:
            raise ValueError('Unknown Ollama mode')
        accepted = body.get('accepted_licenses', [])
        if not isinstance(accepted, list) or ('sarc-taigi' in keys and 'gemma' not in accepted):
            raise ValueError('Review and accept the licenses for the selected models')
        with self.lock:
            if self.closing or self.job['state'] in ('installing', 'starting'):
                raise RuntimeError('Another operation is already running')
            self.job = {'state': 'installing', 'completed': 0, 'total': 0, 'model': None, 'message': ''}
        self.mode, self.selected = mode, list(dict.fromkeys(keys))
        self.stop_event.clear()
        threading.Thread(target=self.install, daemon=True).start()

    def install(self):
        try:
            if any(CATALOG[key]['kind'] == 'ollama' for key in self.selected):
                self.ensure_ollama()
            files = self.manifest()['files']
            for key in self.selected:
                if self.stop_event.is_set():
                    raise InterruptedError('Download canceled. Verified files are retained.')
                row = CATALOG[key]
                self.update(model=key, completed=0, total=row['bytes'], message='檢查檔案')
                if row['kind'] == 'ollama':
                    self.install_ollama(row)
                else:
                    group = [item for item in files if item['model'] == key]
                    if not group:
                        raise RuntimeError(f'The package has no fixed download manifest for {key}')
                    for item in group:
                        self.install_file(item)
                self.verified.add(key)
            (self.data / 'selection.json').write_text(json.dumps({'models': self.selected, 'ollama_mode': self.mode}))
            self.update(state='ready', message='所選模型已驗證完成')
        except InterruptedError as error:
            self.update(state='canceled', message=str(error))
        except Exception as error:
            self.update(state='error', message=str(error))

    def ollama_record(self, row):
        records = {item['id']: item for item in self.manifest().get('ollama_models', [])}
        record = records.get(row['id'])
        if not record or record.get('ollama_model_digest') != row['digest']:
            raise RuntimeError('Offline model verification metadata is missing. Reinstall this release.')
        digest = record.get('manifest_sha256', '')
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise RuntimeError('Ollama manifest verification metadata is invalid. Reinstall this release.')
        return record

    def expected_ollama_digests(self, row):
        # The packaged 0.35.1 runtime reports the raw manifest SHA. The tested
        # external 0.40 runtime reports its model digest, which differs for some
        # models. External Ollama may use either version: both representations
        # must come from this release's pinned record, never from the API itself.
        # Our fixed private runtime accepts only the raw manifest SHA, and its
        # app-owned model store must also pass full manifest/blob file hashing.
        manifest_digest = self.ollama_record(row)['manifest_sha256']
        return {row['digest'], manifest_digest} if self.mode == 'existing' else {manifest_digest}

    def verify_ollama_store(self, row, root):
        record = self.ollama_record(row)
        path = confined(root / 'manifests', record['path'])
        if not path.is_file() or hash_file(path) != record['manifest_sha256']:
            raise RuntimeError('Offline Ollama manifest is damaged. Reinstall this release.')
        model = json.loads(path.read_text())
        total = 0
        for item in [model['config'], *model['layers']]:
            identifier = item['digest']
            expected = identifier.removeprefix('sha256:')
            if not identifier.startswith('sha256:') or len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
                raise RuntimeError('Offline Ollama blob identifier is invalid.')
            blob = confined(root / 'blobs', 'sha256-' + expected)
            if not blob.is_file() or blob.stat().st_size != item['size'] or hash_file(blob) != expected:
                raise RuntimeError('Offline Ollama model is damaged. Reinstall this release.')
            total += item['size']
            self.update(completed=total, message='驗證離線模型')

    def verify_bundled_ollama(self, row):
        self.verify_ollama_store(row, self.resources / 'payload/ollama')

    def install_ollama(self, row):
        offline = self.manifest().get('offline', False)
        if offline:
            self.verify_bundled_ollama(row)
        expected = self.expected_ollama_digests(row)
        if any(item.get('name') == row['model'] and item.get('digest') in expected for item in self.ollama_models()):
            if self.mode == 'bundled' and not offline:
                self.verify_ollama_store(row, self.data / 'ollama')
            return
        if (self.resources / 'payload/ollama').is_dir():
            raise RuntimeError('Offline model payload does not match its manifest. Reinstall this release.')
        if shutil.disk_usage(self.data).free < row['bytes'] + 1024 ** 3:
            raise RuntimeError('Not enough free disk space for this model')
        req = urllib.request.Request(OLLAMA_URLS[self.mode] + '/api/pull',
            data=json.dumps({'model': row['model'], 'stream': True}).encode(),
            headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=60) as response:
            for line in response:
                if self.stop_event.is_set():
                    raise InterruptedError('Download canceled')
                event = json.loads(line)
                if event.get('error'):
                    raise RuntimeError(event['error'])
                self.update(completed=event.get('completed', 0), total=event.get('total', row['bytes']),
                            message=event.get('status', '下載中'))
        if not any(item.get('name') == row['model'] and item.get('digest') in expected for item in self.ollama_models()):
            raise RuntimeError('Downloaded model differs from the tested release. It was not marked ready.')
        if self.mode == 'bundled':
            self.verify_ollama_store(row, self.data / 'ollama')

    def install_file(self, item):
        target = self.payload_path(item['path'])
        if target.is_file() and target.stat().st_size == item['bytes'] and hash_file(target) == item['sha256']:
            return
        if self.manifest().get('offline') and item['model'] not in self.download_only_models():
            raise RuntimeError('Offline model file is missing or damaged. Reinstall this release.')
        target = confined(self.data / 'payload', item['path'])
        target.parent.mkdir(parents=True, exist_ok=True)
        url = item['url']
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname not in ('huggingface.co', 'raw.githubusercontent.com', 'github.com'):
            raise ValueError('Download source is not allowlisted')
        if shutil.disk_usage(self.data).free < item['bytes'] + 512 * 1024 ** 2:
            raise RuntimeError('Not enough free disk space for this file')
        partial = target.with_name(target.name + '.partial')
        digest = hashlib.sha256()
        total = 0
        try:
            with urllib.request.urlopen(url, timeout=60) as response, partial.open('wb') as output:
                while True:
                    if self.stop_event.is_set():
                        raise InterruptedError('Download canceled')
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    total += len(block)
                    if total > item['bytes']:
                        raise ValueError('Download exceeds the recorded size')
                    output.write(block)
                    digest.update(block)
                    self.update(completed=total, total=item['bytes'], message='下載並驗證檔案')
            if total != item['bytes'] or digest.hexdigest() != item['sha256']:
                raise ValueError('File checksum does not match the release')
            partial.replace(target)
        finally:
            partial.unlink(missing_ok=True)

    def start_services(self):
        if not self.selected or self.job['state'] != 'ready' or not set(self.selected).issubset(self.verified):
            raise RuntimeError('Verify the selected models before starting AIRI')
        self.update(state='starting', message='啟動本機推論服務')
        threading.Thread(target=self._start_services, daemon=True).start()
        return {'accepted': True}

    def _start_services(self):
        try:
            self._launch_services()
            self.update(state='running', message='本機服務已就緒', url=ORIGIN + '/?localSetup=1')
        except Exception as error:
            self.update(state='error', message=str(error))

    def _launch_services(self):
        if any(CATALOG[key]['kind'] == 'ollama' for key in self.selected):
            self.ensure_ollama()
        # These commands come from the packaged, fixed build manifest. HTTP cannot
        # supply paths, command names, environment entries, ports, or download URLs.
        manifest = self.manifest()
        services = manifest.get('services', [])
        for key in self.selected:
            if CATALOG[key]['kind'] == 'files' and not any(key in row['requires'] for row in services):
                raise RuntimeError(f'App has no runtime service for {key}')
        for service in services:
            if self.stop_event.is_set():
                raise InterruptedError('Startup canceled')
            if not set(service['requires']).issubset(self.selected):
                continue
            env = dict(os.environ, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                       HF_HUB_DISABLE_TELEMETRY='1', TOKENIZERS_PARALLELISM='false')
            payload = self.resources / 'payload' if manifest.get('offline') else self.data / 'payload'
            if set(service['requires']) & self.download_only_models():
                if not set(service['requires']).issubset(self.download_only_models()):
                    raise RuntimeError('A service cannot mix bundled and separately downloaded payload roots')
                payload = self.data / 'payload'
            for key, value in service['env'].items():
                env[key] = value.replace('{payload}', str(payload)).replace('{resources}', str(self.resources))
            args = [str(self.runtime(service['executable']))] + [arg.replace('{resources}', str(self.resources)) for arg in service['args']]
            self.spawn(service['id'], args, env, service['port'])
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if self.stop_event.is_set():
                    raise InterruptedError('Startup canceled')
                if self.processes[service['id']].poll() is not None:
                    raise RuntimeError(f'{service["id"]} stopped during startup. See its local log.')
                try:
                    request_json(f'http://127.0.0.1:{service["port"]}' + service['health'], timeout=2)
                    break
                except (OSError, ValueError):
                    time.sleep(.25)
            else:
                raise RuntimeError(f'{service["id"]} startup timed out')

    def close(self):
        with self.lock:
            self.closing = True
            self.stop_event.set()
            owned = list(self.processes.values())
        # Every child starts its own session. Include its engine runners without
        # finding or signaling the user's pre-existing processes by port or name.
        for process in owned:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        for process in owned:
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=3)


def make_handler(manager):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def send_data(self, status, data, content_type='application/json'):
            # Static JSON files already contain encoded bytes. Only API objects
            # need serialization, regardless of the shared JSON MIME type.
            if content_type == 'application/json' and not isinstance(data, (bytes, bytearray)):
                raw = json.dumps(data, ensure_ascii=False).encode()
            else:
                raw = data
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "frame-ancestors 'self'")
            self.end_headers()
            self.wfile.write(raw)

        def valid_host(self):
            return self.headers.get('Host') == f'127.0.0.1:{PORT}'

        def do_GET(self):
            if not self.valid_host():
                return self.send_data(403, {'error': 'Invalid host'})
            path = urlsplit(self.path).path
            if path in ('/api/status', '/api/jobs'):
                return self.send_data(200, manager.status())
            if path == '/api/bootstrap':
                return self.send_data(200, {'token': manager.token, 'origin': ORIGIN})
            if path == '/api/airi-config':
                return self.send_data(200, {'models': manager.selected, 'ollama': OLLAMA_URLS[manager.mode] + '/v1/',
                    'asr': 'http://127.0.0.1:18001/v1/', 'speech': 'http://127.0.0.1:18884/v1/',
                    'motion': 'http://127.0.0.1:17905' if 'motiongpt' in manager.selected else None})
            if path.startswith('/licenses/'):
                root = manager.resources / 'licenses'
                relative = path.removeprefix('/licenses/')
            else:
                root = ROOT / 'web' if path.startswith('/setup') else manager.resources / 'web'
                relative = path.removeprefix('/setup').lstrip('/') if path.startswith('/setup') else path.lstrip('/')
            try:
                target = confined(root, relative or 'index.html')
                if not target.is_file() and not Path(relative).suffix:
                    target = root / 'index.html'
                if not target.is_file():
                    return self.send_data(404, {'error': 'Built web app is not present in this source folder'})
                import mimetypes
                return self.send_data(200, target.read_bytes(), mimetypes.guess_type(str(target))[0] or 'application/octet-stream')
            except ValueError:
                return self.send_data(400, {'error': 'Invalid path'})

        def do_POST(self):
            if not self.valid_host() or self.headers.get('Origin') != ORIGIN or not secrets.compare_digest(self.headers.get('X-AIRI-Setup-Token', ''), manager.token):
                return self.send_data(403, {'error': 'Invalid local setup session'})
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.send_data(415, {'error': 'JSON required'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length < 2 or length > 16384:
                    return self.send_data(413, {'error': 'Request too large or empty'})
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError('JSON object required')
                path = urlsplit(self.path).path
                if path == '/api/motion-decision':
                    return self.send_data(200, manager.motion_decisions.decide(body))
                if path == '/api/install':
                    manager.start_job(body)
                    return self.send_data(202, {'accepted': True})
                if path == '/api/cancel':
                    manager.stop_event.set()
                    return self.send_data(202, {'accepted': True})
                if path == '/api/start':
                    return self.send_data(202, manager.start_services())
                return self.send_data(404, {'error': 'Unknown action'})
            except motion_decisions.DecisionError as error:
                return self.send_data(error.status, {'error': str(error), 'code': error.code})
            except (ValueError, KeyError, RuntimeError, OSError) as error:
                return self.send_data(400, {'error': str(error)})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path.home() / 'Library/Application Support/AIRI Local')
    parser.add_argument('--resources', type=Path, default=ROOT / 'resources')
    args = parser.parse_args()
    manager = LocalManager(args.data_dir, args.resources)
    server = ThreadingHTTPServer(('127.0.0.1', PORT), make_handler(manager))
    def terminate(_signal, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, terminate)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        manager.close()


if __name__ == '__main__':
    main()
