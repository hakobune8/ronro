"""Small, deterministic audio primitives for the L1 browser transport.

The browser captures Float32 microphone frames in an AudioWorklet.  These
helpers describe the application-owned wire format and the conversion to the
Realtime transcription input format.  They intentionally do not know about
STT, Analyzer, or the canonical Discussion Graph.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from typing import Iterable, Sequence


TARGET_SAMPLE_RATE = 24_000
TARGET_CHANNELS = 1
PCM_SAMPLE_WIDTH = 2
DEFAULT_CHUNK_SAMPLES = 2_400  # 100 ms at 24 kHz
FRAME_MAGIC = b"DMAP"
FRAME_VERSION = 1
FRAME_HEADER = struct.Struct("<4sB3xId")


class AudioFrameError(ValueError):
    """An audio transport frame is malformed or out of order."""


@dataclass(frozen=True)
class AudioChunk:
    sequence: int
    audio_start_seconds: float
    pcm16le: bytes

    @property
    def sample_count(self) -> int:
        return len(self.pcm16le) // PCM_SAMPLE_WIDTH

    @property
    def duration_seconds(self) -> float:
        return self.sample_count / TARGET_SAMPLE_RATE

    @property
    def audio_end_seconds(self) -> float:
        return self.audio_start_seconds + self.duration_seconds


def clamp_sample(value: float) -> float:
    """Clamp a Float32 sample before PCM16 conversion."""

    if not math.isfinite(value):
        return 0.0
    return max(-1.0, min(1.0, float(value)))


def float32_to_pcm16le(samples: Iterable[float]) -> bytes:
    """Convert mono normalized samples to signed little-endian PCM16."""

    values = [clamp_sample(sample) for sample in samples]
    encoded = bytearray()
    for value in values:
        # Use the asymmetric endpoints used by common PCM conversion: -1.0
        # maps to -32768 and +1.0 maps to +32767.
        integer = int(round(value * 32767.0)) if value >= 0 else int(round(value * 32768.0))
        encoded.extend(struct.pack("<h", max(-32768, min(32767, integer))))
    return bytes(encoded)


def pcm16le_to_float32(pcm16le: bytes) -> list[float]:
    """Decode PCM16 for deterministic tests and diagnostics."""

    if len(pcm16le) % PCM_SAMPLE_WIDTH:
        raise AudioFrameError("PCM16 byte length must be even")
    return [sample / 32768.0 for (sample,) in struct.iter_unpack("<h", pcm16le)]


def resample_mono(samples: Sequence[float], source_rate: int, target_rate: int = TARGET_SAMPLE_RATE) -> list[float]:
    """Linearly resample a mono frame without assuming browser sample rate.

    AudioWorklet frames are short, so a bounded linear interpolation is a
    sufficient Prototype 1 conversion.  The browser keeps the source sample
    rate explicit and sends only the resulting 24 kHz PCM16 to the server.
    """

    if source_rate <= 0 or target_rate <= 0:
        raise ValueError("sample rates must be positive")
    if not samples:
        return []
    if source_rate == target_rate:
        return [float(value) for value in samples]
    output_count = max(1, int(round(len(samples) * target_rate / source_rate)))
    ratio = source_rate / target_rate
    result: list[float] = []
    last = len(samples) - 1
    for index in range(output_count):
        position = index * ratio
        left = min(last, int(position))
        right = min(last, left + 1)
        fraction = position - left
        result.append(float(samples[left]) * (1.0 - fraction) + float(samples[right]) * fraction)
    return result


def pcm16le_duration_seconds(pcm16le: bytes, sample_rate: int = TARGET_SAMPLE_RATE) -> float:
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if len(pcm16le) % PCM_SAMPLE_WIDTH:
        raise AudioFrameError("PCM16 byte length must be even")
    return (len(pcm16le) // PCM_SAMPLE_WIDTH) / sample_rate


def is_silent_pcm16le(pcm16le: bytes, threshold: int = 8) -> bool:
    """Return whether every absolute PCM sample is below a small threshold."""

    if threshold < 0:
        raise ValueError("threshold must be non-negative")
    if len(pcm16le) % PCM_SAMPLE_WIDTH:
        raise AudioFrameError("PCM16 byte length must be even")
    return all(abs(sample) <= threshold for (sample,) in struct.iter_unpack("<h", pcm16le))


def encode_audio_frame(chunk: AudioChunk) -> bytes:
    """Encode a browser→Python binary transport frame.

    Header: ``DMAP`` magic, version byte, uint32 runtime chunk sequence,
    float64 audio start seconds, then mono PCM16LE bytes.
    """

    if chunk.sequence < 0:
        raise AudioFrameError("audio chunk sequence must be non-negative")
    if chunk.audio_start_seconds < 0 or not math.isfinite(chunk.audio_start_seconds):
        raise AudioFrameError("audio start must be a finite non-negative number")
    if len(chunk.pcm16le) == 0 or len(chunk.pcm16le) % PCM_SAMPLE_WIDTH:
        raise AudioFrameError("audio chunk must contain a non-empty even PCM16 byte sequence")
    return FRAME_HEADER.pack(FRAME_MAGIC, FRAME_VERSION, chunk.sequence, chunk.audio_start_seconds) + chunk.pcm16le


def decode_audio_frame(data: bytes) -> AudioChunk:
    if len(data) <= FRAME_HEADER.size:
        raise AudioFrameError("audio frame is too short")
    try:
        magic, version, sequence, audio_start = FRAME_HEADER.unpack(data[: FRAME_HEADER.size])
    except struct.error as exc:
        raise AudioFrameError("audio frame header is malformed") from exc
    if magic != FRAME_MAGIC:
        raise AudioFrameError("audio frame magic is invalid")
    if version != FRAME_VERSION:
        raise AudioFrameError(f"unsupported audio frame version: {version}")
    pcm = data[FRAME_HEADER.size :]
    if len(pcm) % PCM_SAMPLE_WIDTH:
        raise AudioFrameError("audio frame PCM16 payload must have an even byte length")
    return AudioChunk(sequence=sequence, audio_start_seconds=audio_start, pcm16le=pcm)


def chunk_pcm16le(
    pcm16le: bytes,
    *,
    start_seconds: float = 0.0,
    chunk_samples: int = DEFAULT_CHUNK_SAMPLES,
) -> list[AudioChunk]:
    """Split PCM16 into ordered runtime chunks for tests and adapters."""

    if chunk_samples <= 0:
        raise ValueError("chunk_samples must be positive")
    if len(pcm16le) % PCM_SAMPLE_WIDTH:
        raise AudioFrameError("PCM16 byte length must be even")
    chunks: list[AudioChunk] = []
    sample_offset = 0
    sequence = 0
    while sample_offset < len(pcm16le) // PCM_SAMPLE_WIDTH:
        start = sample_offset * PCM_SAMPLE_WIDTH
        end = min(len(pcm16le), start + chunk_samples * PCM_SAMPLE_WIDTH)
        chunks.append(
            AudioChunk(
                sequence=sequence,
                audio_start_seconds=start_seconds + sample_offset / TARGET_SAMPLE_RATE,
                pcm16le=pcm16le[start:end],
            )
        )
        sequence += 1
        sample_offset += (end - start) // PCM_SAMPLE_WIDTH
    return chunks
