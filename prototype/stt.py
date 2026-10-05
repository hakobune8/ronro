"""Recorded-audio STT boundary for the Recorded STT Spike.

The STT layer deliberately stops at Final Transcript Segments and normalized
utterances.  It does not call the Analyzer, Event Store, or Materializer.
Raw provider segments are retained in the returned result and in the
trace-oriented artifacts produced by the spike runner; the canonical Domain
Schema remains unchanged.
"""

from __future__ import annotations

import datetime as dt
import json
import mimetypes
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol


class STTFailure(RuntimeError):
    """A failure before a usable Final Transcript Segment was produced."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class RawSTTSegment:
    segment_id: str
    start: float
    end: float
    text: str
    speaker: str | None
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NormalizedUtterance:
    utterance_id: str
    sequence: int
    text: str
    speaker: str | None
    audio_start: float
    audio_end: float
    raw_segment_ids: tuple[str, ...]
    raw_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.utterance_id,
            "sequence": self.sequence,
            "text": self.text,
            "normalized_text": self.text,
            "raw_text": self.raw_text,
            "speaker": self.speaker,
            "audio_start": round(self.audio_start, 3),
            "audio_end": round(self.audio_end, 3),
            "raw_segment_ids": list(self.raw_segment_ids),
        }


@dataclass(frozen=True)
class STTResult:
    provider: str
    model: str
    response_format: str
    audio_path: str
    processing_ms: float
    raw_response: dict[str, Any]
    segments: tuple[RawSTTSegment, ...]
    diagnostics: tuple[dict[str, Any], ...] = ()

    def to_dict(self, *, include_raw_response: bool = True) -> dict[str, Any]:
        value = {
            "provider": self.provider,
            "model": self.model,
            "response_format": self.response_format,
            "audio_path": self.audio_path,
            "processing_ms": round(self.processing_ms, 3),
            "segments": [segment.to_dict() for segment in self.segments],
            "diagnostics": list(self.diagnostics),
        }
        if include_raw_response:
            value["raw_response"] = self.raw_response
        return value


def stt_result_from_dict(value: Mapping[str, Any]) -> STTResult:
    """Rehydrate a saved, redacted STT artifact without contacting a provider."""

    segments = tuple(
        RawSTTSegment(
            str(item["segment_id"]),
            float(item["start"]),
            float(item["end"]),
            str(item["text"]),
            str(item["speaker"]) if item.get("speaker") is not None else None,
            dict(item.get("raw", {})),
        )
        for item in value.get("segments", [])
    )
    return STTResult(
        provider=str(value.get("provider", "unknown")),
        model=str(value.get("model", "unknown")),
        response_format=str(value.get("response_format", "unknown")),
        audio_path=str(value.get("audio_path", "")),
        processing_ms=float(value.get("processing_ms", 0.0)),
        raw_response=dict(value.get("raw_response", {})),
        segments=segments,
        diagnostics=tuple(value.get("diagnostics", [])),
    )


class STTProvider(Protocol):
    provider_name: str
    model: str

    def transcribe(self, audio_path: Path, *, language: str = "ja") -> STTResult:
        ...


def _multipart_form(fields: list[tuple[str, str]], file_field: str, filename: str, content: bytes, content_type: str) -> tuple[bytes, str]:
    boundary = f"----codex-stt-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields:
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value.encode("utf-8"),
            b"\r\n",
        ])
    chunks.extend([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode(),
        f"Content-Type: {content_type}\r\n\r\n".encode(),
        content,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _transcriptions_endpoint(value: str | None) -> str | None:
    if not value:
        return None
    endpoint = value.rstrip("/")
    if endpoint.endswith("/audio/transcriptions"):
        return endpoint
    if endpoint.endswith("/chat/completions"):
        endpoint = endpoint[: -len("/chat/completions")]
    if endpoint.endswith("/v1"):
        return f"{endpoint}/audio/transcriptions"
    if endpoint.endswith("/audio"):
        return f"{endpoint}/transcriptions"
    return f"{endpoint}/audio/transcriptions"


class OpenAICompatibleTranscriber:
    """Minimal multipart adapter for an OpenAI-compatible transcription API."""

    provider_name = "openai"

    def __init__(
        self,
        *,
        endpoint: str | None,
        api_key: str | None,
        model: str = "gpt-4o-transcribe-diarize",
        timeout_seconds: float = 60.0,
        context_prompt: str | None = None,
        keywords: Iterable[str] = (),
    ) -> None:
        self.endpoint = _transcriptions_endpoint(endpoint)
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.context_prompt = context_prompt
        self.keywords = tuple(str(keyword) for keyword in keywords if str(keyword).strip())

    @classmethod
    def from_environment(cls) -> "OpenAICompatibleTranscriber":
        endpoint = (
            os.getenv("STT_ENDPOINT")
            or os.getenv("OPENAI_TRANSCRIPTIONS_URL")
            or os.getenv("OPENAI_BASE_URL")
            or ("https://api.openai.com/v1" if os.getenv("OPENAI_API_KEY") else None)
        )
        api_key = os.getenv("STT_API_KEY") or os.getenv("OPENAI_API_KEY")
        model = os.getenv("STT_MODEL") or os.getenv("OPENAI_STT_MODEL") or "gpt-4o-transcribe-diarize"
        timeout_raw = os.getenv("STT_TIMEOUT_SECONDS", "60")
        try:
            timeout = float(timeout_raw)
        except ValueError:
            timeout = 60.0
        return cls(endpoint=endpoint, api_key=api_key, model=model, timeout_seconds=timeout)

    @property
    def configured(self) -> bool:
        return bool(self.endpoint and self.api_key and self.model)

    @property
    def response_format(self) -> str:
        if "diarize" in self.model:
            return "diarized_json"
        # The current Transcription API exposes gpt-transcribe as a text/json
        # model.  It accepts prompt/keyword hints, but does not accept the
        # verbose_json + segment-timestamp combination used by the older
        # non-diarized path.  Recorded terminology runs add deterministic
        # audio-chunk offsets around this JSON response instead.
        if self.model == "gpt-transcribe":
            return "json"
        return "verbose_json"

    def transcribe(self, audio_path: Path, *, language: str = "ja") -> STTResult:
        if not self.endpoint:
            raise STTFailure("provider_not_configured", "STT endpoint is not configured")
        if not self.api_key:
            raise STTFailure("provider_not_configured", "STT API key is not configured")
        if not self.model:
            raise STTFailure("provider_not_configured", "STT model is not configured")
        try:
            content = audio_path.read_bytes()
        except OSError as exc:
            raise STTFailure("audio_read_failed", f"Unable to read audio file: {exc}") from exc
        content_type = mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream"
        fields = [
            ("model", self.model),
            ("language", language),
            ("response_format", self.response_format),
        ]
        if "diarize" in self.model:
            fields.append(("chunking_strategy", "auto"))
        elif self.response_format == "verbose_json":
            fields.append(("timestamp_granularities[]", "segment"))
        # The current OpenAI transcription API supports prompt / keyword hints
        # on gpt-transcribe.  gpt-4o-transcribe-diarize explicitly does not
        # support prompt, so never send these fields to the frozen baseline.
        if self.model == "gpt-transcribe":
            if self.context_prompt:
                fields.append(("prompt", self.context_prompt))
            fields.extend(("keyword[]", keyword) for keyword in self.keywords)
        body, multipart_type = _multipart_form(fields, "file", audio_path.name, content, content_type)
        request = urllib.request.Request(
            self.endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": multipart_type,
            },
            method="POST",
        )
        started = time.perf_counter()
        try:
            # The endpoint is operator-supplied configuration, not user input.
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:  # nosec B310
                raw_bytes = response.read()
        except urllib.error.HTTPError as exc:
            # Do not include request headers or the API key in diagnostics.
            body_preview = exc.read().decode("utf-8", errors="replace")[:500]
            raise STTFailure("provider_http_error", f"STT provider returned HTTP {exc.code}: {body_preview}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise STTFailure("provider_network_error", str(exc)) from exc
        elapsed_ms = (time.perf_counter() - started) * 1000
        try:
            response = json.loads(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise STTFailure("provider_output_invalid", f"STT provider returned invalid JSON: {exc}") from exc
        if not isinstance(response, dict):
            raise STTFailure("provider_output_invalid", "STT provider response must be an object")
        segments, diagnostics = parse_stt_response(response)
        return STTResult(
            provider=self.provider_name,
            model=self.model,
            response_format=self.response_format,
            audio_path=str(audio_path),
            processing_ms=elapsed_ms,
            raw_response=response,
            segments=tuple(segments),
            diagnostics=tuple(diagnostics),
        )


class StaticSTTProvider:
    """Test provider with a saved response; it never claims real STT quality."""

    provider_name = "static"

    def __init__(self, response: Mapping[str, Any], model: str = "static") -> None:
        self.response = dict(response)
        self.model = model

    def transcribe(self, audio_path: Path, *, language: str = "ja") -> STTResult:
        del language
        segments, diagnostics = parse_stt_response(self.response)
        return STTResult(
            provider=self.provider_name,
            model=self.model,
            response_format="static",
            audio_path=str(audio_path),
            processing_ms=0.0,
            raw_response=dict(self.response),
            segments=tuple(segments),
            diagnostics=tuple(diagnostics),
        )


def audio_duration_seconds(audio_path: Path) -> float:
    """Read duration using ffprobe, which is already used by the audio fixture builder."""

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise STTFailure("audio_duration_unavailable", "ffprobe is required for recorded STT chunking")
    try:
        value = subprocess.check_output(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
            text=True,
        ).strip()
        return float(value)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        raise STTFailure("audio_duration_unavailable", f"Unable to read audio duration: {exc}") from exc


def transcribe_recorded_audio(
    provider: STTProvider,
    audio_path: Path,
    *,
    chunk_seconds: float = 600.0,
    chunk_dir: Path | None = None,
) -> STTResult:
    """Transcribe a recorded file, splitting only when the provider requires it.

    Chunking is an evaluation transport detail.  Raw provider responses remain
    grouped by chunk, while returned segment offsets are absolute to the
    original audio so Evidence traceability does not depend on chunk IDs.
    """

    duration = audio_duration_seconds(audio_path)
    if duration <= chunk_seconds:
        return provider.transcribe(audio_path)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise STTFailure("audio_chunking_unavailable", "ffmpeg is required for recorded STT chunking")
    directory = chunk_dir or audio_path.parent / f"{audio_path.stem}-chunks"
    directory.mkdir(parents=True, exist_ok=True)
    chunks: list[dict[str, Any]] = []
    all_segments: list[RawSTTSegment] = []
    total_processing_ms = 0.0
    offset = 0.0
    chunk_index = 0
    while offset < duration - 0.01:
        chunk_duration = min(chunk_seconds, duration - offset)
        chunk_path = directory / f"chunk-{chunk_index:03d}.m4a"
        subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", f"{offset:.3f}", "-i", str(audio_path), "-t", f"{chunk_duration:.3f}", "-vn", "-c:a", "aac", "-b:a", "64k", str(chunk_path), "-y"],
            check=True,
        )
        result = provider.transcribe(chunk_path)
        total_processing_ms += result.processing_ms
        chunk_raw = {
            "chunk_index": chunk_index,
            "offset_seconds": round(offset, 3),
            "duration_seconds": round(chunk_duration, 3),
            "audio_path": str(chunk_path),
            "provider_response": result.raw_response,
            "diagnostics": list(result.diagnostics),
        }
        chunks.append(chunk_raw)
        for segment in result.segments:
            all_segments.append(
                RawSTTSegment(
                    segment_id=f"chunk-{chunk_index}:{segment.segment_id}",
                    start=segment.start + offset,
                    end=segment.end + offset,
                    text=segment.text,
                    speaker=segment.speaker,
                    raw={**segment.raw, "chunk_index": chunk_index, "chunk_offset_seconds": round(offset, 3)},
                )
            )
        offset += chunk_duration
        chunk_index += 1
    all_segments.sort(key=lambda item: (item.start, item.end, item.segment_id))
    return STTResult(
        provider=provider.provider_name,
        model=provider.model,
        response_format=getattr(provider, "response_format", "chunked"),
        audio_path=str(audio_path),
        processing_ms=total_processing_ms,
        raw_response={
            "chunked": True,
            "audio_duration_seconds": round(duration, 3),
            "chunk_seconds": chunk_seconds,
            "chunks": chunks,
        },
        segments=tuple(all_segments),
        diagnostics=(),
    )


def parse_stt_response(response: Mapping[str, Any]) -> tuple[list[RawSTTSegment], list[dict[str, Any]]]:
    diagnostics: list[dict[str, Any]] = []
    raw_segments = response.get("segments")
    if not isinstance(raw_segments, list):
        text = str(response.get("text", "")).strip()
        if text:
            duration = response.get("duration")
            try:
                end = float(duration) if duration is not None else 0.0
            except (TypeError, ValueError):
                end = 0.0
            raw_segments = [{"id": "segment-0001", "start": 0.0, "end": end, "text": text}]
            diagnostics.append({"code": "segments_missing", "severity": "warning", "message": "Response had text but no segments; created one trace segment."})
        else:
            diagnostics.append({"code": "empty_transcript", "severity": "error", "message": "STT response contained no text or segments."})
            raw_segments = []
    segments: list[RawSTTSegment] = []
    for index, raw in enumerate(raw_segments):
        if not isinstance(raw, Mapping):
            diagnostics.append({"code": "malformed_segment", "severity": "error", "index": index})
            continue
        text = str(raw.get("text", "")).strip()
        try:
            start = float(raw.get("start"))
            end = float(raw.get("end"))
        except (TypeError, ValueError):
            diagnostics.append({"code": "malformed_timestamp", "severity": "error", "index": index})
            continue
        if start < 0 or end < start:
            diagnostics.append({"code": "malformed_timestamp", "severity": "error", "index": index, "start": start, "end": end})
            continue
        if not text:
            diagnostics.append({"code": "empty_segment", "severity": "warning", "index": index})
            continue
        segment_id = str(raw.get("id", f"segment-{index + 1:04d}"))
        speaker_value = raw.get("speaker", raw.get("speaker_id"))
        speaker = str(speaker_value) if speaker_value is not None else None
        segments.append(RawSTTSegment(segment_id, start, end, text, speaker, dict(raw)))
    return segments, diagnostics


_TERMINAL_RE = re.compile(r"[。！？!?]$")


def _join_text(left: str, right: str) -> str:
    if not left:
        return right
    if not right:
        return left
    if right[0] in "、。！？!?」』)）":
        return left + right
    return left + right if re.search(r"[ぁ-んァ-ン一-龯]$", left) and re.match(r"[ぁ-んァ-ン一-龯]", right) else f"{left} {right}"


def normalize_segments(
    segments: Iterable[RawSTTSegment],
    *,
    silence_gap_seconds: float = 0.8,
    max_utterance_seconds: float = 20.0,
    id_prefix: str = "stt-utt",
) -> tuple[list[NormalizedUtterance], list[dict[str, Any]]]:
    """Merge final STT segments into deterministic Analyzer utterances.

    A punctuation boundary, speaker change, long silence, or duration cap
    prevents merging.  The raw segment IDs and exact raw text are retained so
    an Analyzer Event can be traced back to audio offsets without adding STT
    fields to the canonical Domain Schema.
    """

    diagnostics: list[dict[str, Any]] = []
    source_segments = list(segments)
    ordered = sorted(source_segments, key=lambda item: (item.start, item.end, item.segment_id))
    if source_segments != ordered:
        diagnostics.append({"code": "segments_reordered_by_timestamp", "severity": "warning"})
    deduped: list[RawSTTSegment] = []
    seen: set[tuple[float, float, str]] = set()
    for segment in ordered:
        key = (round(segment.start, 3), round(segment.end, 3), segment.text.strip())
        if key in seen:
            diagnostics.append({"code": "duplicate_segment", "severity": "warning", "segment_id": segment.segment_id})
            continue
        seen.add(key)
        deduped.append(segment)

    groups: list[list[RawSTTSegment]] = []
    for segment in deduped:
        if not groups:
            groups.append([segment])
            continue
        current = groups[-1]
        prior = current[-1]
        gap = max(0.0, segment.start - prior.end)
        duration = segment.end - current[0].start
        can_merge = (
            gap <= silence_gap_seconds
            and duration <= max_utterance_seconds
            and prior.speaker == segment.speaker
            and not _TERMINAL_RE.search(prior.text.strip())
        )
        if can_merge:
            current.append(segment)
        else:
            groups.append([segment])

    normalized: list[NormalizedUtterance] = []
    for index, group in enumerate(groups, start=1):
        text = ""
        for segment in group:
            text = _join_text(text, segment.text.strip())
        normalized.append(
            NormalizedUtterance(
                utterance_id=f"{id_prefix}-{index:04d}",
                sequence=index,
                text=text.strip(),
                speaker=group[0].speaker,
                audio_start=group[0].start,
                audio_end=group[-1].end,
                raw_segment_ids=tuple(segment.segment_id for segment in group),
                raw_text=" ".join(segment.text.strip() for segment in group),
            )
        )
    return normalized, diagnostics


def _parse_datetime(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def canonical_transcript_documents(
    normalized: Iterable[NormalizedUtterance],
    *,
    session_id: str,
    session_started_at: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert normalized utterances to existing Evidence/Utterance documents.

    The third return value is an STT-only trace sidecar.  It carries raw text,
    normalized text, segment IDs, and audio offsets that the strict canonical
    Evidence Schema intentionally does not model.
    """

    base = _parse_datetime(session_started_at)
    evidence: list[dict[str, Any]] = []
    utterances: list[dict[str, Any]] = []
    trace: list[dict[str, Any]] = []
    for item in normalized:
        evidence_id = f"{session_id}:evidence:{item.sequence:04d}"
        utterance_id = f"{session_id}:utterance:{item.sequence:04d}"
        started = base + dt.timedelta(seconds=item.audio_start)
        ended = base + dt.timedelta(seconds=item.audio_end)
        started_text = started.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        ended_text = ended.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        evidence.append({
            "id": evidence_id,
            "session_id": session_id,
            "sequence": item.sequence,
            "timestamp": started_text,
            "speaker": item.speaker,
            "text": item.text,
        })
        utterances.append({
            "id": utterance_id,
            "session_id": session_id,
            "sequence": item.sequence,
            "evidence_ids": [evidence_id],
            "text": item.text,
            "started_at": started_text,
            "ended_at": ended_text,
        })
        trace.append({
            "utterance_id": utterance_id,
            "evidence_id": evidence_id,
            "raw_segment_ids": list(item.raw_segment_ids),
            "audio_start": item.audio_start,
            "audio_end": item.audio_end,
            "speaker": item.speaker,
            "raw_text": item.raw_text,
            "normalized_text": item.text,
        })
    return evidence, utterances, trace


def _normalized_for_error_rate(value: str) -> str:
    return re.sub(r"[\s　]", "", value)


def character_error_rate(reference: str, hypothesis: str) -> float:
    """Return Japanese-friendly CER after whitespace normalization."""

    ref = list(_normalized_for_error_rate(reference))
    hyp = list(_normalized_for_error_rate(hypothesis))
    previous = list(range(len(hyp) + 1))
    for i, ref_char in enumerate(ref, start=1):
        current = [i]
        for j, hyp_char in enumerate(hyp, start=1):
            current.append(min(
                current[-1] + 1,
                previous[j] + 1,
                previous[j - 1] + (ref_char != hyp_char),
            ))
        previous = current
    return round(previous[-1] / max(1, len(ref)), 4)


def whitespace_word_error_rate(reference: str, hypothesis: str) -> float | None:
    """Return WER only when both texts have meaningful whitespace tokens.

    Japanese transcript text normally has no spaces, so returning ``None`` is
    more honest than presenting character tokens as words.  CER remains the
    primary lexical metric for this spike.
    """

    ref = reference.split()
    hyp = hypothesis.split()
    if len(ref) <= 1 or len(hyp) <= 1:
        return None
    previous = list(range(len(hyp) + 1))
    for i, ref_word in enumerate(ref, start=1):
        current = [i]
        for j, hyp_word in enumerate(hyp, start=1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (ref_word != hyp_word)))
        previous = current
    return round(previous[-1] / max(1, len(ref)), 4)
