"""Multipart/CORS/cleanup contract tests without loading weights or Metal."""
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
import server


class FakeEngine:
    compatibility = {'eot_suppressed': False}

    def __init__(self):
        self.last_path = None
        self.fail = False

    def ensure_loaded(self):
        pass

    def transcribe(self, path):
        self.last_path = Path(path)
        assert self.last_path.read_bytes() == b'fake-audio'
        if self.fail:
            raise HTTPException(422, 'Invalid fixture')
        return {'text': '性別平等，從你我做起。', 'duration': 1.5, 'inference_seconds': 0.2}


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.engine = FakeEngine()
        self.client = TestClient(server.create_app(self.engine))

    def request(self, **fields):
        return self.client.post('/v1/audio/transcriptions', data={'model': server.MODEL_ID, **fields}, files={'file': ('recording.webm', b'fake-audio', 'audio/webm')})

    def test_openai_json_and_temp_cleanup(self):
        response = self.request()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'text': '性別平等，從你我做起。'})
        self.assertEqual(response.headers['x-asr-model'], server.MODEL_ID)
        self.assertFalse(self.engine.last_path.exists())

    def test_text_and_verbose_formats(self):
        self.assertEqual(self.request(response_format='text').text, '性別平等，從你我做起。')
        self.assertEqual(self.request(response_format='verbose_json').json()['duration'], 1.5)

    def test_validation(self):
        for fields in [{'model': 'wrong'}, {'language': 'en'}, {'temperature': '0.5'}, {'response_format': 'srt'}]:
            self.assertEqual(self.request(**fields).status_code, 400)

    def test_empty_audio(self):
        response = self.client.post('/v1/audio/transcriptions', files={'file': ('empty.wav', b'', 'audio/wav')})
        self.assertEqual(response.status_code, 422)

    def test_decode_failure_cleans_up(self):
        self.engine.fail = True
        self.assertEqual(self.request().status_code, 422)
        self.assertFalse(self.engine.last_path.exists())

    def test_file_limit(self):
        with patch.object(server, 'MAX_FILE_BYTES', 4):
            self.assertEqual(self.request().status_code, 413)

    def test_multipart_body_limit(self):
        with patch.object(server, 'MAX_REQUEST_BYTES', 4):
            self.assertEqual(self.request().status_code, 413)

    def test_chunked_body_limit(self):
        with patch.object(server, 'MAX_REQUEST_BYTES', 4):
            response = self.client.post('/v1/audio/transcriptions',
                content=iter([b'--boundary\r\n', b'oversized']),
                headers={'Content-Type': 'multipart/form-data; boundary=boundary'})
            self.assertEqual(response.status_code, 413)

    def test_foreign_origin_rejected(self):
        response = self.client.post('/v1/audio/transcriptions', headers={'Origin': 'https://example.org'}, files={'file': ('a.wav', b'fake-audio')})
        self.assertEqual(response.status_code, 403)

    def test_exact_cors(self):
        for origin, allowed in [('http://127.0.0.1:5174', True), ('http://localhost:5174', True), ('https://example.org', False)]:
            response = self.client.options('/v1/audio/transcriptions', headers={'Origin': origin, 'Access-Control-Request-Method': 'POST'})
            self.assertEqual(response.headers.get('access-control-allow-origin') == origin, allowed)

    def test_model_listing(self):
        self.assertEqual(self.client.get('/v1/models').json()['data'][0]['id'], server.MODEL_ID)


if __name__ == '__main__':
    unittest.main()
