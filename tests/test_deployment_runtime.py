from __future__ import annotations

import json
import os
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from prototype.app import DeveloperPrototypeApp
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
