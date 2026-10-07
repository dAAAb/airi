"""A small loopback OpenAI-compatible MMS speech API with strict POJ input."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import runpy
import shutil
import subprocess
from engine import MMSEngine, MODEL_ID, VOICE_ID, HANZI_MODEL_ID, transliterate_hanzi

DEFAULT_PORT, ORIGINS = runpy.run_path(str(Path(__file__).resolve().parent.parent / 'loopback-config.py'))['configuration']('AIRI_MMS', 8882)
MAX_BODY=8192


class Handler(BaseHTTPRequestHandler):
    def reply(self,status,body,content_type='application/json',extra=None):
        if isinstance(body,dict):body=json.dumps(body,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(body)))
        origin=self.headers.get('Origin')
        if origin in ORIGINS:self.send_header('Access-Control-Allow-Origin',origin)
        self.send_header('Vary','Origin')
        self.send_header('Access-Control-Expose-Headers','X-Synthesis-Seconds, X-Audio-Seconds, X-TTS-Model')
        for key,value in (extra or {}).items():self.send_header(key,value)
        self.end_headers();self.wfile.write(body)

    def valid_host(self):
        return self.headers.get('Host','').split(':')[0] in ('127.0.0.1','localhost')

    def do_OPTIONS(self):
        if not self.valid_host() or self.headers.get('Origin') not in ORIGINS:
            return self.reply(403,{'detail':'Origin or host is not allowed'})
        return self.reply(200,b'',extra={'Access-Control-Allow-Methods':'GET, POST, OPTIONS','Access-Control-Allow-Headers':'Content-Type, Authorization'})

    def do_GET(self):
        if not self.valid_host():return self.reply(403,{'detail':'Host is not allowed'})
        if self.path=='/health':return self.reply(200,{'status':'ok','model':MODEL_ID,'voice':VOICE_ID,'input':'POJ, or explicit Taigi-Hanzi transliteration model','provider':'pytorch-cpu','sample_rate':self.server.engine.sample_rate})
        if self.path=='/v1/models':return self.reply(200,{'object':'list','data':[{'id':key,'object':'model','created':0,'owned_by':'Meta'} for key in (MODEL_ID,HANZI_MODEL_ID)]})
        if self.path=='/v1/audio/voices':return self.reply(200,{'voices':[VOICE_ID]})
        if self.path=='/v1/voices':return self.reply(200,{'voices':[{'id':VOICE_ID,'name':'MMS Min Nan POJ','languages':[{'code':'nan','title':'Min Nan POJ'}]}]})
        return self.reply(404,{'detail':'Not found'})

    def do_POST(self):
        if not self.valid_host() or self.headers.get('Origin') not in (None,*ORIGINS):return self.reply(403,{'detail':'Origin or host is not allowed'})
        if self.path!='/v1/audio/speech':return self.reply(404,{'detail':'Not found'})
        try:length=int(self.headers.get('Content-Length','0'))
        except ValueError:return self.reply(400,{'detail':'Invalid Content-Length'})
        if not 0<length<=MAX_BODY:return self.reply(413,{'detail':'JSON body must be 1–8192 bytes'})
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.reply(415,{'detail':'Send application/json'})
        try:
            request=json.loads(self.rfile.read(length))
            if not isinstance(request,dict):raise ValueError('JSON object required')
            selected_model=request.get('model',MODEL_ID)
            if selected_model not in (MODEL_ID,HANZI_MODEL_ID):raise ValueError('Select a listed MMS model')
            if request.get('voice',VOICE_ID) not in (VOICE_ID,'alloy'):raise ValueError('Use voice '+VOICE_ID)
            response_format=request.get('response_format','wav')
            if response_format not in ('wav','mp3','pcm'):raise ValueError('Supported formats: wav, mp3, pcm')
            speed=float(request.get('speed',1.0))
            if not math.isfinite(speed):raise ValueError('speed must be finite')
            text=request.get('input')
            if selected_model==HANZI_MODEL_ID:text=transliterate_hanzi(text)
            audio,report=self.server.engine.synthesize(text,speed=speed)
            media_type='audio/wav'
            if response_format!='wav':
                ffmpeg=shutil.which('ffmpeg')
                if not ffmpeg:raise ValueError('FFmpeg is required for MP3 or PCM; use WAV')
                options=['-f','mp3'] if response_format=='mp3' else ['-ar','24000','-f','s16le','-acodec','pcm_s16le']
                encoded=subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-i','pipe:0',*options,'pipe:1'],input=audio,capture_output=True,check=True,timeout=30)
                audio=encoded.stdout
                media_type='audio/mpeg' if response_format=='mp3' else 'application/octet-stream'
        except (ValueError,TypeError) as error:return self.reply(422,{'detail':str(error)})
        except Exception:return self.reply(500,{'detail':'Local synthesis failed; check local server log'})
        return self.reply(200,audio,media_type,{'X-Synthesis-Seconds':str(report['synthesis_seconds']),'X-Audio-Seconds':str(report['audio_seconds']),'X-TTS-Model':selected_model})

    def log_message(self,format,*args):
        # Do not record user utterances or authorization values.
        pass


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=DEFAULT_PORT)
    args=parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('port must be between 1 and 65535')
    engine=MMSEngine()
    with ThreadingHTTPServer(('127.0.0.1',args.port),Handler) as server:
        server.engine=engine
        print(f'MMS Min Nan ready at http://127.0.0.1:{args.port}/v1/; POJ-only input',flush=True)
        server.serve_forever()
