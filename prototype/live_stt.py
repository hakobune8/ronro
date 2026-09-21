"""Provider boundary for the L2 Realtime transcription slice.

The rest of the Prototype sees only small runtime events.  OpenAI-specific
Realtime messages stay inside this module; they never become Canonical Events.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Protocol

from .live_audio import TARGET_SAMPLE_RATE

try:  # Imported lazily in production, but kept optional for unit tests.
    from websockets.asyncio.client import connect
except ImportError:  # pragma: no cover - exercised only before dependency install
    connect = None  # type: ignore[assignment]


DEFAULT_REALTIME_ENDPOINT = "wss://api.openai.com/v1/realtime?intent=transcription"
DEFAULT_STT_MODEL = "gpt-transcribe"
DEFAULT_STT_PROMPT = (
    "日本語の技術会議。Discussion Map AI FacilitatorのMVPについて、"
    "Discussion Map、Visual Artifact、Current Topic、STT、AI Analyzer、"
    "Candidate Decision、Open Item、Action Item、Parking Lotが話題になります。"
)
DEFAULT_KEYWORDS = (
    "Discussion Map",
    "MVP",
    "Visual Artifact",
    "Current Topic",
    "STT",
    "GPT-5.6 Luna",
    "Candidate Decision",
    "Open Item",
    "Action Item",
    "Parking Lot",
)


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
        return cls(
            endpoint=endpoint,
            api_key=api_key,
            model=model,
            language=language,
            prompt=prompt,
            keywords=tuple(keywords),
            timeout_seconds=max(1.0, timeout),
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
                    # L1/L2 uses explicit Stop → commit.  Server VAD is not
                    # needed for the one-utterance slice.
                    "turn_detection": None,
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
            "raw_type": event_type,
        }
    if event_type == "conversation.item.input_audio_transcription.completed":
        item_id = str(raw.get("item_id", ""))
        if seen_final_item_ids is not None and item_id and item_id in seen_final_item_ids:
            return {
                "type": "duplicate_final",
                "item_id": item_id,
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
                "raw_type": event_type,
            }
        return {
            "type": "final_transcript",
            "text": transcript.strip(),
            "item_id": raw.get("item_id"),
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

    async def commit(self) -> None:
        await self._send(build_commit_event())

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
        return adapt_realtime_event(raw, seen_final_item_ids=self._seen_final_item_ids)

    async def close(self) -> None:
        connection = self._connection
        self._connection = None
        if connection is not None:
            try:
                await connection.close()
            except Exception:
                pass
