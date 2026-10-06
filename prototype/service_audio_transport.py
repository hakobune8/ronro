"""Opt-in, loopback-only authenticated Service audio WebSocket candidate.

This does not replace the Pilot ``/live`` route. The candidate carries PCM
only in memory and records a frame receipt before sending it to STT. It is
not deployment-ready: real-browser, real-Provider, and Pod recovery gates remain.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .live_audio import AudioFrameError, decode_audio_frame
from .live_stt import OpenAIRealtimeTranscriptionClient, RealtimeSTTConfig, RealtimeSTTFailure
from .postgres_service_store import PostgresServiceStore
from .service_auth_http import _cookie_value
from .service_browser_security import COOKIE_NAME
from .service_errors import ServiceStoreError
from .service_identity_store import ServiceIdentityStore
from .service_owner_access import ServiceOwnerAccess
from .service_realtime_items import ServiceRealtimeItemIngestor

try:
    from websockets.asyncio.server import ServerConnection, serve
    from websockets.exceptions import ConnectionClosed
except ImportError:  # pragma: no cover - optional runtime dependency
    ServerConnection = Any  # type: ignore[assignment,misc]
    serve = None  # type: ignore[assignment]

    class ConnectionClosed(Exception):  # type: ignore[no-redef]
        pass


_AUDIO_PATH = re.compile(r"/api/service/sessions/([A-Za-z0-9_-]{1,128})/audio\Z")


class ServiceAudioGateway:
    """Authenticate every socket and hold a durable, renewable Capture lease."""

    def __init__(
        self, identity: ServiceIdentityStore, content: PostgresServiceStore,
        *, stt_config: RealtimeSTTConfig,
        provider_factory: Callable[[RealtimeSTTConfig], Any] = OpenAIRealtimeTranscriptionClient,
        contract_version: str = "v1",
    ) -> None:
        self.access = ServiceOwnerAccess(identity, content)
        self.content = content
        self.stt_config = stt_config
        self.provider_factory = provider_factory
        self.contract_version = contract_version
        self._occupied: set[tuple[str, int]] = set()

    @staticmethod
    def _single_header(headers: Any, name: str) -> str | None:
        values = headers.get_all(name)
        if len(values) > 1:
            raise ServiceStoreError("session_not_found", "Session not found")
        return values[0] if values else None

    @staticmethod
    def _stop_sequence(message: str) -> int:
        if len(message) > 256:
            raise ServiceStoreError("audio_stop_invalid", "Invalid Capture stop control")
        try:
            def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
                value: dict[str, Any] = {}
                for key, item in pairs:
                    if key in value:
                        raise ValueError("Duplicate stop control field")
                    value[key] = item
                return value

            control = json.loads(message, object_pairs_hook=unique)
        except (ValueError, TypeError) as exc:
            raise ServiceStoreError("audio_stop_invalid", "Invalid Capture stop control") from exc
        if (not isinstance(control, dict) or set(control) != {"type", "last_sequence"}
                or control["type"] != "capture_stop"
                or type(control["last_sequence"]) is not int
                or control["last_sequence"] < -1):
            raise ServiceStoreError("audio_stop_invalid", "Invalid Capture stop control")
        return control["last_sequence"]

    @staticmethod
    def _request_identity(connection: ServerConnection) -> tuple[str, int, str | None, str | None]:
        request = connection.request
        parsed = urlsplit(request.path)
        path = _AUDIO_PATH.fullmatch(parsed.path)
        try:
            query = parse_qs(parsed.query, max_num_fields=1)
            values = query["generation"]
            if (path is None or set(query) != {"generation"} or len(values) != 1
                    or not values[0].isascii() or not values[0].isdecimal()
                    or str(int(values[0])) != values[0] or int(values[0]) < 1):
                raise ValueError("Invalid audio route")
        except (KeyError, ValueError) as exc:
            raise ServiceStoreError("session_not_found", "Session not found") from exc
        if ServiceAudioGateway._single_header(request.headers, "Authorization") is not None:
            raise ServiceStoreError("session_not_found", "Session not found")
        return (
            path.group(1), int(values[0]),
            _cookie_value(ServiceAudioGateway._single_header(request.headers, "Cookie"), COOKIE_NAME),
            ServiceAudioGateway._single_header(request.headers, "Origin"),
        )

    async def __call__(self, connection: ServerConnection) -> None:
        try:
            session_id, generation, token, origin = self._request_identity(connection)
            owner = await asyncio.to_thread(
                self.access.audio_websocket, session_id=session_id,
                cookie_token=token, origin=origin,
            )
            await asyncio.to_thread(self.content.recover_expired_capture_lease, session_id)
            snapshot = await asyncio.to_thread(self.content.capture_snapshot, session_id, owner)
            if (snapshot["generation"] != generation
                    or snapshot["state"] not in {"resuming", "reconnecting"}):
                raise ServiceStoreError("stale_capture_generation", "Capture is not ready")
        except (ServiceStoreError, AttributeError, TypeError):
            await connection.close(code=1008, reason="Audio access denied")
            return
        lease = (session_id, generation)
        if lease in self._occupied:
            await connection.close(code=1008, reason="Audio access denied")
            return
        self._occupied.add(lease)
        provider: Any = None
        connection_id = uuid.uuid4().hex
        reader_task: asyncio.Task | None = None
        lease_task: asyncio.Task | None = None
        claimed = False
        try:
            await asyncio.to_thread(
                self.content.acquire_capture_lease,
                session_id, generation=generation, connection_id=connection_id,
            )
            claimed = True

            async def renew_lease() -> None:
                while True:
                    await asyncio.sleep(5)
                    await asyncio.to_thread(
                        self.content.renew_capture_lease,
                        session_id, generation=generation, connection_id=connection_id,
                    )

            lease_task = asyncio.create_task(renew_lease())

            def ensure_lease_healthy() -> None:
                if lease_task is not None and lease_task.done():
                    lease_task.result()

            provider = self.provider_factory(self.stt_config)
            await provider.connect()
            ensure_lease_healthy()
            # Authentication or the Capture generation may have changed while
            # the Provider connection was being established.
            await asyncio.to_thread(
                self.access.audio_websocket, session_id=session_id,
                cookie_token=token, origin=origin,
            )
            await asyncio.to_thread(
                self.content.acknowledge_capture_transition,
                session_id, generation=generation, event="connected",
                connection_id=connection_id,
            )
            ingestor = ServiceRealtimeItemIngestor(
                self.content, session_id=session_id, generation=generation,
                audio_connection_id=connection_id,
                contract_version=self.contract_version,
            )
            await connection.send(json.dumps({
                "type": "capture_ready", "generation": generation,
            }))
            provider_events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

            async def read_provider() -> None:
                try:
                    while True:
                        await provider_events.put(await provider.receive_event())
                except asyncio.CancelledError:
                    raise
                except Exception:
                    await provider_events.put({
                        "type": "stt_error", "code": "provider_connection_interrupted",
                    })

            async def handle_provider(event: dict[str, Any]) -> None:
                ensure_lease_healthy()
                await asyncio.to_thread(
                    self.content.renew_capture_lease,
                    session_id, generation=generation, connection_id=connection_id,
                )
                if (event.get("type") == "stt_error"
                        and event.get("raw_type") != "conversation.item.input_audio_transcription.completed"):
                    raise ServiceStoreError("provider_connection_interrupted", "Provider interrupted")
                outcome = await asyncio.to_thread(ingestor.process, event)
                if outcome and outcome["type"] == "final_accepted":
                    turns = getattr(provider, "turns", None)
                    if turns is not None:
                        turns.acknowledge(event.get("item_id"))
                    await connection.send(json.dumps({
                        "type": "final_accepted", "sequence": outcome["sequence"],
                    }))
                elif outcome and outcome.get("status") in {"empty", "coverage_unknown"}:
                    turns = getattr(provider, "turns", None)
                    if (turns is not None and
                            event.get("raw_type") == "conversation.item.input_audio_transcription.completed"):
                        turns.acknowledge(event.get("item_id"))
                    await connection.send(json.dumps({
                        "type": "possible_evidence_gap", "reason": outcome["status"],
                    }))

            async def settle_pause() -> bool:
                turns = getattr(provider, "turns", None)
                if turns is None:
                    return False
                if turns.meaningful_pending_seconds > 0:
                    decide = getattr(provider, "should_commit_at_session_end", None)
                    if not callable(decide) or not decide(
                        has_audio_buffer=turns.samples > turns.cursor,
                        meaningful_audio=True,
                    ):
                        return False
                    await asyncio.to_thread(
                        self.content.renew_capture_lease,
                        session_id, generation=generation, connection_id=connection_id,
                    )
                    provider.mark_boundary_reason("pause")
                    await provider.commit()
                deadline = time.monotonic() + self.stt_config.timeout_seconds
                while turns.pending() or provider.has_pending_vad_completion():
                    ensure_lease_healthy()
                    await asyncio.to_thread(
                        self.access.audio_websocket, session_id=session_id,
                        cookie_token=token, origin=origin,
                    )
                    current = await asyncio.to_thread(
                        self.content.capture_snapshot, session_id, owner,
                    )
                    if current["generation"] != generation or current["state"] != "pausing":
                        return False
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return False
                    try:
                        event = await asyncio.wait_for(
                            provider_events.get(), timeout=min(remaining, 0.2),
                        )
                    except asyncio.TimeoutError:
                        continue
                    await handle_provider(event)
                return True

            reader_task = asyncio.create_task(read_provider())
            pause_deadline: float | None = None
            while True:
                ensure_lease_healthy()
                # Recheck the cookie and owner as well as generation, even in
                # long silence; revocation must not wait for another frame.
                await asyncio.to_thread(
                    self.access.audio_websocket, session_id=session_id,
                    cookie_token=token, origin=origin,
                )
                snapshot = await asyncio.to_thread(self.content.capture_snapshot, session_id, owner)
                if snapshot["generation"] != generation:
                    break
                if snapshot["state"] not in {"listening", "pausing"}:
                    break
                if snapshot["state"] == "pausing":
                    if pause_deadline is None:
                        pause_deadline = time.monotonic() + self.stt_config.timeout_seconds
                    if time.monotonic() >= pause_deadline:
                        break
                else:
                    pause_deadline = None
                browser_task = asyncio.create_task(connection.recv())
                event_task = asyncio.create_task(provider_events.get())
                done, pending = await asyncio.wait(
                    {browser_task, event_task},
                    timeout=(min(0.2, max(0.0, pause_deadline - time.monotonic()))
                             if pause_deadline is not None else 0.2),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
                stop_requested = False
                if browser_task in done:
                    message = browser_task.result()
                    if isinstance(message, str):
                        if snapshot["state"] != "pausing":
                            raise ServiceStoreError("audio_stop_invalid", "Capture is not pausing")
                        expected = self._stop_sequence(message)
                        actual = await asyncio.to_thread(
                            self.content.capture_stream_tail,
                            session_id, generation=generation, connection_id=connection_id,
                            require_lease=True,
                        )
                        if expected != actual:
                            raise ServiceStoreError(
                                "audio_stop_sequence_mismatch", "Capture stop does not match frames"
                            )
                        stop_requested = True
                    elif isinstance(message, bytes):
                        chunk = decode_audio_frame(message)
                        receipt = await asyncio.to_thread(
                            self.content.record_capture_frame_receipt,
                            session_id, generation=generation,
                            connection_id=connection_id, chunk=chunk, require_lease=True,
                        )
                        if receipt["created"]:
                            try:
                                await provider.append_audio(chunk.pcm16le)
                            except Exception as exc:
                                await asyncio.to_thread(
                                    self.content.record_provider_append_uncertain,
                                    session_id, generation=generation,
                                    connection_id=connection_id, frame_sequence=chunk.sequence,
                                )
                                raise RealtimeSTTFailure(
                                    "provider_append_unverified", "Provider audio append was not verified"
                                ) from exc
                        await connection.send(json.dumps({
                            "type": "frame_received", "sequence": chunk.sequence,
                            "created": receipt["created"],
                        }))
                    else:
                        raise ServiceStoreError("audio_frame_invalid", "Invalid Capture message")
                if event_task in done:
                    await handle_provider(event_task.result())
                if stop_requested:
                    if await settle_pause():
                        await asyncio.to_thread(
                            self.content.acknowledge_capture_transition,
                            session_id, generation=generation, event="paused",
                            connection_id=connection_id,
                        )
                        await connection.send(json.dumps({
                            "type": "capture_paused", "generation": generation,
                        }))
                    break
                turns = getattr(provider, "turns", None)
                if (turns is not None
                        and self.stt_config.finalization_mode in {"bounded", "server_vad_bounded"}
                        and turns.meaningful_pending_seconds >= self.stt_config.periodic_commit_seconds
                        and provider.should_commit_bounded_fallback(
                            has_audio_buffer=turns.samples > turns.cursor,
                            meaningful_audio=True,
                        )):
                    await asyncio.to_thread(
                        self.content.renew_capture_lease,
                        session_id, generation=generation, connection_id=connection_id,
                    )
                    provider.mark_boundary_reason("bounded_fallback")
                    await provider.commit()
        except ConnectionClosed:
            pass
        except (ServiceStoreError, AudioFrameError, RealtimeSTTFailure):
            # The durable Capture ledger retains the interruption. Do not log
            # credential, PCM, transcript, or Provider exception text here.
            pass
        except Exception:
            # Never let an unexpected Provider/transport exception body enter
            # the WebSocket server log. The generation is fenced below.
            pass
        finally:
            if lease_task is not None:
                lease_task.cancel()
                await asyncio.gather(lease_task, return_exceptions=True)
            if reader_task is not None:
                reader_task.cancel()
                await asyncio.gather(reader_task, return_exceptions=True)
            if provider is not None:
                try:
                    await provider.close()
                except Exception:
                    pass
            try:
                snapshot = await asyncio.to_thread(self.content.capture_snapshot, session_id, owner)
                if (claimed and snapshot["generation"] == generation
                        and snapshot["state"] in {"listening", "resuming", "pausing"}):
                    await asyncio.to_thread(
                        self.content.acknowledge_capture_transition,
                        session_id, generation=generation, event="disconnected",
                        connection_id=connection_id,
                    )
            except ServiceStoreError:
                pass
            self._occupied.discard(lease)
            await connection.close()


async def serve_service_audio_candidate(
    gateway: ServiceAudioGateway, *, host: str = "127.0.0.1", port: int = 0,
):
    """Bind only the isolated local candidate; never expose the Pilot port."""

    if host not in {"127.0.0.1", "::1"}:
        raise ValueError("Service audio candidate may bind only to loopback")
    if serve is None:
        raise RuntimeError("websockets is not installed")
    return await serve(gateway, host, port, max_size=256 * 1024)
