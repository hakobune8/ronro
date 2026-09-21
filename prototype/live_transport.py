"""Local Browser→Python WebSocket transport for the L1/L2 slice."""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any
from urllib.parse import parse_qs, urlparse

from .live_audio import AudioFrameError, decode_audio_frame
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
                await self._safe_send(connection, {"type": "error", "code": "unexpected_control_message", "message": "Audio WebSocket accepts binary audio frames only"})
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
                    provider_event=event,
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
                if self.manager.consume_stop_request() and not stop_seen:
                    stop_seen = True
                    commit_pending = await self._request_continuous_commit(provider, connection)
                    if not commit_pending:
                        self.manager.mark_stt_finalization_complete()

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
                        if control_type == "commit" and not stop_seen and not commit_pending:
                            commit_pending = await self._request_continuous_commit(provider, connection)
                        elif control_type == "stop" and not stop_seen:
                            self.manager.request_stop(controller_id=controller_id)
                            stop_seen = True
                            commit_pending = await self._request_continuous_commit(provider, connection)
                            if not commit_pending:
                                self.manager.mark_stt_finalization_complete()
                        elif control_type not in {"commit", "stop"}:
                            await self._safe_send(connection, {"type": "error", "code": "unexpected_control_message", "message": "Supported controls are commit and stop"})

                if provider_task in done:
                    event = provider_task.result()
                    event_type = event.get("type")
                    if event_type == "partial_transcript":
                        snapshot = self.manager.record_partial(str(event.get("text", "")))
                        await self._safe_send(connection, {"type": "partial_transcript", "text": event.get("text", ""), "snapshot": snapshot})
                    elif event_type == "duplicate_final":
                        await self._safe_send(connection, {"type": "duplicate_final", "item_id": event.get("item_id")})
                    elif event_type == "final_transcript":
                        snapshot = self.manager.process_final(
                            raw_text=str(event["text"]),
                            item_id=event.get("item_id"),
                            provider_event=event,
                        )
                        await self._safe_send(connection, {"type": "final_transcript", "text": event["text"], "snapshot": snapshot})
                        had_commit = commit_pending
                        commit_pending = False
                        if stop_seen and had_commit:
                            self.manager.mark_stt_finalization_complete()
                    elif event_type == "stt_error":
                        self.manager.fail(str(event.get("code", "provider_error")), str(event.get("message", "Provider error")))
                        await self._safe_send(connection, {"type": "error", "code": event.get("code"), "message": event.get("message"), "snapshot": self.manager.snapshot()})
                        stop_seen = True
                        commit_pending = False

                await self._send_coalesced_render(connection)
        finally:
            reader_done.set()
            reader_task.cancel()
            try:
                await reader_task
            except (asyncio.CancelledError, Exception):
                pass

    async def _request_continuous_commit(self, provider: OpenAIRealtimeTranscriptionClient, connection: ServerConnection) -> bool:
        session = self.manager.current()
        if session is None or not getattr(session, "has_audio_buffer", lambda: False)():
            return False
        try:
            await provider.commit()
            await self._safe_send(connection, {"type": "stt_committing", "snapshot": self.manager.snapshot()})
            return True
        except RealtimeSTTFailure as exc:
            self.manager.fail(exc.code, exc.message)
            await self._safe_send(connection, {"type": "error", "code": exc.code, "message": exc.message, "snapshot": self.manager.snapshot()})
            return False

    async def _drain_and_send(self, connection: ServerConnection, *, allow_without_stt: bool = False) -> None:
        snapshot = await asyncio.to_thread(self.manager.drain, allow_without_stt=allow_without_stt)
        await self._safe_send(connection, {"type": "session_ended", "snapshot": snapshot})

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
