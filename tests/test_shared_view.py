from __future__ import annotations

import copy
import json
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from prototype.app import DeveloperPrototypeApp
from prototype.live_session import LiveSessionManager
from prototype.projection import build_presentation_projection
from prototype.server import create_server


ROOT = Path(__file__).resolve().parents[1]
LONG_SESSION_RUN = ROOT / "evaluation" / "30min" / "run-gpt-5.6-luna-analyzer-prompt-v4-20260919"


class SharedViewTests(unittest.TestCase):
    def test_shared_view_is_a_separate_read_only_surface(self) -> None:
        html = (ROOT / "prototype" / "web" / "shared.html").read_text(encoding="utf-8")
        for required in (
            "論路",
            "論点図",
            "今話していること",
            "決定候補",
            "まだ確定ではありません",
            "未解決事項",
            "次の対応",
            "話の流れ",
            "flow-item.ellipsis",
            "fetchLive",
        ):
            self.assertIn(required, html)
        for forbidden in (
            "Discussion Map",
            "DiscussionMap",
            "data-command",
            "/commands",
            "Confirm Decision",
            "queue depth",
            "Revision",
            "Event Log",
            "<button",
            "<input",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, html)

    def test_shared_view_readability_uses_fixed_large_type_and_content_budgets(self) -> None:
        html = (ROOT / "prototype" / "web" / "shared.html").read_text(encoding="utf-8")
        self.assertNotIn("clamp(", html)
        for required in (
            "font-size: 60px",
            "font-size: 24px",
            "font-size: 22px",
            "font-size: 20px",
            "font-size: 18px",
            "shared.slots.map",
            "font-size: 40px",
            "確定事項",
            "＋ほか${remaining}件",
            "topic-more",
        ):
            with self.subTest(required=required):
                self.assertIn(required, html)

    def test_shared_route_serves_read_only_html(self) -> None:
        manager = LiveSessionManager(schema_dir=ROOT / "schemas")
        app = DeveloperPrototypeApp(ROOT / "evaluation" / "fixtures", ROOT / "schemas")
        server = create_server(app, "127.0.0.1", 0, live_manager=manager, live_ws_port=18766)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        try:
            with urlopen(f"http://{host}:{port}/shared?fixture=pilot-shared&sequence=10", timeout=2) as response:
                body = response.read().decode("utf-8")
                self.assertEqual(response.status, 200)
                self.assertIn("論路", body)
                self.assertIn("論点図", body)
                self.assertIn("今話していること", body)
                self.assertIn("決定候補", body)
                self.assertNotIn("決まりそうなこと", body)
                self.assertNotIn("Discussion Map", body)
        finally:
            current = manager.current()
            if current is not None:
                current.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_primary_control_and_mobile_routes_have_separate_responsibilities(self) -> None:
        manager = LiveSessionManager(schema_dir=ROOT / "schemas")
        app = DeveloperPrototypeApp(ROOT / "evaluation" / "fixtures", ROOT / "schemas")
        server = create_server(app, "127.0.0.1", 0, live_manager=manager, live_ws_port=18767)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        try:
            for path in ("/", "/shared"):
                with urlopen(f"http://{host}:{port}{path}", timeout=2) as response:
                    body = response.read().decode("utf-8")
                    self.assertEqual(response.status, 200)
                    self.assertIn("論点図", body)
                    self.assertNotIn("Start Continuous", body)
                    self.assertNotIn("<button", body)
            with urlopen(f"http://{host}:{port}/control", timeout=2) as response:
                body = response.read().decode("utf-8")
                self.assertEqual(response.status, 200)
                self.assertIn("Start Continuous", body)
            with urlopen(f"http://{host}:{port}/session", timeout=2) as response:
                body = response.read().decode("utf-8")
                self.assertEqual(response.status, 200)
                self.assertIn("会議をはじめる", body)
                self.assertIn("getUserMedia", body)
                self.assertNotIn("Start Continuous", body)
        finally:
            current = manager.current()
            if current is not None:
                current.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_pilot_shared_scenario_uses_meaningful_labels_and_topic_return(self) -> None:
        app = DeveloperPrototypeApp(ROOT / "evaluation" / "fixtures", ROOT / "schemas")
        snapshot = app.reset_session("pilot-shared", through_sequence=48)
        graph = snapshot["state"]["graph"]
        labels = {node["label"] for node in graph["nodes"]}
        self.assertIn("パイロットをどう評価するか", labels)
        self.assertIn("Pilot #1を実施する", labels)
        self.assertNotIn("主要な観点 6", labels)
        self.assertNotIn("方針候補 1", labels)
        self.assertEqual(
            [item["label"] for item in snapshot["map"]["recent_flow"]][-5:],
            ["画像生成の扱い", "MVPで何を実現するか", "料金と運用", "MVPで何を実現するか", "パイロットをどう評価するか"],
        )

    @unittest.skipUnless(LONG_SESSION_RUN.is_dir(), "private 30-minute evaluation artifact is excluded from the public tree")
    def test_shared_projection_inputs_do_not_mutate_graph(self) -> None:
        graph = json.loads(
            (ROOT / "evaluation" / "30min" / "run-gpt-5.6-luna-analyzer-prompt-v4-20260919" / "run-off.json").read_text(
                encoding="utf-8"
            )
        )["final_graph"]
        recording = json.loads(
            (ROOT / "evaluation" / "30min" / "run-gpt-5.6-luna-analyzer-prompt-v4-20260919" / "normal-analyzer-recording.json").read_text(
                encoding="utf-8"
            )
        )
        events = [event for record in recording for event in record["events"]]
        original = copy.deepcopy(graph)
        projection = build_presentation_projection(graph, events)
        self.assertTrue(projection["presentation_only"])
        self.assertEqual(graph, original)


if __name__ == "__main__":
    unittest.main()
