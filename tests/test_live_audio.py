from __future__ import annotations

import math
import struct
import unittest

from prototype.live_audio import (
    AudioChunk,
    AudioFrameError,
    chunk_pcm16le,
    decode_audio_frame,
    encode_audio_frame,
    float32_to_pcm16le,
    is_silent_pcm16le,
    pcm16le_duration_seconds,
    pcm16le_to_float32,
    resample_mono,
)


class LiveAudioPrimitiveTests(unittest.TestCase):
    def test_pcm_conversion_duration_sample_and_byte_count(self) -> None:
        pcm = float32_to_pcm16le([0.0] * 24_000)
        self.assertEqual(len(pcm), 48_000)
        self.assertEqual(len(pcm) // 2, 24_000)
        self.assertEqual(pcm16le_duration_seconds(pcm), 1.0)
        self.assertTrue(is_silent_pcm16le(pcm))

    def test_pcm_conversion_clips_and_preserves_sign(self) -> None:
        pcm = float32_to_pcm16le([-2.0, -1.0, 0.0, 1.0, 2.0, math.nan])
        values = struct.unpack("<6h", pcm)
        self.assertEqual(values[0], -32768)
        self.assertEqual(values[1], -32768)
        self.assertEqual(values[2], 0)
        self.assertEqual(values[3], 32767)
        self.assertEqual(values[4], 32767)
        self.assertEqual(values[5], 0)
        self.assertFalse(is_silent_pcm16le(float32_to_pcm16le([0.5])))

    def test_resampling_is_explicit_and_deterministic(self) -> None:
        source = [0.0] * 48_000
        source[24_000] = 1.0
        result = resample_mono(source, 48_000, 24_000)
        self.assertEqual(len(result), 24_000)
        self.assertEqual(resample_mono([0.0, 1.0], 24_000, 24_000), [0.0, 1.0])

    def test_transport_framing_and_chunk_sequence(self) -> None:
        pcm = float32_to_pcm16le([0.1] * 4_801)
        chunks = chunk_pcm16le(pcm, chunk_samples=2_400)
        self.assertEqual([chunk.sequence for chunk in chunks], [0, 1, 2])
        self.assertEqual(chunks[1].audio_start_seconds, 0.1)
        encoded = encode_audio_frame(chunks[0])
        decoded = decode_audio_frame(encoded)
        self.assertEqual(decoded.sequence, 0)
        self.assertEqual(decoded.pcm16le, chunks[0].pcm16le)
        with self.assertRaises(AudioFrameError):
            decode_audio_frame(b"bad")

    def test_odd_pcm_payload_is_rejected(self) -> None:
        with self.assertRaises(AudioFrameError):
            encode_audio_frame(AudioChunk(0, 0.0, b"\x00"))
        with self.assertRaises(AudioFrameError):
            decode_audio_frame(encode_audio_frame(AudioChunk(0, 0.0, b"\x00\x00")) + b"\x01")

    def test_decode_round_trip_values(self) -> None:
        values = [-1.0, -0.25, 0.0, 0.25, 1.0]
        decoded = pcm16le_to_float32(float32_to_pcm16le(values))
        self.assertAlmostEqual(decoded[1], values[1], places=3)
        self.assertAlmostEqual(decoded[3], values[3], places=3)


if __name__ == "__main__":
    unittest.main()
