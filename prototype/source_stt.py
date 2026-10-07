"""Provider-neutral, source-scoped STT item and PCM coverage accounting.

This holds bounded range/signal metadata and pending Finals, never raw audio.
Signal means only nontrivial PCM energy, not confirmed speech. Providers must
report item ranges in the source's 24 kHz transport sample coordinates; an
unknown or overlapping range is an integrity failure, not a guessed Final.
"""

from __future__ import annotations

import hashlib
import math
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from typing import AsyncIterator, Protocol

from .live_audio import AudioChunk, TARGET_SAMPLE_RATE


class STTIntegrityError(ValueError):
    """An item, source or audio range cannot safely be correlated."""


@dataclass(frozen=True)
class STTSource:
    session_id: str
    run_id: str
    player_id: str
    connection_generation: str

    def __post_init__(self) -> None:
        if any(not isinstance(value, str) or not value for value in (
            self.session_id, self.run_id, self.player_id, self.connection_generation,
        )):
            raise STTIntegrityError("source identity is incomplete")
        if any(len(value) > 128 for value in (
            self.session_id, self.run_id, self.player_id, self.connection_generation,
        )):
            raise STTIntegrityError("source identity is too long")


@dataclass(frozen=True)
class AudioRange:
    start_sample: int
    end_sample: int

    def __post_init__(self) -> None:
        if (type(self.start_sample) is not int or type(self.end_sample) is not int
                or self.start_sample < 0 or self.end_sample <= self.start_sample):
            raise STTIntegrityError("audio range must be positive and sample-aligned")


@dataclass(frozen=True)
class STTCommitted:
    source: STTSource
    item_id: str
    audio_range: AudioRange


@dataclass(frozen=True)
class STTPartial:
    """Ephemeral Provider hypothesis; never an Evidence candidate."""

    source: STTSource
    text: str
    item_id: str | None = None


@dataclass(frozen=True)
class STTBoundary:
    """Provider speech boundary hint; only Committed owns PCM coverage."""

    source: STTSource
    reason: str
    audio_range: AudioRange | None = None
    item_id: str | None = None


@dataclass(frozen=True)
class STTFinal:
    source: STTSource
    item_id: str
    text: str


@dataclass(frozen=True)
class STTFailure:
    source: STTSource
    code: str
    item_id: str | None = None

    def __post_init__(self) -> None:
        if (not isinstance(self.code, str) or not self.code
                or len(self.code) > 64
                or any(not (char.isascii() and (char.isalnum() or char == "_"))
                       for char in self.code)):
            raise STTIntegrityError("Provider failure code must be a safe identifier")


class LiveSTTSession(Protocol):
    """One Provider stream per audio source; no Canonical write permission."""

    async def append_audio(self, chunk: AudioChunk) -> None: ...

    async def finish(self, reason: str) -> None: ...

    def events(self) -> AsyncIterator[
        STTPartial | STTBoundary | STTCommitted | STTFinal | STTFailure
    ]: ...


class LiveSTTProvider(Protocol):
    async def open(self, *, source: STTSource,
                   config: Mapping[str, object]) -> LiveSTTSession: ...


@dataclass(frozen=True)
class STTDrain:
    unresolved_item_ids: tuple[str, ...]
    unclaimed_audio: tuple[AudioRange, ...]
    uncommitted_audio: AudioRange | None
    source_failure_codes: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not (self.unresolved_item_ids or self.unclaimed_audio
                    or self.uncommitted_audio or self.source_failure_codes)


@dataclass
class _Item:
    audio_range: AudioRange
    possible_signal: bool
    digest: bytes | None = None
    final: STTFinal | None = None
    acknowledged: bool = False
    unresolved_empty: bool = False
    unresolved_failure: bool = False
    failure_code: str | None = None


class SourceSTTLedger:
    """Correlate one source's frames, committed items and accepted Finals.

    Accepted Finals are returned in item-commit order. The caller acknowledges
    each only *after* durable Evidence acceptance. A blank Final never creates
    Evidence; possible signal makes it an unresolved item while later items
    may still proceed. Cross-source ordering belongs to the Content merger.
    """

    def __init__(self, source: STTSource, *, max_pending_frames: int = 1200,
                 max_items: int = 256) -> None:
        if max_pending_frames < 1 or max_items < 1:
            raise ValueError("STT ledger bounds must be positive")
        self.source = source
        self._max_pending_frames = max_pending_frames
        self._max_items = max_items
        self._next_sequence = 0
        self._sample_end = 0
        self._committed_end = 0
        self._frames: list[tuple[int, int, bool]] = []
        self._items: dict[str, _Item] = {}
        self._unclaimed: list[AudioRange] = []
        self._source_failures: list[str] = []
        self._closed = False

    @property
    def accepted_sample_end(self) -> int:
        return self._sample_end

    def append(self, chunk: AudioChunk) -> None:
        if self._closed:
            raise STTIntegrityError("source capture is closed")
        if (type(chunk.sequence) is not int or chunk.sequence != self._next_sequence
                or not chunk.pcm16le or len(chunk.pcm16le) % 2
                or len(chunk.pcm16le) > 9_600):
            raise STTIntegrityError("audio frame sequence or PCM size is invalid")
        raw_start = chunk.audio_start_seconds * TARGET_SAMPLE_RATE
        if (not math.isfinite(raw_start) or raw_start < 0
                or abs(raw_start - round(raw_start)) > 1e-4
                or round(raw_start) != self._sample_end):
            raise STTIntegrityError("audio frame has a gap or overlap")
        if len(self._frames) >= self._max_pending_frames:
            raise STTIntegrityError("uncommitted audio metadata limit reached")
        possible_signal = any(abs(sample) > 8 for (sample,) in struct.iter_unpack("<h", chunk.pcm16le))
        end = self._sample_end + chunk.sample_count
        self._frames.append((self._sample_end, end, possible_signal))
        self._sample_end = end
        self._next_sequence += 1

    def commit(self, value: STTCommitted) -> None:
        if value.source != self.source or not value.item_id or len(value.item_id) > 256:
            raise STTIntegrityError("committed item has wrong source or no identity")
        if value.item_id in self._items:
            if self._items[value.item_id].audio_range == value.audio_range:
                return  # Duplicate Provider acknowledgement, not a new item.
            raise STTIntegrityError("committed item identity changed its audio range")
        span = value.audio_range
        if (span.start_sample < self._committed_end or span.end_sample > self._sample_end
                or len(self._items) >= self._max_items):
            raise STTIntegrityError("committed item range is unknown, overlapping or unbounded")
        if span.start_sample > self._committed_end:
            skipped = AudioRange(self._committed_end, span.start_sample)
            if self._has_signal(skipped):
                self._unclaimed.append(skipped)
        possible_signal = self._has_signal(span)
        self._items[value.item_id] = _Item(span, possible_signal)
        self._committed_end = span.end_sample
        self._frames = [(max(start, span.end_sample), end, signal)
                        for start, end, signal in self._frames if end > span.end_sample]

    def complete(self, value: STTFinal) -> bool:
        if (value.source != self.source or not value.item_id or len(value.item_id) > 256
                or not isinstance(value.text, str) or len(value.text) > 16_000):
            raise STTIntegrityError("Final has wrong source or invalid identity/text")
        item = self._items.get(value.item_id)
        if item is None:
            raise STTIntegrityError("Final has no correlated committed item")
        if item.unresolved_failure:
            raise STTIntegrityError("failed item cannot later become a Final")
        digest = hashlib.sha256(value.text.encode("utf-8")).digest()
        if item.digest is not None:
            if item.digest == digest:
                return False  # Idempotent duplicate, including after acknowledgement.
            raise STTIntegrityError("conflicting duplicate Final")
        item.digest = digest
        if value.text.strip():
            item.final = value
        else:
            item.acknowledged = True
            item.unresolved_empty = item.possible_signal
        return True

    def fail(self, value: STTFailure) -> None:
        """Record an explicit incomplete item/source without ending the meeting."""
        if value.source != self.source:
            raise STTIntegrityError("Provider failure belongs to another source")
        if value.item_id is None:
            if len(self._source_failures) >= 32:
                raise STTIntegrityError("source failure metadata limit reached")
            self._source_failures.append(value.code)
            return
        item = self._items.get(value.item_id)
        if item is None:
            raise STTIntegrityError("failure has no correlated committed item")
        if item.unresolved_failure:
            if item.failure_code == value.code:
                return
            raise STTIntegrityError("conflicting duplicate item failure")
        if item.acknowledged or item.final is not None:
            raise STTIntegrityError("completed item cannot become a failure")
        item.unresolved_failure = True
        item.failure_code = value.code
        item.acknowledged = True  # Let subsequent completed items progress.

    def next_ready_final(self) -> STTFinal | None:
        """Return one ordered Final; retry it until Evidence is acknowledged."""
        for item in self._items.values():
            if item.acknowledged:
                continue
            return item.final
        return None

    def acknowledge(self, item_id: str) -> None:
        ready = self.next_ready_final()
        if ready is None or ready.item_id != item_id:
            raise STTIntegrityError("Final is not ready for Evidence acknowledgement")
        item = self._items[item_id]
        item.acknowledged = True
        item.final = None  # Retain only digest/metadata for duplicate detection.

    def close_capture(self, last_sequence: int) -> None:
        if last_sequence != self._next_sequence - 1:
            raise STTIntegrityError("capture stop does not match accepted audio")
        self._closed = True

    def drain(self) -> STTDrain:
        uncommitted = None
        if self._sample_end > self._committed_end:
            span = AudioRange(self._committed_end, self._sample_end)
            if self._has_signal(span):
                uncommitted = span
        return STTDrain(
            unresolved_item_ids=tuple(key for key, item in self._items.items()
                                      if not item.acknowledged or item.unresolved_empty
                                      or item.unresolved_failure),
            unclaimed_audio=tuple(self._unclaimed),
            uncommitted_audio=uncommitted,
            source_failure_codes=tuple(self._source_failures),
        )

    def _has_signal(self, span: AudioRange) -> bool:
        return any(start < span.end_sample and end > span.start_sample and signal
                   for start, end, signal in self._frames)
