"""Minimal stdlib HTTP server for the Prototype 1 Analyzer Spike UI."""

from __future__ import annotations

import argparse
import json
import os
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from .app import DeveloperPrototypeApp
from .errors import PrototypeError
from .live_session import LiveSessionManager
from .live_transport import LiveWebSocketServer


ROOT = Path(__file__).resolve().parents[1]


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


class DeveloperRequestHandler(BaseHTTPRequestHandler):
    app: DeveloperPrototypeApp
    index_html: bytes
    shared_html: bytes
    session_html: bytes
    live_manager: LiveSessionManager | None = None
    live_worklet: bytes = b""
    readiness_check = staticmethod(lambda: True)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def _send(self, status: int, body: bytes, content_type: str = "application/json; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, exc: PrototypeError) -> None:
        status = 409 if exc.code in {"revision_mismatch", "live_controller_owned"} else 422
        self._send(status, _json_bytes({"error": exc.as_dict()}))

    def _websocket_url(self, controller_id: str | None = None) -> str:
        """Return a browser-reachable WebSocket URL.

        Local development keeps the historical two-port URL.  Behind an
        Ingress, the forwarded host/protocol and the same-origin ``/live``
        path are used so the browser never receives an internal Pod address
        or an insecure ``ws://`` URL from an HTTPS page.
        """

        configured = os.getenv("LIVE_PUBLIC_WEBSOCKET_URL")
        if configured:
            websocket_url = configured
        else:
            path = os.getenv("LIVE_WEBSOCKET_PATH", "/live")
            if not path.startswith("/"):
                path = f"/{path}"
            forwarded_proto = (self.headers.get("X-Forwarded-Proto") or "").split(",", 1)[0].strip().lower()
            forwarded_host = self.headers.get("X-Forwarded-Host") or self.headers.get("Host")
            if forwarded_proto and forwarded_host:
                scheme = "wss" if forwarded_proto == "https" else "ws"
                websocket_url = f"{scheme}://{forwarded_host}{path}"
            else:
                request_host = self.headers.get("Host", "").split(":", 1)[0].strip()
                host = request_host or str(self.server.server_address[0])
                websocket_url = f"ws://{host}:{getattr(self.server, 'live_ws_port', 8765)}{path}"
        if controller_id:
            separator = "&" if "?" in websocket_url else "?"
            websocket_url = f"{websocket_url}{separator}controller_id={quote(controller_id, safe='')}"
        return websocket_url

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/healthz":
                self._send(200, _json_bytes({"status": "ok"}))
                return
            if parsed.path == "/readyz":
                ready = bool(self.readiness_check())
                self._send(200 if ready else 503, _json_bytes({"status": "ready" if ready else "not_ready"}))
                return
            if parsed.path == "/":
                self._send(200, self.shared_html, "text/html; charset=utf-8")
                return
            if parsed.path == "/shared":
                self._send(200, self.shared_html, "text/html; charset=utf-8")
                return
            if parsed.path == "/control":
                self._send(200, self.index_html, "text/html; charset=utf-8")
                return
            if parsed.path == "/session":
                self._send(200, self.session_html, "text/html; charset=utf-8")
                return
            if parsed.path == "/static/live-audio-worklet.js":
                self._send(200, self.live_worklet, "text/javascript; charset=utf-8")
                return
            if parsed.path == "/api/live":
                if self.live_manager is None:
                    self._send(404, _json_bytes({"error": {"code": "live_disabled", "message": "Live Audio is not enabled"}}))
                else:
                    controller_id = parse_qs(parsed.query).get("controller_id", [None])[0]
                    self._send(200, _json_bytes(self.live_manager.snapshot_for_controller(controller_id)))
                return
            if parsed.path == "/api/live/evaluation":
                if self.live_manager is None:
                    self._send(404, _json_bytes({"error": {"code": "live_disabled", "message": "Live Audio is not enabled"}}))
                else:
                    self._send(200, _json_bytes({"evaluation": self.live_manager.evaluation_snapshot()}))
                return
            if parsed.path == "/api/fixtures":
                self._send(200, _json_bytes({"fixtures": self.app.list_fixtures()}))
                return
            prefix = "/api/sessions/"
            if parsed.path.startswith(prefix):
                fixture_id = unquote(parsed.path[len(prefix) :]).strip("/")
                values = parse_qs(parsed.query)
                sequence = values.get("sequence", [None])[0]
                mode = values.get("mode", ["events"])[0]
                runtime = self.app.handler_sessions.get(fixture_id)
                if sequence is not None or runtime is None or runtime.mode != mode:
                    self.app.reset_session(
                        fixture_id,
                        None if sequence is None else int(sequence),
                        mode=mode,
                    )
                self._send(200, _json_bytes(self.app.session_snapshot(fixture_id)))
                return
            self._send(404, _json_bytes({"error": {"code": "not_found", "message": "Not found"}}))
        except PrototypeError as exc:
            self._error(exc)
        except (ValueError, TypeError) as exc:
            self._send(400, _json_bytes({"error": {"code": "request_invalid", "message": str(exc)}}))

    def do_POST(self) -> None:  # noqa: N802
        evaluation_paths = {
            "/api/live/evaluation/start",
            "/api/live/evaluation/marker",
            "/api/live/evaluation/snapshot",
            "/api/live/evaluation/feedback",
            "/api/live/evaluation/observer-review",
            "/api/live/evaluation/golden",
            "/api/live/evaluation/end",
        }
        if self.path in evaluation_paths:
            if self.live_manager is None:
                self._send(404, _json_bytes({"error": {"code": "live_disabled", "message": "Live Audio is not enabled"}}))
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = {}
                if length:
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("Evaluation request body must be a JSON object")
                if self.path == "/api/live/evaluation/start":
                    result = self.live_manager.start_evaluation(payload)
                elif self.path == "/api/live/evaluation/marker":
                    result = self.live_manager.add_evaluation_marker(
                        str(payload.get("type", "")),
                        note=payload.get("note"),
                    )
                elif self.path == "/api/live/evaluation/snapshot":
                    result = self.live_manager.add_evaluation_periodic_snapshot(int(payload.get("minute")))
                elif self.path == "/api/live/evaluation/feedback":
                    result = self.live_manager.set_evaluation_feedback(payload)
                elif self.path == "/api/live/evaluation/observer-review":
                    result = self.live_manager.set_evaluation_observer_review(payload)
                elif self.path == "/api/live/evaluation/golden":
                    result = self.live_manager.set_evaluation_golden(payload)
                else:
                    result = self.live_manager.end_evaluation()
                self._send(200, _json_bytes(result))
            except PrototypeError as exc:
                self._error(exc)
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                self._send(400, _json_bytes({"error": {"code": "request_invalid", "message": str(exc)}}))
            return
        if self.path in {"/api/live/start", "/api/live/stop", "/api/live/retry", "/api/live/commands"}:
            if self.live_manager is None:
                self._send(404, _json_bytes({"error": {"code": "live_disabled", "message": "Live Audio is not enabled"}}))
                return
            try:
                if self.path == "/api/live/start":
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = {}
                    if length:
                        payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    mode = payload.get("mode", "one_utterance") if isinstance(payload, dict) else "one_utterance"
                    controller_id = payload.get("controller_id") if isinstance(payload, dict) else None
                    consented = payload.get("all_participants_consented", False) if isinstance(payload, dict) else False
                    snapshot = self.live_manager.start_mode(str(mode), controller_id=controller_id,
                                                            all_participants_consented=consented is True)
                    snapshot["websocket_url"] = self._websocket_url(controller_id=controller_id)
                elif self.path == "/api/live/stop":
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = {}
                    if length:
                        payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    controller_id = payload.get("controller_id") if isinstance(payload, dict) else None
                    snapshot = self.live_manager.request_stop(controller_id=controller_id)
                elif self.path == "/api/live/retry":
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = {}
                    if length:
                        payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    controller_id = payload.get("controller_id") if isinstance(payload, dict) else None
                    snapshot = self.live_manager.retry(controller_id=controller_id)
                else:
                    length = int(self.headers.get("Content-Length", "0"))
                    command = json.loads(self.rfile.read(length).decode("utf-8"))
                    snapshot = self.live_manager.execute_command(command)
                self._send(200, _json_bytes(snapshot))
            except PrototypeError as exc:
                self._error(exc)
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                self._send(400, _json_bytes({"error": {"code": "request_invalid", "message": str(exc)}}))
            return
        prefix = "/api/sessions/"
        parsed = urlparse(self.path)
        if not parsed.path.startswith(prefix):
            self._send(404, _json_bytes({"error": {"code": "not_found", "message": "Not found"}}))
            return
        suffix = parsed.path[len(prefix) :]
        if suffix.endswith("/transcript/step"):
            fixture_id = unquote(suffix[: -len("/transcript/step")]).strip("/")
            try:
                response = self.app.step_transcript(fixture_id)
                self._send(200, _json_bytes(response))
            except PrototypeError as exc:
                self._error(exc)
            return
        if suffix.endswith("/transcript/reset"):
            fixture_id = unquote(suffix[: -len("/transcript/reset")]).strip("/")
            try:
                values = parse_qs(parsed.query)
                mode = values.get("mode", ["transcript"])[0]
                response = self.app.reset_session(fixture_id, mode=mode)
                self._send(200, _json_bytes(response))
            except PrototypeError as exc:
                self._error(exc)
            return
        if not suffix.endswith("/commands"):
            self._send(404, _json_bytes({"error": {"code": "not_found", "message": "Not found"}}))
            return
        fixture_id = unquote(suffix[: -len("/commands")]).strip("/")
        try:
            length = int(self.headers.get("Content-Length", "0"))
            command = json.loads(self.rfile.read(length).decode("utf-8"))
            response = self.app.execute_command(fixture_id, command)
            self._send(200, _json_bytes(response))
        except PrototypeError as exc:
            self._error(exc)
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            self._send(400, _json_bytes({"error": {"code": "request_invalid", "message": str(exc)}}))


def create_server(
    app: DeveloperPrototypeApp,
    host: str = "127.0.0.1",
    port: int = 8000,
    *,
    live_manager: LiveSessionManager | None = None,
    live_ws_port: int = 8765,
) -> ThreadingHTTPServer:
    index_path = Path(__file__).resolve().parent / "web" / "index.html"
    shared_path = Path(__file__).resolve().parent / "web" / "shared.html"
    session_path = Path(__file__).resolve().parent / "web" / "session.html"
    worklet_path = Path(__file__).resolve().parent / "web" / "live-audio-worklet.js"
    handler_type = type(
        "BoundDeveloperRequestHandler",
        (DeveloperRequestHandler,),
        {
            "app": app,
            "index_html": index_path.read_bytes(),
            "shared_html": shared_path.read_bytes(),
            "session_html": session_path.read_bytes(),
            "live_manager": live_manager,
            "live_worklet": worklet_path.read_bytes(),
            "readiness_check": staticmethod(lambda: _runtime_ready(index_path, worklet_path, session_path, live_manager)),
        },
    )
    server = ThreadingHTTPServer((host, port), handler_type)
    server.live_ws_port = live_ws_port  # type: ignore[attr-defined]
    return server


def _runtime_ready(
    index_path: Path,
    worklet_path: Path,
    session_path: Path,
    live_manager: LiveSessionManager | None,
) -> bool:
    """Check local initialization only; never call an external provider."""

    api_key_configured = bool(
        os.getenv("OPENAI_API_KEY")
        or os.getenv("STT_API_KEY")
        or os.getenv("REAL_ANALYZER_API_KEY")
    )
    analyzer_model_configured = bool(os.getenv("REAL_ANALYZER_MODEL") or os.getenv("OPENAI_MODEL"))
    stt_model_configured = bool(
        os.getenv("OPENAI_REALTIME_STT_MODEL")
        or os.getenv("LIVE_STT_MODEL")
        or "gpt-transcribe"
    )
    return bool(
        live_manager is not None
        and index_path.is_file()
        and worklet_path.is_file()
        and session_path.is_file()
        and api_key_configured
        and analyzer_model_configured
        and stt_model_configured
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Discussion Map Prototype 1 Recorded Analyzer Spike UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--live-ws-port", type=int, default=8765)
    args = parser.parse_args()
    app = DeveloperPrototypeApp(ROOT / "evaluation" / "fixtures", ROOT / "schemas")
    evaluation_root = Path(os.getenv("EVALUATION_ROOT", str(ROOT / "evaluation" / "live" / "sessions")))
    evaluation_report_root = Path(os.getenv("EVALUATION_REPORT_ROOT", str(ROOT / "docs" / "evaluation")))
    live_manager = LiveSessionManager(
        schema_dir=ROOT / "schemas",
        dotenv_path=ROOT / ".env",
        evaluation_root=evaluation_root,
        evaluation_report_root=evaluation_report_root,
    )
    live_ws_server = LiveWebSocketServer(live_manager, host=args.host, port=args.live_ws_port)
    live_ws_server.start()
    server = create_server(
        app,
        args.host,
        args.port,
        live_manager=live_manager,
        live_ws_port=args.live_ws_port,
    )
    print(f"Recorded Analyzer Spike UI: http://{args.host}:{args.port}")
    print(f"Live Audio WebSocket: ws://{args.host}:{args.live_ws_port}/live")
    shutdown_requested = threading.Event()

    def request_shutdown(signum: int, _frame: object) -> None:
        if shutdown_requested.is_set():
            return
        shutdown_requested.set()
        print(f"Received signal {signum}; draining the active Live Session")
        live_manager.shutdown_for_termination(timeout_seconds=45.0)
        threading.Thread(target=server.shutdown, name="discussion-map-http-shutdown", daemon=True).start()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    try:
        server.serve_forever()
    finally:
        if not shutdown_requested.is_set():
            live_manager.shutdown_for_termination(timeout_seconds=45.0)
        live_manager.close()
        server.server_close()
        live_ws_server.close()


if __name__ == "__main__":
    main()
