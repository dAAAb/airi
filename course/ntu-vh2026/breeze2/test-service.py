"""Contract tests without weights. The fake engine validates routing, not speech."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
import server


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)
        self.payload = {'input': '歡迎來到臺灣。', 'model': 'breeze2-vits', 'voice': 'breeze2-zh-tw'}

    def test_english_and_digits_are_explicit_errors(self):
        for text in ['AI 模型', '課程 2026']:
            response = self.client.post('/v1/audio/speech', json={**self.payload, 'input': text})
            self.assertEqual(response.status_code, 422)
            self.assertTrue(response.json()['detail']['unsupported'])

    def test_wrong_provider_and_format_fail(self):
        for update in [{'model': 'other'}, {'voice': 'other'}, {'response_format': 'ogg'}]:
            self.assertEqual(self.client.post('/v1/audio/speech', json={**self.payload, **update}).status_code, 400)

    def test_foreign_origin_cannot_trigger_synthesis(self):
        response = self.client.post('/v1/audio/speech', json=self.payload, headers={'Origin': 'https://example.org'})
        self.assertEqual(response.status_code, 403)

    def test_cors_exact_origin(self):
        for origin, allowed in [('http://127.0.0.1:5174', True), ('https://example.org', False)]:
            response = self.client.options('/v1/audio/speech', headers={'Origin': origin, 'Access-Control-Request-Method': 'POST'})
            self.assertEqual(response.headers.get('access-control-allow-origin') == origin, allowed)

    def test_wav_response(self):
        fake = SimpleNamespace(generate=lambda *args, **kwargs: SimpleNamespace(samples=[0.0] * 2205, sample_rate=22050))
        with patch.object(server, 'get_tts', return_value=fake):
            response = self.client.post('/v1/audio/speech', json=self.payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content[:4], b'RIFF')
        self.assertEqual(response.headers['x-audio-seconds'], '0.100000')


if __name__ == '__main__':
    unittest.main()
