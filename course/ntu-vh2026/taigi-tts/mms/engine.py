"""Strict POJ-character MMS Min Nan synthesis, with no automatic translation."""
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import unicodedata
import wave

ROOT = Path(__file__).resolve().parent
MODEL_ID = 'mms-tts-nan'
VOICE_ID = 'nan-poj'
HANZI_MODEL_ID = 'mms-tts-nan-taigi-hanzi'

def transliterate_hanzi(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 400:
        raise ValueError('Provide 1–400 Taigi Han characters')
    python = Path(os.environ.get('AIRI_TAIBUN_PYTHON', ROOT.parent / '.venv-taibun/bin/python'))
    if not python.exists():
        raise ValueError('Taibun environment is not configured; use POJ input or set AIRI_TAIBUN_PYTHON')
    script = Path(os.environ.get('AIRI_TAIBUN_SCRIPT', ROOT.parent / 'transliterate.py'))
    result = subprocess.run([str(python), str(script)], input=json.dumps({'text': text}), text=True, capture_output=True, timeout=15)
    if result.returncode:
        raise ValueError('Taibun conversion failed. Review input or use explicit POJ.')
    response = json.loads(result.stdout)
    if not response.get('ok'):
        raise ValueError('Taibun conversion failed')
    return response['poj']


def normalize_poj(text, vocab):
    if not isinstance(text, str) or not text.strip() or len(text) > 600:
        raise ValueError('Provide 1–600 characters of Min Nan POJ romanization')
    normalized = unicodedata.normalize('NFC', text.lower())
    normalized = re.sub(r'[.,!?;:，。！？；：]', ' ', normalized)
    normalized = ' '.join(normalized.split())
    allowed = set(vocab) - {'|', '<unk>'}
    unsupported = sorted(set(normalized) - allowed)
    if unsupported:
        raise ValueError('Unsupported POJ characters: ' + ' '.join(unsupported) + '. Han characters and digits are not automatically translated.')
    if not normalized:
        raise ValueError('No pronounceable POJ characters')
    return normalized


class MMSEngine:
    def __init__(self, threads=4):
        for key in ('HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE', 'HF_HUB_DISABLE_TELEMETRY'):
            os.environ[key] = '1'
        import torch
        from transformers import AutoTokenizer, VitsModel
        self.torch = torch
        self.lock = threading.Lock()
        torch.set_num_threads(threads)
        self.threads = threads
        self.vocab = json.loads((ROOT / 'model/vocab.json').read_text())
        started = time.perf_counter()
        self.tokenizer = AutoTokenizer.from_pretrained(str(ROOT / 'model'), local_files_only=True)
        self.model = VitsModel.from_pretrained(str(ROOT / 'model'), local_files_only=True).to('cpu').eval()
        self.load_seconds = time.perf_counter() - started
        self.sample_rate = self.model.config.sampling_rate
        self.parameters = sum(x.numel() for x in self.model.parameters())

    def synthesize(self, text, speed=1.0, seed=2026):
        if not 0.5 <= speed <= 2.0:
            raise ValueError('speed must be between 0.5 and 2.0')
        normalized = normalize_poj(text, self.vocab)
        inputs = self.tokenizer(normalized, return_tensors='pt')
        actual = [int(x) for x in inputs['input_ids'][0].tolist() if int(x) != self.tokenizer.pad_token_id]
        expected = [self.vocab[character] for character in normalized]
        if actual != expected:
            raise ValueError('Tokenizer changed or discarded input characters; refusing synthesis')
        if self.tokenizer.unk_token_id in actual:
            raise ValueError('Unknown token found; refusing synthesis')
        with self.lock:
            self.torch.manual_seed(seed)
            self.model.speaking_rate = speed
            started = time.perf_counter()
            with self.torch.inference_mode():
                audio = self.model(**inputs).waveform[0].cpu().numpy()
            elapsed = time.perf_counter() - started
        import numpy as np
        if not len(audio) or not np.isfinite(audio).all():
            raise RuntimeError('Empty or non-finite synthesis result')
        pcm = (np.clip(audio, -1, 1) * 32767).astype('<i2').tobytes()
        output = io.BytesIO()
        with wave.open(output, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self.sample_rate)
            wav.writeframes(pcm)
        report = {'input': text, 'normalized_poj': normalized, 'unknown_tokens': 0,
            'sample_rate': self.sample_rate, 'audio_seconds': len(audio) / self.sample_rate,
            'synthesis_seconds': elapsed, 'rtf': elapsed / (len(audio) / self.sample_rate),
            'speed': speed, 'seed': seed, 'provider': 'pytorch-cpu', 'threads': self.threads}
        return output.getvalue(), report
