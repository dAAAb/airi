"""Runtime-only fix for mlx-audio 0.4.3 HF Whisper no-speech token lookup.

NOTICE:
mlx-audio 0.4.3 reads <|nospeech|> although this HF tokenizer has <|nocaptions|>.
Its unknown-token fallback equals EOT, so the decoder suppresses its own end.
Context: mlx_audio/stt/models/whisper/whisper.py, HFTokenizerWrapper.no_speech.
Remove this workaround after the upstream wrapper passes verify-tokenizer.py.
Call install_whisper_no_speech_compat(model) after load(), before generate().
No model weights, tokenizer files, or installed package files are changed.
"""


def resolve_no_speech_id(hf_tokenizer):
    """Resolve a real vocabulary entry; never accept unknown-token fallback."""
    vocab = hf_tokenizer.get_vocab()
    eot = hf_tokenizer.eos_token_id
    if eot is None:
        raise ValueError("Whisper tokenizer has no EOS token ID")
    candidates = []
    for spelling in ("<|nocaptions|>", "<|nospeech|>"):
        if spelling not in vocab:
            continue
        token_id = int(vocab[spelling])
        if token_id < 0 or token_id == eot or token_id == hf_tokenizer.unk_token_id:
            raise ValueError(f"Unsafe no-speech token mapping: {spelling}={token_id}")
        if hf_tokenizer.convert_tokens_to_ids(spelling) != token_id:
            raise ValueError(f"Inconsistent vocabulary mapping for {spelling}")
        candidates.append((spelling, token_id))
    if not candidates:
        raise ValueError("No valid Whisper no-speech token in the vocabulary")
    if len({token_id for _, token_id in candidates}) != 1:
        raise ValueError("Ambiguous no-speech token IDs; refusing to patch")
    return candidates[0]


def patch_and_verify_wrapper(wrapper, get_suppress_tokens):
    """Patch this wrapper class in memory, restoring it if verification fails."""
    spelling, expected_id = resolve_no_speech_id(wrapper.hf_tokenizer)
    previous_id = wrapper.no_speech
    wrapper_class = type(wrapper)
    previous_property = wrapper_class.no_speech

    def validated_no_speech(self):
        return resolve_no_speech_id(self.hf_tokenizer)[1]

    wrapper_class.no_speech = property(validated_no_speech)
    try:
        suppressed = get_suppress_tokens(wrapper)
        if wrapper.no_speech != expected_id:
            raise ValueError("No-speech token verification failed")
        if wrapper.eot in suppressed:
            raise ValueError("EOS is still suppressed; refusing this decoder setup")
        if expected_id not in suppressed:
            raise ValueError("No-speech token is not suppressed as expected")
    except Exception:
        wrapper_class.no_speech = previous_property
        raise
    return {
        "compatibility_patch": "HF Whisper no-speech spelling",
        "previous_no_speech_id": previous_id,
        "no_speech_spelling": spelling,
        "no_speech_id": expected_id,
        "eot_id": wrapper.eot,
        "eot_suppressed": False,
        "scope": "in-memory wrapper property only; site-packages unchanged",
    }


def install_whisper_no_speech_compat(model):
    """Return verified patch metadata for an already loaded mlx-audio model."""
    from mlx_audio.stt.models.whisper.decoding import get_suppress_tokens

    wrapper = model.get_tokenizer(language="zh", task="transcribe")
    return patch_and_verify_wrapper(wrapper, get_suppress_tokens)
