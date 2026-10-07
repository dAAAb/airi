"""Offline Taiwan Hokkien inference using published KaedeTai checkpoints.

This replaces the upstream CLI's unpublished tts_long dependency. It calls the
published S1, S2, Taiwanese phoneme frontend, Hubert and speaker encoder directly.
The reference is the author's released synthetic demo, not a cloned human voice.
"""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time
import unicodedata

ROOT = Path(__file__).resolve().parent
REPO = Path(os.environ.get('AIRI_TAIGI_SOURCE_DIR', ROOT / 'GPT-SoVITS')).expanduser().resolve()
MODELS = Path(os.environ.get('AIRI_TAIGI_MODELS_DIR', ROOT / 'models')).expanduser().resolve()
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['PYTORCH_ENABLE_MPS_FALLBACK'] = '1'
sys.path[:0] = [str(REPO), str(REPO / 'GPT_SoVITS'), str(REPO / 'GPT_SoVITS/eres2net')]

import librosa
import numpy as np
import soundfile as sf
import torch
from transformers import HubertModel
from AR.models.t2s_model import Text2SemanticDecoder
from module.models import SynthesizerTrn
from module.mel_processing import spectrogram_torch
from ERes2NetV2 import ERes2NetV2
import kaldi
from text.cleaner import clean_text
from text import cleaned_text_to_sequence
from sandhi_preprocessor import apply_sandhi


class TaigiEngine:
    def __init__(self, device='cpu'):
        self.device = torch.device(device)
        torch.set_num_threads(4)
        start = time.perf_counter()
        s1 = torch.load(MODELS / 's1_trilingual.ckpt', map_location='cpu', weights_only=True)
        self.s1 = Text2SemanticDecoder(s1['config'], top_k=3)
        weights = {k.removeprefix('model.'): v for k, v in s1['weight'].items()}
        self.s1.load_state_dict(weights)
        self.s1.eval().to(self.device)
        s2 = torch.load(MODELS / 's2_r4_e15.pth', map_location='cpu', weights_only=True)
        print('S2_KEYS', list(s2), flush=True)
        # The published file is a training checkpoint: config is not embedded.
        # Its architecture is defined in the same pinned source tree. Strict
        # tensor shape/key checking below prevents a silently wrong config.
        cfg = s2.get('config') or json.loads((REPO / 'configs/s2_tai_v2pro_ft.json').read_text())
        weights2 = s2.get('weight', s2.get('model'))
        self.cfg = cfg
        model_cfg = dict(cfg['model'])
        model_cfg['version'] = 'v2ProTw'
        model_cfg['semantic_frame_rate'] = '25hz'
        self.s2 = SynthesizerTrn(cfg['data']['filter_length'] // 2 + 1,
            cfg['train']['segment_size'] // cfg['data']['hop_length'],
            n_speakers=cfg['data']['n_speakers'], **model_cfg)
        match = self.s2.load_state_dict(weights2, strict=False)
        print('S2_LOAD', match, flush=True)
        if match.missing_keys or match.unexpected_keys:
            raise RuntimeError('S2 architecture does not match published weights')
        del s1, s2, weights, weights2
        self.s2.eval().to(self.device)
        self.hubert = HubertModel.from_pretrained(MODELS / 'chinese-hubert-base', local_files_only=True).eval().to(self.device)
        self.sv = ERes2NetV2(baseWidth=24, scale=4, expansion=4)
        self.sv.load_state_dict(torch.load(MODELS / 'sv/pretrained_eres2netv2w24s4ep4.ckpt', map_location='cpu', weights_only=True))
        self.sv.eval().to(self.device)
        self.ref_path = REPO / 'tw_samples/demo_02_kin_a_jit_thinn_khi.mp3'
        # Published demo transcript after the author's r4 sandhi preprocessing.
        self.ref_text = 'Kīn-à-ji̍t thīnn-khì tsiok hó.'
        self.ref_ids, _ = self.phone_ids(self.ref_text, sandhi=False)
        with torch.inference_mode():
            ref16, _ = librosa.load(self.ref_path, sr=16000, mono=True)
            ref32, _ = librosa.load(self.ref_path, sr=cfg['data']['sampling_rate'], mono=True)
            wav16 = torch.from_numpy(np.pad(ref16, (0, 4800))).to(self.device).unsqueeze(0)
            hidden = self.hubert(wav16).last_hidden_state.transpose(1, 2)
            self.prompt = self.s2.extract_latent(hidden)[0, 0].unsqueeze(0)
            wave32 = torch.from_numpy(ref32).unsqueeze(0)
            # FFT feature extraction stays on CPU. Neural networks use device.
            d = cfg['data']
            self.ref_spec = spectrogram_torch(wave32, d['filter_length'], d['sampling_rate'], d['hop_length'], d['win_length'], center=False).to(self.device)
            feats = kaldi.fbank(torch.from_numpy(ref16).unsqueeze(0), num_mel_bins=80, sample_frequency=16000, dither=0)
            self.ref_sv = self.sv.forward3(feats.unsqueeze(0).to(self.device))
        self.load_seconds = time.perf_counter() - start
        print('LOADED', self.load_seconds, device, flush=True)

    def phone_ids(self, text, sandhi=True):
        if any('CJK' in unicodedata.name(c, '') and 'IDEOGRAPH' in unicodedata.name(c, '') for c in text):
            raise ValueError('Provide tone-marked POJ/Tai-lo, not Chinese characters')
        # Match the published r4 weights rather than the author's newer private stack.
        processed = apply_sandhi(text, t2_target=3, t5_target=7, t7_to_t3=True, citation_t3_remap=False, sandhi_after_double_dash=False) if sandhi else text
        phones, _, normalized = clean_text(processed, 'tw', 'v2tw')
        if not any(p.startswith('tw_') for p in phones) or 'UNK' in phones:
            raise ValueError('Unsupported Taiwanese phoneme: ' + repr(phones))
        if len(phones) > 180:
            raise ValueError('Utterance exceeds the 180-phoneme experimental limit; split into shorter sentences')
        return cleaned_text_to_sequence(phones, 'v2tw'), normalized

    def synthesize(self, text, seed=42):
        target_ids, normalized = self.phone_ids(text)
        start = time.perf_counter()
        torch.manual_seed(seed)
        ids = torch.tensor([self.ref_ids + target_ids], device=self.device)
        lens = torch.tensor([ids.shape[-1]], device=self.device)
        bert = torch.zeros((1, 1024, ids.shape[-1]), device=self.device)
        with torch.inference_mode():
            pred, idx = self.s1.infer_panel(ids, lens, self.prompt, bert,
                top_k=20, top_p=0.6, temperature=0.6, early_stop_num=750)
            if idx <= 0 or idx >= 750:
                raise RuntimeError('S1 hit the duration cap without a natural stop')
            pred = pred[:, -idx:].unsqueeze(0)
            output = self.s2.decode(pred, torch.tensor([target_ids], device=self.device),
                [self.ref_spec], speed=1.0, sv_emb=[self.ref_sv])[0][0]
            waveform = output.detach().float().cpu().numpy()
        if not waveform.size or not np.isfinite(waveform).all():
            raise RuntimeError('Empty or nonfinite waveform')
        peak = float(np.abs(waveform).max())
        if peak > 1:
            waveform = waveform / peak
        rate = self.cfg['data']['sampling_rate']
        return waveform, rate, dict(text=text, normalized=normalized, phonemes=len(target_ids),
            inference_seconds=time.perf_counter()-start, audio_seconds=len(waveform)/rate,
            semantic_tokens=idx, device=str(self.device), seed=seed, reference='KaedeTai upstream synthetic demo_02_kin_a_jit_thinn_khi.mp3')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('text', nargs='?', default='Lí hó, guá sī lí ê Tâi-gí tsōo-lí.')
    parser.add_argument('--device', choices=['cpu', 'mps'], default='cpu')
    parser.add_argument('--output', type=Path, default=ROOT/'outputs/new-sentence.wav')
    args = parser.parse_args()
    engine = TaigiEngine(args.device)
    wav, sr, result = engine.synthesize(args.text)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(args.output, wav, sr, subtype='PCM_16')
    result['load_seconds'] = engine.load_seconds
    result['versions'] = {p: importlib.metadata.version(p) for p in ['torch','torchaudio','transformers','librosa']}
    result['source'] = 'KaedeTai/gpt-sovits-tw, r4 public weights, custom direct inference runner'
    result['reference_is_synthetic'] = True
    result['quality'] = 'Not yet rated by a native Taiwanese speaker'
    args.output.with_suffix('.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
