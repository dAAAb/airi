"""Create the pinned CPU TTS engine from an explicit local model directory."""
import os
from pathlib import Path
import sherpa_onnx


def create_tts():
    root = Path(os.environ.get("BREEZE2_MODEL_DIR", Path(__file__).parent / "model")).expanduser().resolve()
    config = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                model=str(root / "breeze2-vits.onnx"),
                lexicon=str(root / "lexicon.txt"),
                tokens=str(root / "tokens.txt"),
            ), num_threads=4, provider="cpu", debug=False
        ), max_num_sentences=1,
    )
    if not config.validate():
        raise RuntimeError("Invalid Sherpa TTS configuration. Download and verify the model first.")
    return sherpa_onnx.OfflineTts(config)
