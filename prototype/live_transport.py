"""Local Browser→Python WebSocket transport for the L1/L2 slice."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any
from urllib.parse import parse_qs, urlparse

from .live_audio import AudioFrameError, decode_audio_frame
from .live_diagnostic import diagnostic
from .errors import PrototypeError
from .live_session import LiveSessionManager
from .live_stt import OpenAIRealtimeTranscriptionClient, RealtimeSTTConfig, RealtimeSTTFailure

try:
    from websockets.asyncio.server import Server, ServerConnection, serve
except ImportError:  # pragma: no cover - dependency is declared in requirements-dev.txt
    Server = Any  # type: ignore[assignment,misc]
    ServerConnection = Any  # type: ignore[assignment,misc]
    serve = None  # type: ignore[assignment]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


_logger = logging.getLogger(__name__)


class LiveWebSocketGateway:
    """Handle L1/L2 one-turn and L4 continuous binary audio streams."""

    def __init__(self, manager: LiveSessionManager, *, stt_config: RealtimeSTTConfig | None = None) -> None:
        self.manager = manager
        self.stt_config = stt_config or RealtimeSTTConfig.from_environment()

    async def __call__(self, connection: ServerConnection) -> None:
        session = self.manager.current()
        if session is None:
            await connection.send(_json({"type": "error", "code": "live_session_missing", "message": "Start a Live session first"}))
            await connection.close()
            return
        provider: OpenAIRealtimeTranscriptionClient | None = None
        controller_id = self._controller_id_from_connection(connection)
        transport_failed = False
        try:
            snapshot = self.manager.mark_connected(controller_id=controller_id)
            await connection.send(_json({"type": "runtime_snapshot", "snapshot": snapshot}))
            provider = OpenAIRealtimeTranscriptionClient(self.stt_config)
            await provider.connect()
            diagnostic_context = getattr(provider, "diagnostic_context", None)
            if callable(diagnostic_context):
                self.manager.record_transport_diagnostics(diagnostic_context())
            await connection.send(_json({"type": "stt_connected", "config": self.stt_config.public_dict()}))
            if getattr(session, "mode", "one_utterance") == "continuous":
                snapshot = self.manager.activate()
                await connection.send(_json({"type": "live_active", "snapshot": snapshot}))
                await self._capture_continuous(connection, provider, controller_id=controller_id)
            else:
                await self._capture(connection, provider)
        except RealtimeSTTFailure as exc:
            transport_failed = True
            snapshot = self.manager.fail(exc.code, exc.message)
            await self._safe_send(connection, {"type": "error", "code": exc.code, "message": exc.message, "snapshot": snapshot})
        except PrototypeError as exc:
            await self._safe_send(connection, {"type": "error", "code": exc.code, "message": exc.message})
        except (AudioFrameError, ValueError, TypeError) as exc:
            transport_failed = True
            snapshot = self.manager.fail("audio_transport_error", str(exc))
            await self._safe_send(connection, {"type": "error", "code": "audio_transport_error", "message": str(exc), "snapshot": snapshot})
        except Exception as exc:  # Transport errors must not touch the Graph.
            transport_failed = True
            snapshot = self.manager.fail("live_transport_error", str(exc))
            await self._safe_send(connection, {"type": "error", "code": "live_transport_error", "message": str(exc), "snapshot": snapshot})
        finally:
            try:
                if provider is not None:
                    await provider.close()
            except Exception:
                pass
            session = self.manager.current()
            if session is not None and getattr(session, "mode", "one_utterance") == "continuous":
                if transport_failed and session.runtime_state in {"active", "starting", "finalizing"}:
                    try:
                        await asyncio.to_thread(self.manager.drain, allow_without_stt=True)
                    except Exception:
                        pass
                elif session.runtime_state in {"active", "starting", "finalizing"}:
                    # A browser/controller disconnect is recoverable. Keep
                    # the in-memory Session and Graph for the same controller.
                    self.manager.mark_controller_disconnected(controller_id=controller_id)
                await self._safe_send(connection, {"type": "runtime_snapshot", "snapshot": session.snapshot()})
            elif session is not None and session.runtime_state not in {"disconnected"}:
                session.runtime_state = "disconnected"
                session.stt_state = "disconnected"
                await self._safe_send(connection, {"type": "runtime_snapshot", "snapshot": session.snapshot()})

    async def _capture(self, connection: ServerConnection, provider: OpenAIRealtimeTranscriptionClient) -> None:
        while True:
            if self.manager.consume_stop_request():
                await self._commit_and_process_final(connection, provider)
                return
            try:
                message = await asyncio.wait_for(connection.recv(), timeout=0.2)
            except asyncio.TimeoutError:
                continue
            if message is None:
                return
            if not isinstance(message, bytes):
                control = self._parse_control_message(message)
                if control.get("type") == "audio_diagnostics":
                    track = control.get("track", {})
                    snapshot = self.manager.record_audio_diagnostics(track if isinstance(track, dict) else {})
                    await self._safe_send(connection, {"type": "audio_diagnostics_recorded", "snapshot": snapshot})
                else:
                    await self._safe_send(connection, {"type": "error", "code": "unexpected_control_message", "message": "Supported controls are audio_diagnostics"})
                continue
            chunk = decode_audio_frame(message)
            snapshot = self.manager.accept_chunk(chunk)
            await provider.append_audio(chunk.pcm16le)
            await self._safe_send(
                connection,
                {
                    "type": "audio_chunk_accepted",
                    "sequence": chunk.sequence,
                    "audio_end": chunk.audio_end_seconds,
                    "snapshot": snapshot,
                },
            )

    async def _commit_and_process_final(self, connection: ServerConnection, provider: OpenAIRealtimeTranscriptionClient) -> None:
        try:
            await provider.commit()
            await self._safe_send(connection, {"type": "stt_committing", "snapshot": self.manager.snapshot()})
            runtime_events = await provider.receive_until_final()
        except RealtimeSTTFailure as exc:
            snapshot = self.manager.fail(exc.code, exc.message)
            await self._safe_send(connection, {"type": "error", "code": exc.code, "message": exc.message, "snapshot": snapshot})
            return

        for event in runtime_events:
            event_type = event.get("type")
            if event_type == "partial_transcript":
                snapshot = self.manager.record_partial(str(event.get("text", "")))
                await self._safe_send(connection, {"type": "partial_transcript", "text": event.get("text", ""), "snapshot": snapshot})
            elif event_type == "duplicate_final":
                await self._safe_send(connection, {"type": "duplicate_final", "item_id": event.get("item_id")})
            elif event_type == "stt_error":
                snapshot = self.manager.fail(str(event.get("code", "provider_error")), str(event.get("message", "Provider error")))
                await self._safe_send(connection, {"type": "error", "code": event.get("code"), "message": event.get("message"), "snapshot": snapshot})
                return
            elif event_type == "final_transcript":
                await self._safe_send(connection, {"type": "final_transcript", "text": event["text"], "snapshot": self.manager.snapshot()})
                snapshot = self.manager.process_final(
                    raw_text=str(event["text"]),
                    item_id=event.get("item_id"),
                    provider_event=self._with_transport_diagnostics(event, provider),
                )
                await self._safe_send(connection, {"type": "live_complete", "snapshot": snapshot})
                return

    async def _capture_continuous(
        self,
        connection: ServerConnection,
        provider: OpenAIRealtimeTranscriptionClient,
        *,
        controller_id: str | None,
    ) -> None:
        """Run audio input and provider events concurrently until Drain."""

        provider_events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        reader_done = asyncio.Event()
        commit_pending = False
        pending_boundary_reason: str | None = None
        stop_seen = False

        async def read_provider() -> None:
            try:
                while not reader_done.is_set():
                    await provider_events.put(await provider.receive_event())
            except RealtimeSTTFailure as exc:
                await provider_events.put({"type": "stt_error", "code": exc.code, "message": exc.message})
            finally:
                reader_done.set()

        reader_task = asyncio.create_task(read_provider())
        try:
            while True:
                turns = getattr(provider, 'turns', None)
                if turns is not None:
                    current = self.manager.current()
                    if current.stt_state == 'error':
                        await self._drain_and_send(connection)
                        return
                    current.retire_committed_audio(turns.cursor / 24000)
                    commit_pending = bool(turns.intents)
                    if turns.expired(self.stt_config.timeout_seconds):
                        self.manager.fail('provider_item_timeout', 'An audio item did not resolve before its deadline')
                        await self._drain_and_send(connection)
                        return
                    if stop_seen and current.stt_state != 'error':
                        await self._request_continuous_commit(provider, connection, boundary_reason='session_end')
                        commit_pending = bool(turns.intents)
                        if not provider.has_pending_vad_completion():
                            self.manager.mark_stt_finalization_complete()
                diagnostic("transport_state", session=self.manager.current(), provider=provider, commit_pending=commit_pending, pending_boundary_reason=pending_boundary_reason, stop_seen=stop_seen)
                if self.manager.consume_stop_request() and not stop_seen:
                    stop_seen = True
                    commit_pending = await self._request_continuous_commit(
                        provider, connection, boundary_reason="session_end"
                    )
                    pending_boundary_reason = "session_end" if commit_pending else None
                    if not commit_pending and not self._provider_has_pending_vad_completion(provider):
                        self.manager.mark_stt_finalization_complete()

                if (
                    not stop_seen
                    and not commit_pending
                    and self.stt_config.finalization_mode in {"bounded", "server_vad_bounded"}
                ):
                    current = self.manager.current()
                    # Leading silence is retained for range accounting, but
                    # must not make the first speech frame immediately overdue.
                    bound_duration = (
                        current.audio_buffer_duration_seconds() if current is not None else 0.0
                    )
                    if turns is not None:
                        bound_duration = turns.meaningful_pending_seconds
                    meaningful_audio = bool(
                        current is not None
                        and getattr(current, "has_meaningful_audio_buffer", lambda: False)()
                    )
                    provider_decision = getattr(provider, "should_commit_bounded_fallback", None)
                    if callable(provider_decision):
                        should_commit = bool(
                            provider_decision(
                                has_audio_buffer=bool(current and current.has_audio_buffer()),
                                meaningful_audio=meaningful_audio,
                            )
                        )
                    else:
                        should_commit = meaningful_audio
                    if (
                        should_commit
                        and (turns is not None or not self._provider_has_pending_vad_completion(provider))
                        and bound_duration >= self.stt_config.periodic_commit_seconds
                    ):
                        diagnostic("bounded_fallback_fired", session=current, provider=provider, commit_pending=commit_pending, bounded_timer_armed=True, bounded_timer_age=bound_duration)
                        commit_pending = await self._request_continuous_commit(
                            provider, connection, boundary_reason="bounded_fallback"
                        )
                        pending_boundary_reason = "bounded_fallback" if commit_pending else None

                if stop_seen and self.manager.current() is not None:
                    current = self.manager.current()
                    state = current.snapshot()["live_state"] if current is not None else {}
                    if state.get("stt_state") in {"finalized", "error"} and not commit_pending:
                        await self._drain_and_send(connection)
                        return

                browser_task = asyncio.create_task(connection.recv())
                provider_task = asyncio.create_task(provider_events.get())
                done, pending = await asyncio.wait(
                    {browser_task, provider_task},
                    timeout=0.2,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                if not done:
                    await self._send_coalesced_render(connection)
                    continue

                if browser_task in done:
                    message = browser_task.result()
                    if message is None:
                        self.manager.mark_controller_disconnected(controller_id=controller_id)
                        return
                    if isinstance(message, bytes):
                        if stop_seen:
                            await self._safe_send(connection, {"type": "audio_after_stop", "message": "Audio ignored while finalizing"})
                        else:
                            chunk = decode_audio_frame(message)
                            snapshot = self.manager.accept_chunk(chunk)
                            await provider.append_audio(chunk.pcm16le)
                            await self._safe_send(
                                connection,
                                {
                                    "type": "audio_chunk_accepted",
                                    "sequence": chunk.sequence,
                                    "audio_end": chunk.audio_end_seconds,
                                    "snapshot": snapshot,
                                },
                            )
                    else:
                        control = self._parse_control_message(message)
                        control_type = control.get("type")
                        if control_type == "audio_diagnostics":
                            track = control.get("track", {})
                            snapshot = self.manager.record_audio_diagnostics(track if isinstance(track, dict) else {})
                            await self._safe_send(connection, {"type": "audio_diagnostics_recorded", "snapshot": snapshot})
                        elif control_type == "commit" and not stop_seen and not commit_pending:
                            commit_pending = await self._request_continuous_commit(
                                provider, connection, boundary_reason="explicit_commit"
                            )
                            pending_boundary_reason = "explicit_commit" if commit_pending else None
                        elif control_type == "stop" and not stop_seen:
                            self.manager.request_stop(controller_id=controller_id)
                            stop_seen = True
                            commit_pending = await self._request_continuous_commit(
                                provider, connection, boundary_reason="session_end"
                            )
                            pending_boundary_reason = "session_end" if commit_pending else None
                            if not commit_pending and not self._provider_has_pending_vad_completion(provider):
                                self.manager.mark_stt_finalization_complete()
                        elif control_type not in {"commit", "stop"}:
                            await self._safe_send(connection, {"type": "error", "code": "unexpected_control_message", "message": "Supported controls are audio_diagnostics, commit and stop"})

                if provider_task in done:
                    event = provider_task.result()
                    event_type = event.get("type")
                    diagnostic("application_handle", session=self.manager.current(), provider=provider, item_id=event.get("item_id"), event_id=event.get("event_id"), event_type=event_type, commit_pending=commit_pending, pending_boundary_reason=pending_boundary_reason, item_context=event.get('_turn'))
                    if event_type == "partial_transcript":
                        snapshot = self.manager.record_partial(str(event.get("text", "")))
                        await self._safe_send(connection, {"type": "partial_transcript", "text": event.get("text", ""), "snapshot": snapshot})
                    elif event_type == "duplicate_final":
                        await self._safe_send(connection, {"type": "duplicate_final", "item_id": event.get("item_id")})
                    elif event_type == "final_transcript":
                        snapshot = self.manager.process_final(
                            raw_text=str(event["text"]),
                            item_id=event.get("item_id"),
                            provider_event=self._with_transport_diagnostics(event, provider),
                        )
                        await self._safe_send(connection, {"type": "final_transcript", "text": event["text"], "snapshot": snapshot})
                        if turns is not None:
                            turns.acknowledge(event.get('item_id'))
                        had_commit = commit_pending
                        commit_pending = False
                        pending_boundary_reason = None
                        if stop_seen and ((had_commit and turns is None) or not self._provider_has_pending_vad_completion(provider)):
                            self.manager.mark_stt_finalization_complete()
                    elif event_type == "stt_error":
                        code = str(event.get("code", "provider_error"))
                        benign = event.get('_benign_empty') if turns is not None else self._is_benign_vad_empty_final(
                            provider,
                            code=code,
                            commit_pending=commit_pending,
                        )
                        if benign:
                            if turns is not None:
                                turns.acknowledge(event.get('item_id'))
                            commit_pending = False
                            pending_boundary_reason = None
                            current = self.manager.current()
                            record_empty = getattr(current, "record_empty_final_ignored", None)
                            if callable(record_empty):
                                record_empty()
                            if not self._provider_has_pending_vad_completion(provider):
                                self.manager.mark_stt_finalization_complete()
                            await self._safe_send(
                                connection,
                                {
                                    "type": "empty_final_ignored",
                                    "reason": "vad_shutdown_without_meaningful_pending_audio",
                                    "snapshot": self.manager.snapshot(),
                                },
                            )
                        else:
                            # Private server diagnostics only: the public
                            # snapshot intentionally omits Provider item IDs.
                            # Keep enough identity/range to distinguish an
                            # empty automatic VAD item from an explicit commit.
                            _logger.warning("unsafe_stt_event %s", _json({
                                "code": code,
                                "item_id": event.get("item_id"),
                                "event_id": event.get("event_id"),
                                "turn": event.get("_turn"),
                                "transport": event.get("_transport"),
                            }))
                            self.manager.fail(code, str(event.get("message", "Provider error")))
                            await self._safe_send(
                                connection,
                                {
                                    "type": "error",
                                    "code": event.get("code"),
                                    "message": event.get("message"),
                                    "provider_item_id": event.get("item_id"),
                                    "provider_event_id": event.get("event_id"),
                                    "provider_transcript_id": event.get("transcript_id"),
                                    "provider_commit_id": event.get("commit_id"),
                                    "transport_diagnostics": event.get("_transport"),
                                    "snapshot": self.manager.snapshot(),
                                },
                            )
                            stop_seen = True
                            commit_pending = False
                            pending_boundary_reason = None

                await self._send_coalesced_render(connection)
        finally:
            reader_done.set()
            reader_task.cancel()
            try:
                await reader_task
            except (asyncio.CancelledError, Exception):
                pass

    async def _request_continuous_commit(
        self,
        provider: OpenAIRealtimeTranscriptionClient,
        connection: ServerConnection,
        *,
        boundary_reason: str = "explicit_commit",
    ) -> bool:
        session = self.manager.current()
        if session is None:
            return False
        has_audio_buffer = bool(getattr(session, "has_audio_buffer", lambda: False)())
        meaningful_audio = bool(getattr(session, "has_meaningful_audio_buffer", lambda: False)())
        if boundary_reason == "session_end":
            provider_decision = getattr(provider, "should_commit_at_session_end", None)
            if callable(provider_decision):
                should_commit = bool(
                    provider_decision(
                        has_audio_buffer=has_audio_buffer,
                        meaningful_audio=meaningful_audio,
                    )
                )
            else:
                should_commit = has_audio_buffer
        elif boundary_reason == "bounded_fallback":
            provider_decision = getattr(provider, "should_commit_bounded_fallback", None)
            if callable(provider_decision):
                should_commit = bool(
                    provider_decision(
                        has_audio_buffer=has_audio_buffer,
                        meaningful_audio=meaningful_audio,
                    )
                )
            else:
                should_commit = meaningful_audio
        else:
            should_commit = has_audio_buffer
        if not should_commit:
            return False
        diagnostic("commit_requested", session=session, provider=provider, reason=boundary_reason)
        try:
            mark_boundary_reason = getattr(provider, "mark_boundary_reason", None)
            if callable(mark_boundary_reason):
                mark_boundary_reason(boundary_reason)
            await provider.commit()
            await self._safe_send(
                connection,
                {
                    "type": "stt_committing",
                    "boundary_reason": boundary_reason,
                    "snapshot": self.manager.snapshot(),
                },
            )
            return True
        except RealtimeSTTFailure as exc:
            self.manager.fail(exc.code, exc.message)
            await self._safe_send(connection, {"type": "error", "code": exc.code, "message": exc.message, "snapshot": self.manager.snapshot()})
            return False

    @staticmethod
    def _provider_has_pending_vad_completion(provider: OpenAIRealtimeTranscriptionClient) -> bool:
        value = getattr(provider, "has_pending_vad_completion", None)
        return bool(value()) if callable(value) else False

    @staticmethod
    def _is_benign_vad_empty_final(
        provider: OpenAIRealtimeTranscriptionClient,
        *,
        code: str,
        commit_pending: bool,
    ) -> bool:
        if code != "empty_final_transcript" or commit_pending:
            return False
        if not bool(getattr(provider, "vad_enabled", False)):
            return False
        # Automatic VAD completion can arrive after the next speech segment
        # has already started.  The current local PCM buffer therefore cannot
        # be used to classify that completed provider turn.  The absence of a
        # local commit is the reliable distinction here: explicit session-end
        # and bounded-fallback commits remain unsafe when they return empty.
        return True

    async def _drain_and_send(self, connection: ServerConnection, *, allow_without_stt: bool = False) -> None:
        snapshot = await asyncio.to_thread(self.manager.drain, allow_without_stt=allow_without_stt)
        await self._safe_send(connection, {"type": "session_ended", "snapshot": snapshot})

    @staticmethod
    def _with_transport_diagnostics(
        event: dict[str, Any],
        provider: OpenAIRealtimeTranscriptionClient,
    ) -> dict[str, Any]:
        value = dict(event)
        diagnostic_context = getattr(provider, "diagnostic_context", None)
        if callable(diagnostic_context) and '_transport' not in value:
            value["_transport"] = diagnostic_context()
        return value

    async def _send_coalesced_render(self, connection: ServerConnection) -> None:
        snapshot = self.manager.poll_render()
        if snapshot is not None:
            await self._safe_send(connection, {"type": "map_render", "snapshot": snapshot})

    @staticmethod
    def _parse_control_message(message: Any) -> dict[str, Any]:
        if not isinstance(message, str):
            return {}
        try:
            value = json.loads(message)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _controller_id_from_connection(connection: ServerConnection) -> str | None:
        request = getattr(connection, "request", None)
        path = getattr(request, "path", "") if request is not None else ""
        if not path:
            return None
        return parse_qs(urlparse(path).query).get("controller_id", [None])[0]

    @staticmethod
    async def _safe_send(connection: ServerConnection, value: Any) -> None:
        try:
            await connection.send(_json(value))
        except Exception:
            pass


class LiveWebSocketServer:
    """Run the small asyncio WebSocket listener beside the stdlib HTTP server."""

    def __init__(self, manager: LiveSessionManager, *, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.manager = manager
        self.host = host
        self.port = port
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._server: Server | None = None
        self._startup_error: Exception | None = None

    def start(self) -> None:
        if serve is None:  # pragma: no cover
            raise RuntimeError("websockets is not installed")
        self._thread = threading.Thread(target=self._run, name="discussion-map-live-ws", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5.0)
        if self._startup_error is not None:
            raise self._startup_error

    def _run(self) -> None:
        try:
            asyncio.run(self._serve())
        except Exception as exc:  # Surface startup errors to the HTTP process.
            self._startup_error = exc
            self._ready.set()

    async def _serve(self) -> None:
        gateway = LiveWebSocketGateway(self.manager)
        self._server = await serve(gateway, self.host, self.port, max_size=16 * 1024 * 1024)
        self._ready.set()
        await self._server.wait_closed()

    def close(self) -> None:
        server = self._server
        if server is None:
            return
        server.close()
