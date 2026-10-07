"""Exercise the bundled codecs without loading MLX weights or user recordings."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import av
from fastapi import HTTPException
import numpy as np
from server import decode_audio_file


class DecoderTests(unittest.TestCase):
    def make_clip(self, path, codec):
        rate = 48000
        wave = np.sin(np.arange(rate, dtype=np.float32) * 2 * np.pi * 440 / rate) * .2
        with av.open(str(path), 'w') as output:
            stream = output.add_stream(codec, rate=rate)
            stream.layout = 'mono'
            frame = av.AudioFrame.from_ndarray(wave.reshape(1, -1), format='flt', layout='mono')
            frame.sample_rate = rate
            for packet in stream.encode(frame):
                output.mux(packet)
            for packet in stream.encode():
                output.mux(packet)

    def test_microphone_formats_are_mono_16k(self):
        with tempfile.TemporaryDirectory() as folder:
            for suffix, codec in [('wav', 'pcm_s16le'), ('webm', 'libopus'), ('mp3', 'libmp3lame')]:
                with self.subTest(format=suffix):
                    path = Path(folder) / ('test.' + suffix)
                    self.make_clip(path, codec)
                    audio, duration = decode_audio_file(path)
                    self.assertAlmostEqual(duration, 1, delta=.05)
                    self.assertEqual(audio.ndim, 1)
                    self.assertEqual(audio.dtype, np.float32)
                    self.assertTrue(np.isfinite(audio).all())
                    self.assertGreater(float(abs(audio).max()), .1)

    def test_invalid_and_excess_audio_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'invalid.wav'
            path.write_bytes(b'invalid')
            with self.assertRaises(HTTPException) as error:
                decode_audio_file(path)
            self.assertEqual(error.exception.status_code, 422)
            self.make_clip(path, 'pcm_s16le')
            with patch('server.MAX_AUDIO_SECONDS', .2), self.assertRaises(HTTPException) as error:
                decode_audio_file(path)
            self.assertEqual(error.exception.status_code, 413)


if __name__ == '__main__':
    unittest.main()
