"""Verify the runtime fix using the local tokenizer, without loading weights."""
import json
from pathlib import Path

from transformers import WhisperProcessor
from mlx_audio.stt.models.whisper.whisper import HFTokenizerWrapper
from mlx_audio.stt.models.whisper.decoding import get_suppress_tokens

import runpy
compat = runpy.run_path(str(Path(__file__).with_name("whisper-compat.py")))
patch_and_verify_wrapper = compat["patch_and_verify_wrapper"]
resolve_no_speech_id = compat["resolve_no_speech_id"]

import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--model-dir", type=Path, default=Path(__file__).resolve().parent / "model")
model_path = parser.parse_args().model_dir
processor = WhisperProcessor.from_pretrained(str(model_path), local_files_only=True)
wrapper = HFTokenizerWrapper(processor.tokenizer, language="zh", task="transcribe")
before = {"eot": wrapper.eot, "no_speech": wrapper.no_speech,
          "eot_suppressed": wrapper.eot in get_suppress_tokens(wrapper)}
after = patch_and_verify_wrapper(wrapper, get_suppress_tokens)
expected = json.loads((model_path / "generation_config.json").read_text())["suppress_tokens"]
assert set(get_suppress_tokens(wrapper)) == set(expected)
assert wrapper.eot == 50257 and wrapper.no_speech == 50362

class InvalidTokenizer:
    eos_token_id = 50257
    unk_token_id = 50257
    def __init__(self, vocab): self.vocab = vocab
    def get_vocab(self): return self.vocab
    def convert_tokens_to_ids(self, text): return self.vocab.get(text, self.unk_token_id)

for invalid in ({}, {"<|nocaptions|>": 50257},
                {"<|nocaptions|>": 50362, "<|nospeech|>": 50361}):
    try:
        resolve_no_speech_id(InvalidTokenizer(invalid))
    except ValueError:
        continue
    raise AssertionError("Unsafe or ambiguous vocabulary was accepted")

print(json.dumps({"before": before, "after": after,
                  "suppression_matches_generation_config": True,
                  "invalid_vocabulary_checks": 3}, ensure_ascii=False, indent=2))
