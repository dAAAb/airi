"""Tokenizer regression tests with no ML dependencies or model download."""
from pathlib import Path
import runpy
import unittest

compat = runpy.run_path(str(Path(__file__).with_name('whisper-compat.py')))
resolve = compat['resolve_no_speech_id']
patch_wrapper = compat['patch_and_verify_wrapper']


class Tokenizer:
    eos_token_id = 50257
    unk_token_id = 50257

    def __init__(self, vocab):
        self.vocab = vocab

    def get_vocab(self):
        return self.vocab

    def convert_tokens_to_ids(self, token):
        return self.vocab.get(token, self.unk_token_id)


class CompatTests(unittest.TestCase):
    def test_missing_unsafe_and_ambiguous_tokens_fail(self):
        for vocab in [{}, {'<|nocaptions|>': 50257}, {'<|nocaptions|>': 50362, '<|nospeech|>': 50361}]:
            with self.assertRaises(ValueError):
                resolve(Tokenizer(vocab))

    def test_valid_token_is_a_real_entry(self):
        self.assertEqual(resolve(Tokenizer({'<|nocaptions|>': 50362})), ('<|nocaptions|>', 50362))

    def test_failed_verification_rolls_back(self):
        class Wrapper:
            hf_tokenizer = Tokenizer({'<|nocaptions|>': 50362})
            eot = 50257
            no_speech = property(lambda self: self.hf_tokenizer.convert_tokens_to_ids('<|nospeech|>'))
        original = Wrapper.no_speech
        with self.assertRaises(ValueError):
            patch_wrapper(Wrapper(), lambda wrapper: [wrapper.no_speech, wrapper.eot])
        self.assertIs(Wrapper.no_speech, original)

    def test_end_token_is_no_longer_suppressed(self):
        class Wrapper:
            hf_tokenizer = Tokenizer({'<|nocaptions|>': 50362})
            eot = 50257
            no_speech = property(lambda self: self.hf_tokenizer.convert_tokens_to_ids('<|nospeech|>'))
        wrapper = Wrapper()
        self.assertEqual(wrapper.no_speech, wrapper.eot)
        report = patch_wrapper(wrapper, lambda value: [value.no_speech])
        self.assertEqual(wrapper.no_speech, 50362)
        self.assertFalse(report['eot_suppressed'])


if __name__ == '__main__':
    unittest.main()
