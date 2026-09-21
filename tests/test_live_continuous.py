from __future__ import annotations

import asyncio
import copy
import json
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from prototype.analyzer import CandidateEvent
from prototype.errors import PrototypeError
from prototype.live_audio import AudioChunk, encode_audio_frame
from prototype.live_continuous import LiveContinuousSession
from prototype.live_session import LiveSessionManager
from prototype.live_stt import RealtimeSTTConfig
from prototype.live_transport import LiveWebSocketGateway
from prototype.replay import ReplayRunner, semantic_equal
from prototype.schema import SchemaValidator


ROOT = Path(__file__).resolve().parents[1]


class ContinuousAnalyzer:
    provider_name = "test"
    model = "continuous-test"
    prompt_version = "analyzer-prompt-v4"

    def __init__(self, *, delay: float = 0.0, fail_texts: set[str] | None = None) -> None:
        self.delay = delay
        self.fail_texts = set(fail_texts or ())
        self.calls: list[int] = []
        self.last_trace = None

    def analyze(self, utterance, current_graph, recent_events):
        del current_graph, recent_events
        if self.delay:
            time.sleep(self.delay)
        sequence = int(utterance["sequence"])
        self.calls.append(sequence)
        if utterance["text"] in self.fail_texts:
            self.last_trace = {
                "validation_error": {
                    "code": "provider_failure",
                    "message": "synthetic Analyzer failure",
                }
            }
            return []
        self.last_trace = None
        return [
            CandidateEvent(
                event_id=f"continuous:{utterance['session_id']}:{sequence}",
                session_id=utterance["session_id"],
                event_type="node_detected",
                occurred_at=utterance["ended_at"],
                source_evidence_ids=tuple(utterance["evidence_ids"]),
                payload={"node_type": "idea", "label": utterance["text"]},
            )
        ]


class FakeRealtimeProvider:
    def __init__(self, config):
        self.config = config
        self.events: asyncio.Queue[dict[str, object]] = asyncio.Queue()
        self.commits = 0

    async def connect(self):
        return None

    async def append_audio(self, pcm16le: bytes):
        assert pcm16le

    async def commit(self):
        self.commits += 1
        if self.commits == 1:
            await self.events.put({"type": "partial_transcript", "text": "Discussion Map"})
            await self.events.put({"type": "final_transcript", "text": "Discussion Mapを中心に進めましょう", "item_id": "fake-item-1"})

    async def receive_event(self):
        return await self.events.get()

    async def close(self):
        return None


class FakeConnection:
    def __init__(self):
        self.incoming: asyncio.Queue[bytes | str | None] = asyncio.Queue()
        self.sent: list[dict[str, object]] = []
        self.stop_enqueued = False

    async def recv(self):
        return await self.incoming.get()

    async def send(self, payload: str):
        event = json.loads(payload)
        self.sent.append(event)
        if event.get("type") == "final_transcript" and not self.stop_enqueued:
            self.stop_enqueued = True
            await self.incoming.put(json.dumps({"type": "stop"}))

    async def close(self):
        await self.incoming.put(None)


def make_session(
    analyzer: ContinuousAnalyzer | None = None,
    *,
    render_interval_seconds: float = 60.0,
    drain_timeout_seconds: float = 2.0,
) -> LiveContinuousSession:
    validator = SchemaValidator(ROOT / "schemas")
    runner = ReplayRunner(validator)
    return LiveContinuousSession(
        session_id=f"continuous-test-{id(analyzer)}",
        schema_validator=validator,
        replay_runner=runner,
        analyzer=analyzer or ContinuousAnalyzer(),
        render_interval_seconds=render_interval_seconds,
        drain_timeout_seconds=drain_timeout_seconds,
    )


def activate(session: LiveContinuousSession) -> None:
    session.mark_connected()
    session.activate()


def add_final(session: LiveContinuousSession, sequence: int, text: str) -> None:
    pcm = b"\x00\x00" * 240
    session.accept_audio_chunk(
        AudioChunk(
            sequence=sequence,
            audio_start_seconds=sequence / 10,
            pcm16le=pcm,
        )
    )
    session.process_final_transcript(raw_text=text, provider_event={"item_id": f"item-{sequence}"})


def wait_settled(session: LiveContinuousSession, count: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = session.snapshot()["live_state"]["queue"]
        if snapshot["completed"] + snapshot["failed"] >= count and snapshot["processing"] == 0:
            return
        time.sleep(0.005)
    raise AssertionError(f"Queue did not settle: {session.snapshot()['live_state']['queue']}")


class LiveContinuousSessionTests(unittest.TestCase):
    def tearDown(self) -> None:
        session = getattr(self, "session", None)
        if session is not None:
            session.close()

    def test_incremental_graph_updates_are_render_coalesced(self) -> None:
        self.session = make_session(render_interval_seconds=60.0)
        activate(self.session)
        initial_revision = self.session.state["graph"]["revision"]
        for sequence in range(3):
            add_final(self.session, sequence, f"idea-{sequence}")
        wait_settled(self.session, 3)

        live_state = self.session.snapshot()["live_state"]
        self.assertEqual(live_state["queue"]["completed"], 3)
        self.assertEqual(live_state["metrics"]["graph_update_count"], 3)
        self.assertEqual(live_state["rendered_revision"], initial_revision)
        self.assertTrue(live_state["render_pending"])
        self.assertEqual(live_state["render_status"], "Updating")

        rendered = self.session.render_now()["live_state"]
        self.assertEqual(rendered["rendered_revision"], rendered["graph_revision"])
        self.assertEqual(rendered["metrics"]["map_render_count"], 2)
        completed_item = rendered["queue"]["items"][-1]
        self.assertIsNotNone(completed_item["map_rendered_at"])
        self.assertIsNotNone(completed_item["end_to_end_seconds"])

    def test_human_command_renders_immediately(self) -> None:
        self.session = make_session()
        activate(self.session)
        add_final(self.session, 0, "料金体系")
        wait_settled(self.session, 1)
        node_id = self.session.state["graph"]["nodes"][0]["id"]
        revision = self.session.state["graph"]["revision"]
        result = self.session.execute_command(
            {
                "command_type": "rename_node",
                "node_id": node_id,
                "label": "料金モデル",
                "expected_revision": revision,
                "occurred_at": "2026-09-20T00:00:01Z",
            }
        )
        self.assertEqual(result["event"]["actor"], "human")
        live_state = result["snapshot"]["live_state"]
        self.assertEqual(live_state["rendered_revision"], live_state["graph_revision"])
        self.assertEqual(result["snapshot"]["state"]["graph"]["nodes"][0]["label"], "料金モデル")

    def test_stop_during_queue_drains_to_ended(self) -> None:
        self.session = make_session(ContinuousAnalyzer(delay=0.02), drain_timeout_seconds=3.0)
        activate(self.session)
        for sequence in range(10):
            add_final(self.session, sequence, f"burst-{sequence}")
        self.session.begin_stop()
        self.session.mark_stt_finalization_complete()
        snapshot = self.session.drain()
        live_state = snapshot["live_state"]
        self.assertEqual(live_state["runtime_state"], "ended")
        self.assertEqual(live_state["queue"]["pending"], 0)
        self.assertEqual(live_state["queue"]["processing"], 0)
        self.assertEqual(live_state["final_utterance_count"], 10)
        self.assertEqual(live_state["rendered_revision"], live_state["graph_revision"])
        self.assertTrue(snapshot["live_state"]["drain"]["complete"])
        self.assertIsNotNone(snapshot["live_state"]["metrics"]["drain_duration_seconds"])

    def test_drain_timeout_preserves_evidence_and_reports_incomplete(self) -> None:
        self.session = make_session(ContinuousAnalyzer(delay=0.2), drain_timeout_seconds=0.01)
        activate(self.session)
        add_final(self.session, 0, "slow")
        self.session.begin_stop()
        self.session.mark_stt_finalization_complete()
        snapshot = self.session.drain()
        live_state = snapshot["live_state"]
        self.assertEqual(live_state["runtime_state"], "ended_with_incomplete_processing")
        self.assertEqual(live_state["error"]["code"], "drain_timeout")
        self.assertEqual(len(snapshot["state"]["evidence"]), 1)
        self.assertFalse(live_state["drain"]["complete"])
        self.assertIsNotNone(live_state["metrics"]["drain_duration_seconds"])

    def test_failed_item_does_not_block_drain(self) -> None:
        self.session = make_session(ContinuousAnalyzer(fail_texts={"bad"}))
        activate(self.session)
        add_final(self.session, 0, "bad")
        add_final(self.session, 1, "good")
        wait_settled(self.session, 2)
        self.session.begin_stop()
        self.session.mark_stt_finalization_complete()
        snapshot = self.session.drain()
        live_state = snapshot["live_state"]
        self.assertEqual(live_state["runtime_state"], "ended")
        self.assertEqual(live_state["queue"]["failed"], 1)
        self.assertEqual(live_state["queue"]["completed"], 1)
        self.assertEqual(live_state["drain"]["failed_count"], 1)
        self.assertEqual(len(snapshot["state"]["evidence"]), 2)

    def test_finalizing_disables_new_human_mutations(self) -> None:
        self.session = make_session()
        activate(self.session)
        self.session.begin_stop()
        with self.assertRaises(PrototypeError) as context:
            self.session.execute_command({"command_type": "set_current_topic", "topic_id": "missing"})
        self.assertEqual(context.exception.code, "live_finalizing")

    def test_replay_of_continuous_events_is_deterministic(self) -> None:
        self.session = make_session()
        activate(self.session)
        for sequence in range(3):
            add_final(self.session, sequence, f"replay-{sequence}")
        wait_settled(self.session, 3)
        self.session.begin_stop()
        self.session.mark_stt_finalization_complete()
        snapshot = self.session.drain()
        replay = self.session.replay_runner.replay_events(
            session_id=self.session.session_id,
            evidence=snapshot["state"]["evidence"],
            utterances=snapshot["state"]["utterances"],
            events=snapshot["events"],
        )
        self.assertTrue(semantic_equal(replay.state, snapshot["state"]))

    def test_continuous_start_is_idempotent_and_retry_is_not_exposed(self) -> None:
        analyzer_factory = lambda: ContinuousAnalyzer()
        manager = LiveSessionManager(schema_dir=ROOT / "schemas", analyzer_factory=analyzer_factory)
        first = manager.start_mode("continuous")
        second = manager.start_mode("continuous")
        self.assertEqual(first["live_state"]["session_id"], second["live_state"]["session_id"])
        with self.assertRaises(PrototypeError) as context:
            manager.retry()
        self.assertEqual(context.exception.code, "live_retry_unsupported")
        current = manager.current()
        if current is not None:
            current.close()

    def test_ui_exposes_continuous_controls_and_revision_state(self) -> None:
        html = (ROOT / "prototype" / "web" / "index.html").read_text(encoding="utf-8")
        for text in ("live-start-continuous", "live-commit", "live-end", "rendered_revision", "session_ended"):
            self.assertIn(text, html)

    def test_continuous_websocket_transport_routes_final_and_drains(self) -> None:
        manager = LiveSessionManager(
            schema_dir=ROOT / "schemas",
            analyzer_factory=lambda: ContinuousAnalyzer(),
        )
        manager.start_mode("continuous")
        connection = FakeConnection()
        connection.incoming.put_nowait(encode_audio_frame(AudioChunk(0, 0.0, b"\x00\x00" * 240)))
        connection.incoming.put_nowait(json.dumps({"type": "commit"}))
        config = RealtimeSTTConfig(
            endpoint="wss://example.invalid/realtime",
            api_key="test-only",
            model="gpt-transcribe",
            language="ja",
            prompt="test",
            keywords=(),
            timeout_seconds=1.0,
        )

        async def run_gateway():
            gateway = LiveWebSocketGateway(manager, stt_config=config)
            with patch("prototype.live_transport.OpenAIRealtimeTranscriptionClient", FakeRealtimeProvider):
                await asyncio.wait_for(gateway(connection), timeout=2.0)

        asyncio.run(run_gateway())
        current = manager.current()
        self.assertIsNotNone(current)
        snapshot = current.snapshot()
        self.assertEqual(snapshot["live_state"]["runtime_state"], "ended")
        self.assertEqual(snapshot["live_state"]["final_utterance_count"], 1)
        self.assertEqual(snapshot["live_state"]["queue"]["completed"], 1)
        self.assertEqual(snapshot["live_state"]["rendered_revision"], snapshot["live_state"]["graph_revision"])
        self.assertIn("session_ended", [event.get("type") for event in connection.sent])
        current.close()


if __name__ == "__main__":
    unittest.main()
