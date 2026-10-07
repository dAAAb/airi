"""Fixed-route API contracts without contacting speech backends."""
import json
import unittest

import httpx
from fastapi.testclient import TestClient
from server import create_app


class HubTests(unittest.TestCase):
    def setUp(self):
        self.requests=[]
        self.upstream_status=200
        self.upstream_body=b'RIFFexample-audio'
        self.upstream_type='audio/wav'
        self.failure=None
        async def upstream(request):
            self.requests.append(request)
            if self.failure:raise self.failure
            return httpx.Response(self.upstream_status,content=self.upstream_body,headers={'Content-Type':self.upstream_type,'X-Audio-Seconds':'1.2'},request=request)
        self.client=TestClient(create_app(httpx.MockTransport(upstream)),base_url='http://127.0.0.1:8884')

    def payload(self,model='kokoro'):
        return {'model':model,'voice':'zf_xiaobei' if model=='kokoro' else 'taigi-demo-reference','input':'你好。','response_format':'wav'}

    def test_fixed_routes_and_voice_preserved(self):
        for model,port in [('kokoro',8880),('taigi-hanzi',8883)]:
            payload=self.payload(model)
            response=self.client.post('/v1/audio/speech',json=payload)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.content,self.upstream_body)
            self.assertEqual(response.headers['content-type'],'audio/wav')
            self.assertEqual(str(self.requests[-1].url),f'http://127.0.0.1:{port}/v1/audio/speech')
            self.assertEqual(json.loads(self.requests[-1].content),payload)

    def test_upstream_error_is_unchanged_and_never_falls_back(self):
        self.upstream_status=422
        self.upstream_body=b'{"detail":"unsupported syllable"}'
        self.upstream_type='application/json'
        response=self.client.post('/v1/audio/speech',json=self.payload('taigi-hanzi'))
        self.assertEqual(response.status_code,422)
        self.assertEqual(response.content,self.upstream_body)
        self.assertEqual(len(self.requests),1)
        self.assertEqual(self.requests[0].url.port,8883)

    def test_no_arbitrary_destination_or_fields(self):
        for payload in [{**self.payload(),'model':'http://example.org/'},{**self.payload(),'url':'http://example.org/'}]:
            self.assertEqual(self.client.post('/v1/audio/speech',json=payload).status_code,400)
        self.assertEqual(self.requests,[])

    def test_wrong_voice_rejected(self):
        payload={**self.payload(),'voice':'taigi-demo-reference'}
        self.assertEqual(self.client.post('/v1/audio/speech',json=payload).status_code,400)
        self.assertEqual(self.requests,[])

    def test_max_body_content_length(self):
        self.assertEqual(self.client.post('/v1/audio/speech',content=b'x'*4097,headers={'Content-Type':'application/json'}).status_code,413)
        self.assertEqual(self.requests,[])

    def test_max_body_chunked(self):
        self.assertEqual(self.client.post('/v1/audio/speech',content=iter([b'x'*2048,b'y'*2049]),headers={'Content-Type':'application/json'}).status_code,413)
        self.assertEqual(self.requests,[])

    def test_foreign_origin_and_host(self):
        self.assertEqual(self.client.post('/v1/audio/speech',json=self.payload(),headers={'Origin':'https://example.org'}).status_code,403)
        self.assertEqual(self.client.get('/health',headers={'Host':'example.org'}).status_code,400)
        self.assertEqual(self.requests,[])

    def test_timeout_is_explicit(self):
        self.failure=httpx.ReadTimeout('timeout')
        self.assertEqual(self.client.post('/v1/audio/speech',json=self.payload()).status_code,504)
        self.assertEqual(len(self.requests),1)

    def test_unavailable_is_explicit(self):
        self.failure=httpx.ConnectError('unavailable')
        self.assertEqual(self.client.post('/v1/audio/speech',json=self.payload()).status_code,502)
        self.assertEqual(len(self.requests),1)

    def test_models_voices_and_cors(self):
        self.assertEqual([x['id'] for x in self.client.get('/v1/models').json()['data']],['kokoro','taigi-hanzi'])
        self.assertEqual(self.client.get('/v1/audio/voices').json()['voices'],['zf_xiaobei','taigi-demo-reference'])
        response=self.client.options('/v1/audio/speech',headers={'Origin':'http://localhost:5174','Access-Control-Request-Method':'POST'})
        self.assertEqual(response.headers.get('access-control-allow-origin'),'http://localhost:5174')

    def test_completion_log_contains_only_fixed_ids_and_metadata(self):
        payload={**self.payload(),'input':'private-utterance-do-not-log'}
        with self.assertLogs('local-speech-hub.completion',level='INFO') as captured:
            response=self.client.post('/v1/audio/speech',json=payload)
        entry=json.loads(captured.records[0].getMessage())
        self.assertEqual(set(entry),{'timestamp','route','model','voice','status','duration_ms','bytes'})
        self.assertEqual(entry['model'],'kokoro')
        self.assertEqual(entry['voice'],'zf_xiaobei')
        self.assertEqual(entry['status'],response.status_code)
        self.assertEqual(entry['bytes'],len(response.content))
        self.assertNotIn(payload['input'],captured.records[0].getMessage())


if __name__=='__main__':unittest.main()
