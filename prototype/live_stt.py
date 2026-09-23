"""Provider boundary for the L2 Realtime transcription slice.

The rest of the Prototype sees only small runtime events.  OpenAI-specific
Realtime messages stay inside this module; they never become Canonical Events.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Protocol

from .live_audio import TARGET_SAMPLE_RATE
from .live_diagnostic import diagnostic
from .live_turns import TurnLedger

try:  # Imported lazily in production, but kept optional for unit tests.
    from websockets.asyncio.client import connect
except ImportError:  # pragma: no cover - exercised only before dependency install
    connect = None  # type: ignore[assignment]


DEFAULT_REALTIME_ENDPOINT = "wss://api.openai.com/v1/realtime?intent=transcription"
DEFAULT_STT_MODEL = "gpt-transcribe"
DEFAULT_STT_PROMPT = (
    "日本語の会議・打ち合わせの音声です。"
    "発話内容を忠実に文字起こしし、音声として確認できない内容を補完しないでください。"
)
DEFAULT_KEYWORDS = (
    "論路",
)
FINALIZATION_MODES = frozenset({"none", "server_vad", "semantic_vad", "bounded", "server_vad_bounded"})
_logger = logging.getLogger(__name__)
_TRACE_TYPES = frozenset({
    "input_audio_buffer.speech_started",
    "input_audio_buffer.speech_stopped",
    "input_audio_buffer.committed",
    "conversation.item.input_audio_transcription.completed",
    "conversation.item.input_audio_transcription.failed",
    "error",
})


class RealtimeSTTFailure(RuntimeError):
    """A failure at the provider boundary, safe to report without secrets."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class RealtimeSTTConfig:
    endpoint: str
    api_key: str | None
    model: str
    language: str
    prompt: str | None
    keywords: tuple[str, ...]
    timeout_seconds: float
    finalization_mode: str = "none"
    vad_threshold: float = 0.5
    vad_prefix_padding_ms: int = 300
    vad_silence_duration_ms: int = 500
    semantic_vad_eagerness: str = "auto"
    periodic_commit_seconds: float = 30.0

    @classmethod
    def from_environment(cls) -> "RealtimeSTTConfig":
        endpoint = (
            os.getenv("OPENAI_REALTIME_ENDPOINT")
            or os.getenv("REALTIME_TRANSCRIPTION_ENDPOINT")
            or DEFAULT_REALTIME_ENDPOINT
        )
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("STT_API_KEY")
        model = os.getenv("OPENAI_REALTIME_STT_MODEL") or os.getenv("LIVE_STT_MODEL") or DEFAULT_STT_MODEL
        language = os.getenv("OPENAI_REALTIME_LANGUAGE") or os.getenv("LIVE_STT_LANGUAGE") or "ja"
        prompt = os.getenv("OPENAI_REALTIME_PROMPT") or os.getenv("LIVE_STT_PROMPT") or DEFAULT_STT_PROMPT
        raw_keywords = os.getenv("OPENAI_REALTIME_KEYWORDS") or os.getenv("LIVE_STT_KEYWORDS")
        keywords = _parse_keywords(raw_keywords) if raw_keywords else DEFAULT_KEYWORDS
        timeout_raw = os.getenv("OPENAI_REALTIME_TIMEOUT_SECONDS") or os.getenv("LIVE_STT_TIMEOUT_SECONDS") or "45"
        try:
            timeout = float(timeout_raw)
        except ValueError:
            timeout = 45.0
        finalization_mode = _parse_finalization_mode(
            os.getenv("OPENAI_REALTIME_FINALIZATION_MODE")
            or os.getenv("LIVE_STT_FINALIZATION_MODE")
            or "none"
        )
        vad_threshold = _bounded_float(
            os.getenv("OPENAI_REALTIME_VAD_THRESHOLD")
            or os.getenv("LIVE_STT_VAD_THRESHOLD"),
            default=0.5,
            minimum=0.0,
            maximum=1.0,
        )
        vad_prefix_padding_ms = _positive_int(
            os.getenv("OPENAI_REALTIME_VAD_PREFIX_PADDING_MS")
            or os.getenv("LIVE_STT_VAD_PREFIX_PADDING_MS"),
            default=300,
        )
        vad_silence_duration_ms = _positive_int(
            os.getenv("OPENAI_REALTIME_VAD_SILENCE_DURATION_MS")
            or os.getenv("LIVE_STT_VAD_SILENCE_DURATION_MS"),
            default=500,
        )
        semantic_vad_eagerness = _parse_semantic_vad_eagerness(
            os.getenv("OPENAI_REALTIME_SEMANTIC_VAD_EAGERNESS")
            or os.getenv("LIVE_STT_SEMANTIC_VAD_EAGERNESS")
            or "auto"
        )
        periodic_commit_seconds = _positive_float(
            os.getenv("OPENAI_REALTIME_PERIODIC_COMMIT_SECONDS")
            or os.getenv("LIVE_STT_PERIODIC_COMMIT_SECONDS"),
            default=30.0,
        )
        return cls(
            endpoint=endpoint,
            api_key=api_key,
            model=model,
            language=language,
            prompt=prompt,
            keywords=tuple(keywords),
            timeout_seconds=max(1.0, timeout),
            finalization_mode=finalization_mode,
            vad_threshold=vad_threshold,
            vad_prefix_padding_ms=vad_prefix_padding_ms,
            vad_silence_duration_ms=vad_silence_duration_ms,
            semantic_vad_eagerness=semantic_vad_eagerness,
            periodic_commit_seconds=periodic_commit_seconds,
        )

    @property
    def configured(self) -> bool:
        return bool(self.endpoint and self.api_key and self.model)

    def public_dict(self) -> dict[str, Any]:
        """Safe runtime configuration summary; never includes the API key."""

        return {
            "endpoint": self.endpoint,
            "model": self.model,
            "language": self.language,
            "prompt_configured": bool(self.prompt),
            "keywords": list(self.keywords),
            "timeout_seconds": self.timeout_seconds,
            "finalization_mode": self.finalization_mode,
            "vad_threshold": self.vad_threshold,
            "vad_prefix_padding_ms": self.vad_prefix_padding_ms,
            "vad_silence_duration_ms": self.vad_silence_duration_ms,
            "semantic_vad_eagerness": self.semantic_vad_eagerness,
            "periodic_commit_seconds": self.periodic_commit_seconds,
            "configured": self.configured,
        }


def _parse_keywords(value: str) -> tuple[str, ...]:
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return tuple(str(item).strip() for item in parsed if str(item).strip())
    except json.JSONDecodeError:
        pass
    return tuple(item.strip() for item in value.replace("\n", ",").split(",") if item.strip())


def _positive_float(value: str | None, *, default: float) -> float:
    try:
        parsed = float(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return parsed if parsed > 0 else default


def _positive_int(value: str | None, *, default: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return parsed if parsed > 0 else default


def _bounded_float(value: str | None, *, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _parse_finalization_mode(value: str) -> str:
    normalized = str(value or "none").strip().lower()
    return normalized if normalized in FINALIZATION_MODES else "none"


def _parse_semantic_vad_eagerness(value: str) -> str:
    normalized = str(value or "auto").strip().lower()
    return normalized if normalized in {"auto", "low", "medium", "high"} else "auto"


def build_turn_detection(config: RealtimeSTTConfig) -> dict[str, Any] | None:
    """Build the provider turn detector without changing the default baseline."""

    if config.finalization_mode in {"server_vad", "server_vad_bounded"}:
        return {
            "type": "server_vad",
            "threshold": config.vad_threshold,
            "prefix_padding_ms": config.vad_prefix_padding_ms,
            "silence_duration_ms": config.vad_silence_duration_ms,
        }
    if config.finalization_mode == "semantic_vad":
        return {
            "type": "semantic_vad",
            "eagerness": config.semantic_vad_eagerness,
        }
    return None


def build_session_update(config: RealtimeSTTConfig) -> dict[str, Any]:
    """Build the dedicated transcription session configuration."""

    transcription: dict[str, Any] = {"model": config.model}
    if config.language:
        transcription["language"] = config.language
    if config.prompt:
        transcription["prompt"] = config.prompt
    if config.keywords:
        transcription["keywords"] = list(config.keywords)
    return {
        "type": "session.update",
        "session": {
            "type": "transcription",
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": TARGET_SAMPLE_RATE},
                    "transcription": transcription,
                    "turn_detection": build_turn_detection(config),
                }
            },
        },
    }


def build_append_event(pcm16le: bytes) -> dict[str, str]:
    import base64

    return {
        "type": "input_audio_buffer.append",
        "audio": base64.b64encode(pcm16le).decode("ascii"),
    }


def build_commit_event() -> dict[str, str]:
    return {"type": "input_audio_buffer.commit"}


def adapt_realtime_event(raw: Mapping[str, Any], *, seen_final_item_ids: set[str] | None = None) -> dict[str, Any]:
    """Map provider messages into the internal runtime event vocabulary."""

    event_type = raw.get("type")
    if event_type == "conversation.item.input_audio_transcription.delta":
        return {
            "type": "partial_transcript",
            "text": str(raw.get("delta", "")),
            "item_id": raw.get("item_id"),
            "event_id": raw.get("event_id"),
            "raw_type": event_type,
        }
    if event_type == "conversation.item.input_audio_transcription.completed":
        item_id = str(raw.get("item_id", ""))
        if seen_final_item_ids is not None and item_id and item_id in seen_final_item_ids:
            return {
                "type": "duplicate_final",
                "item_id": item_id,
                "event_id": raw.get("event_id"),
                "raw_type": event_type,
            }
        if seen_final_item_ids is not None and item_id:
            seen_final_item_ids.add(item_id)
        transcript = raw.get("transcript")
        if not isinstance(transcript, str) or not transcript.strip():
            return {
                "type": "stt_error",
                "code": "empty_final_transcript",
                "message": "Provider completed a turn without transcript text",
                "item_id": raw.get("item_id"),
                "event_id": raw.get("event_id"),
                "transcript_id": raw.get("transcript_id"),
                "commit_id": raw.get("commit_id"),
                "raw_type": event_type,
            }
        return {
            "type": "final_transcript",
            "text": transcript.strip(),
            "item_id": raw.get("item_id"),
            "event_id": raw.get("event_id"),
            "transcript_id": raw.get("transcript_id"),
            "commit_id": raw.get("commit_id"),
            "languages": raw.get("languages", []),
            "usage": raw.get("usage"),
            "raw_type": event_type,
        }
    if event_type == "error" or str(event_type).endswith(".error"):
        error = raw.get("error") if isinstance(raw.get("error"), Mapping) else {}
        return {
            "type": "stt_error",
            "code": str(error.get("code") or raw.get("code") or "provider_error"),
            "message": str(error.get("message") or raw.get("message") or "Realtime STT provider error"),
            "raw_type": event_type,
        }
    return {"type": "ignored", "raw_type": event_type}


class RealtimeTranscriptionClient(Protocol):
    async def connect(self) -> None:
        ...

    async def append_audio(self, pcm16le: bytes) -> None:
        ...

    async def commit(self) -> None:
        ...

    async def receive_until_final(self) -> list[dict[str, Any]]:
        ...

    async def close(self) -> None:
        ...


class OpenAIRealtimeTranscriptionClient:
    """Small backend-only WebSocket adapter for OpenAI Realtime STT."""

    def __init__(self, config: RealtimeSTTConfig) -> None:
        self.config = config
        self._connection: Any = None
        self._seen_final_item_ids: set[str] = set()
        # Local diagnostic identity.  This is intentionally distinct from any
        # provider identifier and is safe to expose in a private evaluation
        # artifact without persisting audio or credentials.
        self.connection_id = f"stt-conn-{uuid.uuid4().hex[:12]}"
        self._commit_sequence = 0
        self._last_boundary_reason = "session_start"
        self._last_boundary_event_id: str | None = None
        self._vad_boundary_seen = False
        self._vad_speech_active = False
        self._pending_vad_completions = 0
        self._provider_event_counts: dict[str, int] = {}
        self._trace_item_lifecycle = os.getenv("RONRO_STT_ITEM_TRACE") == "1"
        self.turns = TurnLedger('semantic_vad' if config.finalization_mode == 'semantic_vad' else 'server_vad')

    def _trace_lifecycle(self, kind: str, **fields: Any) -> None:
        if not self._trace_item_lifecycle:
            return
        try:
            _logger.warning("stt_item_lifecycle %s", json.dumps({
                "kind": kind, "connection_id": self.connection_id, **fields,
            }, ensure_ascii=False, separators=(",", ":")))
        except (TypeError, ValueError):
            # Opt-in diagnostics must not change Provider event handling.
            pass

    async def connect(self) -> None:
        if connect is None:  # pragma: no cover
            raise RealtimeSTTFailure("dependency_missing", "websockets is not installed")
        if not self.config.api_key:
            raise RealtimeSTTFailure("provider_not_configured", "OPENAI_API_KEY is not configured")
        try:
            self._connection = await asyncio.wait_for(
                connect(
                    self.config.endpoint,
                    additional_headers={"Authorization": f"Bearer {self.config.api_key}"},
                    max_size=16 * 1024 * 1024,
                ),
                timeout=self.config.timeout_seconds,
            )
            await self._send(build_session_update(self.config))
        except RealtimeSTTFailure:
            raise
        except Exception as exc:
            await self.close()
            raise RealtimeSTTFailure("provider_connection_failed", str(exc)) from exc

    async def _send(self, value: Mapping[str, Any]) -> None:
        if self._connection is None:
            raise RealtimeSTTFailure("provider_not_connected", "Realtime STT is not connected")
        try:
            await self._connection.send(json.dumps(value, ensure_ascii=False))
        except Exception as exc:
            raise RealtimeSTTFailure("provider_send_failed", str(exc)) from exc

    async def append_audio(self, pcm16le: bytes) -> None:
        if not pcm16le:
            return
        await self._send(build_append_event(pcm16le))
        self.turns.append(pcm16le)
        diagnostic("provider_append_sent", provider=self, samples=len(pcm16le)//2, duration=len(pcm16le)/48000)

    async def commit(self) -> None:
        self._commit_sequence += 1
        client_event_id = f'{self.connection_id}-commit-{self._commit_sequence}'
        self.turns.request(self._commit_sequence, self._last_boundary_reason, client_event_id)
        self._trace_lifecycle("explicit_commit_requested", event_id=client_event_id,
                              sequence=self._commit_sequence,
                              reason=self._last_boundary_reason,
                              audio_start=self.turns.intents[-1]['start'] / TARGET_SAMPLE_RATE,
                              audio_end=self.turns.intents[-1]['end'] / TARGET_SAMPLE_RATE)
        diagnostic("explicit_commit_attempt", provider=self, local_commit_sequence=self._commit_sequence)
        await self._send({**build_commit_event(), 'event_id': client_event_id})
        diagnostic("explicit_commit_sent", provider=self, local_commit_sequence=self._commit_sequence)

    def mark_boundary_reason(self, reason: str) -> None:
        """Attach a local, non-semantic reason to the next Final trace."""

        self._last_boundary_reason = str(reason)

    @property
    def vad_enabled(self) -> bool:
        return self.config.finalization_mode in {"server_vad", "semantic_vad", "server_vad_bounded"}

    def has_pending_vad_completion(self) -> bool:
        return self.turns.pending() or self.turns.meaningful(self.turns.cursor, self.turns.samples)

    def should_commit_bounded_fallback(
        self,
        *,
        has_audio_buffer: bool,
        meaningful_audio: bool,
    ) -> bool:
        """Guard the bounded fallback with the provider's VAD state.

        A loopback can contain non-zero device noise after a VAD turn has
        already completed.  Local PCM energy alone must not turn that trailing
        noise into an explicit commit against an already-empty provider
        buffer.  For non-VAD bounded mode, the existing local signal guard is
        sufficient.
        """

        if self.turns.frames:
            return (not self.turns.intents and
                    self.turns.meaningful(self.turns.cursor, self.turns.samples))
        if not has_audio_buffer or not meaningful_audio:
            return False
        if self.vad_enabled:
            return self._vad_speech_active
        return True

    def should_commit_at_session_end(
        self,
        *,
        has_audio_buffer: bool,
        meaningful_audio: bool,
    ) -> bool:
        """Return whether an explicit stop commit is still needed.

        VAD owns normal turn boundaries.  A session-end commit remains the
        fallback for speech that is still active, for a provider that has not
        emitted a VAD boundary yet, or for non-VAD mode.  Once a VAD boundary
        has completed and only trailing silence remains, sending another
        commit can produce an empty provider completion.
        """

        if self.turns.frames:
            return (not self.turns.intents and self.turns.samples > self.turns.cursor
                    and (not self.vad_enabled or
                         self.turns.meaningful(self.turns.cursor, self.turns.samples)))
        if self.config.finalization_mode == "bounded":
            return meaningful_audio
        if not self.vad_enabled:
            return has_audio_buffer
        if self._pending_vad_completions > 0:
            return False
        if meaningful_audio:
            return True
        if self._vad_speech_active:
            return has_audio_buffer
        if self._vad_boundary_seen:
            return False
        return meaningful_audio

    def diagnostic_context(self) -> dict[str, Any]:
        """Return non-secret local metadata for correlating provider events."""

        return {
            "connection_id": self.connection_id,
            "local_commit_sequence": self._commit_sequence,
            "finalization_mode": self.config.finalization_mode,
            "boundary_reason": self._last_boundary_reason,
            "boundary_event_id": self._last_boundary_event_id,
            "vad_boundary_seen": self._vad_boundary_seen,
            "vad_speech_active": self._vad_speech_active,
            "pending_vad_completions": self._pending_vad_completions,
            "provider_event_counts": dict(self._provider_event_counts),
        }

    async def receive_until_final(self) -> list[dict[str, Any]]:
        if self._connection is None:
            raise RealtimeSTTFailure("provider_not_connected", "Realtime STT is not connected")
        events: list[dict[str, Any]] = []
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.config.timeout_seconds
        while loop.time() < deadline:
            remaining = max(0.1, deadline - loop.time())
            try:
                runtime_event = await self.receive_event(timeout=remaining)
            except RealtimeSTTFailure as exc:
                if exc.code == "provider_timeout":
                    raise
                raise
            events.append(runtime_event)
            if runtime_event["type"] == "final_transcript":
                return events
            if runtime_event["type"] == "stt_error":
                return events
        raise RealtimeSTTFailure("provider_timeout", "Timed out waiting for final transcript")

    async def receive_event(self, *, timeout: float | None = None) -> dict[str, Any]:
        """Receive one provider message and map it to a runtime event.

        Continuous Mode uses one reader task for this method while the browser
        audio loop continues to append PCM.  One-Utterance Mode keeps using
        ``receive_until_final``.
        """

        if self.turns.ready:
            return self.turns.ready.popleft()
        if self._connection is None:
            raise RealtimeSTTFailure("provider_not_connected", "Realtime STT is not connected")
        try:
            recv = self._connection.recv()
            raw_value = await (asyncio.wait_for(recv, timeout=timeout) if timeout is not None else recv)
        except asyncio.TimeoutError as exc:
            raise RealtimeSTTFailure("provider_timeout", "Timed out waiting for provider event") from exc
        except Exception as exc:
            raise RealtimeSTTFailure("provider_receive_failed", str(exc)) from exc
        if isinstance(raw_value, bytes):
            return {"type": "ignored", "raw_type": "binary_provider_event"}
        try:
            raw = json.loads(raw_value)
        except (TypeError, json.JSONDecodeError) as exc:
            return {"type": "stt_error", "code": "malformed_provider_event", "message": str(exc)}
        if not isinstance(raw, Mapping):
            return {
                "type": "stt_error",
                "code": "malformed_provider_event",
                "message": "Provider event must be an object",
            }
        raw_type = raw.get("type")
        diagnostic("provider_receive", provider=self, raw=raw)
        self.turns.observe(raw)
        if raw_type in _TRACE_TYPES:
            fields = {k: raw.get(k) for k in (
                "event_id", "item_id", "previous_item_id", "audio_start_ms", "audio_end_ms"
            ) if raw.get(k) is not None}
            if raw_type == "conversation.item.input_audio_transcription.completed":
                transcript = raw.get("transcript")
                fields["transcript_empty"] = not isinstance(transcript, str) or not transcript.strip()
                fields["transcript_length"] = len(transcript) if isinstance(transcript, str) else None
                fields["turn"] = self.turns.context(raw.get("item_id"))
            elif raw_type == "error":
                error = raw.get("error") if isinstance(raw.get("error"), Mapping) else {}
                fields["error_code"] = error.get("code")
                fields["related_event_id"] = error.get("event_id")
            self._trace_lifecycle(str(raw_type), **fields)
        if raw_type:
            self._provider_event_counts[str(raw_type)] = self._provider_event_counts.get(str(raw_type), 0) + 1
        if raw_type in {"input_audio_buffer.speech_started", "input_audio_buffer.speech_stopped"}:
            self._last_boundary_event_id = str(raw.get("event_id")) if raw.get("event_id") else None
            if raw_type.endswith("speech_started"):
                self._vad_speech_active = True
                self._last_boundary_reason = "speech_started"
            else:
                self._vad_speech_active = False
                self._vad_boundary_seen = True
                self._pending_vad_completions += 1
                self._last_boundary_reason = (
                    "semantic_vad" if self.config.finalization_mode == "semantic_vad" else "server_vad"
                )
        runtime_event = adapt_realtime_event(raw, seen_final_item_ids=self._seen_final_item_ids)
        provider_error = raw.get('error') if isinstance(raw.get('error'), Mapping) else {}
        if raw_type == 'error' and provider_error.get('code') == 'input_audio_buffer_commit_empty':
            if self.turns.reconcile_empty_commit(provider_error.get('event_id')):
                runtime_event = dict(type='ignored', raw_type=raw_type, reason='commit_superseded_by_vad', event_id=raw.get('event_id'))
        item_id = raw.get("item_id")
        if raw_type == "conversation.item.input_audio_transcription.completed" and runtime_event.get("type") != "duplicate_final":
            context = self.turns.context(item_id)
            runtime_event['_turn'] = context
            if not context['range_known'] and runtime_event.get('type') == 'final_transcript':
                runtime_event = dict(type='stt_error', code='turn_correlation_failed',
                                     message='Provider item audio coverage is unknown or overlapping',
                                     item_id=item_id, event_id=raw.get('event_id'), _turn=context)
            runtime_event['_transport'] = {
                **self.diagnostic_context(),
                'boundary_reason': context['boundary_reason'],
                'boundary_event_id': context['boundary_event_id'],
                'local_commit_sequence': context['local_commit_sequence'],
            }
            if runtime_event.get('code') == 'empty_final_transcript':
                # Only a known, silent automatic item is benign. An explicit
                # or unknown region remains unsafe, regardless of other items.
                runtime_event['_benign_empty'] = (
                    context['range_known'] and not context['meaningful']
                    and context['boundary_reason'] in {'server_vad', 'semantic_vad'})
        if raw_type == "conversation.item.input_audio_transcription.completed":
            self._pending_vad_completions = max(0, self._pending_vad_completions - 1)
        if runtime_event.get("type") == "stt_error":
            runtime_event["item_id"] = raw.get("item_id")
            runtime_event["event_id"] = raw.get("event_id")
            runtime_event["transcript_id"] = raw.get("transcript_id")
            runtime_event["commit_id"] = raw.get("commit_id")
            runtime_event.setdefault("_transport", self.diagnostic_context())
        diagnostic("provider_adapted", provider=self, raw_type=raw_type, item_id=raw.get("item_id"), event_id=raw.get("event_id"), adapted_type=runtime_event.get("type"), code=runtime_event.get("code"), item_context=runtime_event.get('_turn'))
        if raw_type == "conversation.item.input_audio_transcription.completed" and runtime_event.get('type') != 'duplicate_final':
            return self.turns.complete(item_id, runtime_event)
        return runtime_event

    async def close(self) -> None:
        connection = self._connection
        self._connection = None
        if connection is not None:
            try:
                await connection.close()
            except Exception:
                pass
