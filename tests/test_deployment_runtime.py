from __future__ import annotations

import json
import os
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from prototype.app import DeveloperPrototypeApp
from prototype.errors import PrototypeError
from prototype.live_session import LiveSessionManager
from prototype.server import create_server


ROOT = Path(__file__).resolve().parents[1]


class NoopAnalyzer:
    provider_name = "test"
    model = "deployment-test"
    prompt_version = "analyzer-prompt-v4"

    def analyze(self, utterance, current_graph, recent_events):
        del utterance, current_graph, recent_events
        return []


class DeploymentRuntimeTests(unittest.TestCase):
    def test_http_live_snapshot_controller_contract_and_read_only_access(self) -> None:
        manager = LiveSessionManager(
            schema_dir=ROOT / "schemas",
            analyzer_factory=NoopAnalyzer,
        )
        app = DeveloperPrototypeApp(ROOT / "evaluation" / "fixtures", ROOT / "schemas")
        server = create_server(app, "127.0.0.1", 0, live_manager=manager, live_ws_port=18765)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        base = f"http://{host}:{port}"
        try:
            start_request = Request(
                f"{base}/api/live/start",
                data=json.dumps({"mode": "continuous", "controller_id": "phone-a"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(start_request, timeout=2) as response:
                started = json.loads(response.read().decode("utf-8"))
            session_id = started["live_state"]["session_id"]
            graph_revision = started["live_state"]["graph_revision"]

            with urlopen(f"{base}/api/live?controller_id=phone-a", timeout=2) as response:
                self.assertEqual(response.status, 200)
                owner_snapshot = json.loads(response.read().decode("utf-8"))
            self.assertEqual(owner_snapshot["live_state"]["session_id"], session_id)
            self.assertEqual(owner_snapshot["live_state"]["controller"]["status"], "owned_by_this_controller")

            with urlopen(f"{base}/api/live", timeout=2) as response:
                self.assertEqual(response.status, 200)
                anonymous_snapshot = json.loads(response.read().decode("utf-8"))
            self.assertEqual(anonymous_snapshot["live_state"]["session_id"], session_id)
            self.assertEqual(anonymous_snapshot["live_state"]["graph_revision"], graph_revision)
            self.assertEqual(anonymous_snapshot["live_state"]["controller"]["status"], "owned_by_other")

            with urlopen(f"{base}/api/live?controller_id=phone-b", timeout=2) as response:
                self.assertEqual(response.status, 200)
                other_snapshot = json.loads(response.read().decode("utf-8"))
            self.assertEqual(other_snapshot["live_state"]["controller"]["status"], "owned_by_other")
            self.assertEqual(other_snapshot["live_state"]["session_id"], session_id)
            self.assertEqual(manager.current().runtime_state, "starting")
            self.assertEqual(manager.current().snapshot()["live_state"]["graph_revision"], graph_revision)

            other_stop = Request(
                f"{base}/api/live/stop",
                data=json.dumps({"controller_id": "phone-b"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(HTTPError) as stop_error:
                urlopen(other_stop, timeout=2)
            self.assertEqual(stop_error.exception.code, 409)
            stop_error.exception.close()

            owner_stop = Request(
                f"{base}/api/live/stop",
                data=json.dumps({"controller_id": "phone-a"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(owner_stop, timeout=2) as response:
                self.assertEqual(response.status, 200)
            ended = manager.drain(timeout_seconds=0.5, allow_without_stt=True)
            self.assertEqual(ended["live_state"]["runtime_state"], "ended")
        finally:
            current = manager.current()
            if current is not None:
                current.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_controller_ownership_and_short_reconnect(self) -> None:
        manager = LiveSessionManager(
            schema_dir=ROOT / "schemas",
            analyzer_factory=NoopAnalyzer,
        )
        first = manager.start_mode("continuous", controller_id="phone-a")
        session_id = first["live_state"]["session_id"]
        self.assertEqual(first["live_state"]["controller"]["status"], "owned_by_this_controller")

        same_controller = manager.start_mode("continuous", controller_id="phone-a")
        self.assertEqual(same_controller["live_state"]["session_id"], session_id)

        with self.assertRaises(PrototypeError) as start_error:
            manager.start_mode("continuous", controller_id="phone-b")
        self.assertEqual(start_error.exception.code, "live_controller_owned")
        self.assertEqual(manager.snapshot_for_controller("phone-b")["live_state"]["controller"]["status"], "owned_by_other")

        with self.assertRaises(PrototypeError) as stop_error:
            manager.request_stop(controller_id="phone-b")
        self.assertEqual(stop_error.exception.code, "live_controller_owned")

        with self.assertRaises(PrototypeError) as command_error:
            manager.execute_command({"controller_id": "phone-b", "command_type": "correct_relation"})
        self.assertEqual(command_error.exception.code, "live_controller_owned")

        manager.mark_connected(controller_id="phone-a")
        manager.mark_controller_disconnected(controller_id="phone-a")
        self.assertEqual(manager.current().runtime_state, "starting")
        self.assertFalse(manager.current().transport_connected)
        manager.mark_connected(controller_id="phone-a")
        self.assertTrue(manager.current().transport_connected)
        manager.current().close()

    def test_shutdown_without_transport_drains_continuous_session(self) -> None:
        manager = LiveSessionManager(
            schema_dir=ROOT / "schemas",
            analyzer_factory=NoopAnalyzer,
        )
        manager.start_mode("continuous")
        snapshot = manager.shutdown_for_termination(timeout_seconds=0.5)
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["live_state"]["runtime_state"], "ended")
        self.assertTrue(snapshot["live_state"]["drain"]["complete"])
        current = manager.current()
        if current is not None:
            current.close()

    def test_health_readiness_and_forwarded_websocket_url(self) -> None:
        previous_key = os.environ.get("OPENAI_API_KEY")
        previous_model = os.environ.get("REAL_ANALYZER_MODEL")
        os.environ["OPENAI_API_KEY"] = "test-only-not-a-provider-call"
        os.environ["REAL_ANALYZER_MODEL"] = "gpt-5.6-luna"
        manager = LiveSessionManager(schema_dir=ROOT / "schemas", analyzer_factory=NoopAnalyzer)
        app = DeveloperPrototypeApp(ROOT / "evaluation" / "fixtures", ROOT / "schemas")
        server = create_server(app, "127.0.0.1", 0, live_manager=manager, live_ws_port=18765)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        base = f"http://{host}:{port}"
        try:
            with urlopen(f"{base}/healthz", timeout=2) as response:
                self.assertEqual(response.status, 200)
            with urlopen(f"{base}/readyz", timeout=2) as response:
                self.assertEqual(response.status, 200)
            request = Request(
                f"{base}/api/live/start",
                data=json.dumps({"mode": "one_utterance"}).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "X-Forwarded-Proto": "https",
                    "X-Forwarded-Host": "discussion-map-pilot.example.test",
                },
                method="POST",
            )
            with urlopen(request, timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["websocket_url"], "wss://discussion-map-pilot.example.test/live")
        finally:
            current = manager.current()
            if current is not None:
                current.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            if previous_key is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = previous_key
            if previous_model is None:
                os.environ.pop("REAL_ANALYZER_MODEL", None)
            else:
                os.environ["REAL_ANALYZER_MODEL"] = previous_model


if __name__ == "__main__":
    unittest.main()
