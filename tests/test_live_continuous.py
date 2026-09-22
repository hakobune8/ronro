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


class FakeVADProvider(FakeRealtimeProvider):
    """Small provider double for VAD/end-of-session sequencing tests."""

    vad_enabled = True

    def __init__(
        self,
        config,
        *,
        auto_final: str | None = None,
        empty_after_final: bool = False,
        commit_final: str | None = None,
        commit_empty: bool = False,
    ):
        super().__init__(config)
        self.auto_final = auto_final
        self.empty_after_final = empty_after_final
        self.commit_final = commit_final
        self.commit_empty = commit_empty
        self.boundary_reason = "server_vad"
        self.vad_speech_active = True
        self._seeded = False

    async def append_audio(self, pcm16le: bytes):
        assert pcm16le
        if self._seeded or self.auto_final is None:
            return
        self._seeded = True
        await self.events.put({"type": "final_transcript", "text": self.auto_final, "item_id": "vad-item-1"})
        if self.empty_after_final:
            await self.events.put({"type": "stt_error", "code": "empty_final_transcript", "message": "empty VAD completion"})

    async def commit(self):
        self.commits += 1
        if self.commit_empty:
            await self.events.put({"type": "stt_error", "code": "empty_final_transcript", "message": "empty commit"})
        elif self.commit_final is not None:
            await self.events.put({"type": "final_transcript", "text": self.commit_final, "item_id": f"commit-item-{self.commits}"})

    def mark_boundary_reason(self, reason: str) -> None:
        self.boundary_reason = reason

    def diagnostic_context(self):
        return {
            "connection_id": "fake-vad-connection",
            "local_commit_sequence": self.commits,
            "finalization_mode": self.config.finalization_mode,
            "boundary_reason": self.boundary_reason,
            "boundary_event_id": "fake-vad-event",
        }

    def should_commit_at_session_end(self, *, has_audio_buffer: bool, meaningful_audio: bool) -> bool:
        return meaningful_audio

    def should_commit_bounded_fallback(self, *, has_audio_buffer: bool, meaningful_audio: bool) -> bool:
        return has_audio_buffer and meaningful_audio and self.vad_speech_active

    def has_pending_vad_completion(self) -> bool:
        return False


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

    def test_audio_and_provider_metadata_are_correlated_without_raw_audio(self) -> None:
        self.session = make_session()
        activate(self.session)
        self.session.record_audio_diagnostics(
            {
                "track_label": "BlackHole 2ch",
                "kind": "audio",
                "ready_state": "live",
                "muted": False,
                "enabled": True,
                "sample_rate": 48_000,
                "channel_count": 2,
                "device_id_present": True,
                "device_id": "must-not-be-retained",
            }
        )
        self.session.record_transport_diagnostics({"connection_id": "stt-conn-test"})
        self.session.accept_audio_chunk(
            AudioChunk(sequence=0, audio_start_seconds=0.0, pcm16le=b"\x00\x00" * 240)
        )
        snapshot = self.session.process_final_transcript(
            raw_text="音声経路を確認します",
            item_id="item-7",
            provider_event={
                "type": "final_transcript",
                "item_id": "item-7",
                "event_id": "evt-7",
                "transcript_id": "transcript-7",
                "commit_id": "provider-commit-7",
                "_transport": {"connection_id": "stt-conn-test", "local_commit_sequence": 1},
            },
        )
        trace = snapshot["live_state"]["evidence_traces"][0]
        self.assertEqual(trace["audio_connection_id"], "stt-conn-test")
        self.assertEqual(trace["audio_frame_sequence_start"], 0)
        self.assertEqual(trace["audio_frame_sequence_end"], 0)
        self.assertEqual(trace["provider_item_id"], "item-7")
        self.assertEqual(trace["provider_event_id"], "evt-7")
        self.assertEqual(trace["provider_transcript_id"], "transcript-7")
        self.assertEqual(trace["provider_commit_id"], "provider-commit-7")
        self.assertEqual(trace["local_commit_sequence"], 1)
        self.assertNotIn("device_id", snapshot["live_state"]["audio_diagnostics"])

    def test_audio_buffer_duration_is_available_without_exposing_audio(self) -> None:
        self.session = make_session()
        activate(self.session)
        self.session.accept_audio_chunk(
            AudioChunk(sequence=0, audio_start_seconds=12.0, pcm16le=b"\x00\x00" * 2_400)
        )
        self.assertAlmostEqual(self.session.audio_buffer_duration_seconds(), 0.1)

    def test_meaningful_audio_guard_and_max_unfinalized_duration(self) -> None:
        self.session = make_session()
        activate(self.session)
        self.session.accept_audio_chunk(
            AudioChunk(sequence=0, audio_start_seconds=0.0, pcm16le=b"\x10\x00" * 2_400)
        )
        self.session.accept_audio_chunk(
            AudioChunk(sequence=1, audio_start_seconds=0.1, pcm16le=b"\x00\x00" * 2_400)
        )
        self.assertTrue(self.session.has_meaningful_audio_buffer())
        self.assertAlmostEqual(self.session.audio_buffer_duration_seconds(), 0.2)
        self.assertAlmostEqual(self.session.metrics()["max_unfinalized_audio_seconds"], 0.2)
        self.session.process_final_transcript(raw_text="音声を確認します")
        self.assertFalse(self.session.has_meaningful_audio_buffer())
        self.assertAlmostEqual(self.session.audio_buffer_duration_seconds(), 0.0)

    def test_evidence_keeps_finalization_boundary_reason(self) -> None:
        self.session = make_session()
        activate(self.session)
        self.session.accept_audio_chunk(
            AudioChunk(sequence=0, audio_start_seconds=0.0, pcm16le=b"\x10\x00" * 240)
        )
        snapshot = self.session.process_final_transcript(
            raw_text="音声を確認します",
            provider_event={
                "item_id": "item-boundary",
                "_transport": {
                    "connection_id": "stt-conn-boundary",
                    "local_commit_sequence": 1,
                    "boundary_reason": "bounded_fallback",
                    "boundary_event_id": "evt-boundary",
                    "finalization_mode": "server_vad_bounded",
                },
            },
        )
        trace = snapshot["live_state"]["evidence_traces"][0]
        self.assertEqual(trace["boundary_reason"], "bounded_fallback")
        self.assertEqual(trace["boundary_event_id"], "evt-boundary")
        self.assertEqual(trace["finalization_mode"], "server_vad_bounded")

    def test_bounded_mode_requests_a_periodic_commit_without_ui_control(self) -> None:
        manager = LiveSessionManager(
            schema_dir=ROOT / "schemas",
            analyzer_factory=lambda: ContinuousAnalyzer(),
        )
        manager.start_mode("continuous")
        connection = FakeConnection()
        connection.incoming.put_nowait(encode_audio_frame(AudioChunk(0, 0.0, b"\x10\x00" * 240)))
        config = RealtimeSTTConfig(
            endpoint="wss://example.invalid/realtime",
            api_key="test-only",
            model="gpt-transcribe",
            language="ja",
            prompt="test",
            keywords=(),
            timeout_seconds=1.0,
            finalization_mode="bounded",
            periodic_commit_seconds=0.005,
        )

        async def run_gateway():
            gateway = LiveWebSocketGateway(manager, stt_config=config)
            with patch("prototype.live_transport.OpenAIRealtimeTranscriptionClient", FakeRealtimeProvider):
                await asyncio.wait_for(gateway(connection), timeout=2.0)

        asyncio.run(run_gateway())
        current = manager.current()
        self.assertIsNotNone(current)
        snapshot = current.snapshot()
        self.assertEqual(snapshot["live_state"]["final_utterance_count"], 1)
        self.assertTrue(any(event.get("type") == "stt_committing" for event in connection.sent))
        current.close()

    def test_server_vad_end_does_not_recommit_after_vad_final(self) -> None:
        manager = LiveSessionManager(schema_dir=ROOT / "schemas", analyzer_factory=lambda: ContinuousAnalyzer())
        manager.start_mode("continuous")
        connection = FakeConnection()
        connection.incoming.put_nowait(encode_audio_frame(AudioChunk(0, 0.0, b"\x10\x00" * 240)))
        config = RealtimeSTTConfig(
            endpoint="wss://example.invalid/realtime",
            api_key="test-only",
            model="gpt-transcribe",
            language="ja",
            prompt="test",
            keywords=(),
            timeout_seconds=1.0,
            finalization_mode="server_vad",
        )

        async def run_gateway():
            gateway = LiveWebSocketGateway(manager, stt_config=config)
            with patch("prototype.live_transport.OpenAIRealtimeTranscriptionClient", lambda cfg: FakeVADProvider(cfg, auto_final="VADで確定した発話です")):
                await asyncio.wait_for(gateway(connection), timeout=2.0)

        asyncio.run(run_gateway())
        current = manager.current()
        self.assertIsNotNone(current)
        snapshot = current.snapshot()
        self.assertEqual(snapshot["live_state"]["runtime_state"], "ended")
        self.assertEqual(snapshot["live_state"]["metrics"]["stt_failures"], 0)
        self.assertEqual(snapshot["live_state"]["final_utterance_count"], 1)
        self.assertEqual(len([event for event in connection.sent if event.get("type") == "stt_committing"]), 0)
        current.close()

    def test_vad_shutdown_empty_final_is_benign_after_speech_final(self) -> None:
        manager = LiveSessionManager(schema_dir=ROOT / "schemas", analyzer_factory=lambda: ContinuousAnalyzer())
        manager.start_mode("continuous")
        connection = FakeConnection()
        connection.incoming.put_nowait(encode_audio_frame(AudioChunk(0, 0.0, b"\x10\x00" * 240)))
        config = RealtimeSTTConfig(
            endpoint="wss://example.invalid/realtime",
            api_key="test-only",
            model="gpt-transcribe",
            language="ja",
            prompt="test",
            keywords=(),
            timeout_seconds=1.0,
            finalization_mode="server_vad",
        )

        async def run_gateway():
            gateway = LiveWebSocketGateway(manager, stt_config=config)
            with patch("prototype.live_transport.OpenAIRealtimeTranscriptionClient", lambda cfg: FakeVADProvider(cfg, auto_final="VADの発話です", empty_after_final=True)):
                await asyncio.wait_for(gateway(connection), timeout=2.0)

        asyncio.run(run_gateway())
        current = manager.current()
        self.assertIsNotNone(current)
        snapshot = current.snapshot()
        self.assertEqual(snapshot["live_state"]["runtime_state"], "ended")
        self.assertEqual(snapshot["live_state"]["metrics"]["stt_failures"], 0)
        self.assertTrue(any(event.get("type") == "empty_final_ignored" for event in connection.sent))
        current.close()

    def test_vad_session_end_flushes_pending_speech(self) -> None:
        manager = LiveSessionManager(schema_dir=ROOT / "schemas", analyzer_factory=lambda: ContinuousAnalyzer())
        manager.start_mode("continuous")
        connection = FakeConnection()
        connection.incoming.put_nowait(encode_audio_frame(AudioChunk(0, 0.0, b"\x10\x00" * 240)))
        connection.incoming.put_nowait(json.dumps({"type": "stop"}))
        config = RealtimeSTTConfig(
            endpoint="wss://example.invalid/realtime",
            api_key="test-only",
            model="gpt-transcribe",
            language="ja",
            prompt="test",
            keywords=(),
            timeout_seconds=1.0,
            finalization_mode="server_vad",
        )

        async def run_gateway():
            gateway = LiveWebSocketGateway(manager, stt_config=config)
            with patch("prototype.live_transport.OpenAIRealtimeTranscriptionClient", lambda cfg: FakeVADProvider(cfg, commit_final="停止時に確定した発話です")):
                await asyncio.wait_for(gateway(connection), timeout=2.0)

        asyncio.run(run_gateway())
        current = manager.current()
        self.assertIsNotNone(current)
        snapshot = current.snapshot()
        self.assertEqual(snapshot["live_state"]["runtime_state"], "ended")
        self.assertEqual(snapshot["live_state"]["final_utterance_count"], 1)
        self.assertEqual(len([event for event in connection.sent if event.get("type") == "stt_committing"]), 1)
        current.close()

    def test_vad_empty_final_with_pending_speech_remains_incomplete(self) -> None:
        manager = LiveSessionManager(schema_dir=ROOT / "schemas", analyzer_factory=lambda: ContinuousAnalyzer())
        manager.start_mode("continuous")
        connection = FakeConnection()
        connection.incoming.put_nowait(encode_audio_frame(AudioChunk(0, 0.0, b"\x10\x00" * 240)))
        connection.incoming.put_nowait(json.dumps({"type": "stop"}))
        config = RealtimeSTTConfig(
            endpoint="wss://example.invalid/realtime",
            api_key="test-only",
            model="gpt-transcribe",
            language="ja",
            prompt="test",
            keywords=(),
            timeout_seconds=1.0,
            finalization_mode="server_vad",
        )

        async def run_gateway():
            gateway = LiveWebSocketGateway(manager, stt_config=config)
            with patch("prototype.live_transport.OpenAIRealtimeTranscriptionClient", lambda cfg: FakeVADProvider(cfg, commit_empty=True)):
                await asyncio.wait_for(gateway(connection), timeout=2.0)

        asyncio.run(run_gateway())
        current = manager.current()
        self.assertIsNotNone(current)
        snapshot = current.snapshot()
        self.assertEqual(snapshot["live_state"]["runtime_state"], "ended_with_incomplete_processing")
        self.assertEqual(snapshot["live_state"]["error"]["code"], "empty_final_transcript")
        current.close()

    def test_hybrid_bounded_fallback_commits_only_meaningful_audio(self) -> None:
        manager = LiveSessionManager(schema_dir=ROOT / "schemas", analyzer_factory=lambda: ContinuousAnalyzer())
        manager.start_mode("continuous")
        connection = FakeConnection()
        connection.incoming.put_nowait(encode_audio_frame(AudioChunk(0, 0.0, b"\x10\x00" * 240)))
        config = RealtimeSTTConfig(
            endpoint="wss://example.invalid/realtime",
            api_key="test-only",
            model="gpt-transcribe",
            language="ja",
            prompt="test",
            keywords=(),
            timeout_seconds=1.0,
            finalization_mode="server_vad_bounded",
            periodic_commit_seconds=0.005,
        )

        async def run_gateway():
            gateway = LiveWebSocketGateway(manager, stt_config=config)
            with patch("prototype.live_transport.OpenAIRealtimeTranscriptionClient", lambda cfg: FakeVADProvider(cfg, commit_final="bounded fallbackで確定した発話です")):
                await asyncio.wait_for(gateway(connection), timeout=2.0)

        asyncio.run(run_gateway())
        current = manager.current()
        self.assertIsNotNone(current)
        snapshot = current.snapshot()
        self.assertEqual(snapshot["live_state"]["runtime_state"], "ended")
        self.assertTrue(any(event.get("boundary_reason") == "bounded_fallback" for event in connection.sent if event.get("type") == "stt_committing"))
        self.assertEqual(snapshot["live_state"]["evidence_traces"][0]["boundary_reason"], "bounded_fallback")
        current.close()

    def test_hybrid_does_not_commit_pure_silence(self) -> None:
        manager = LiveSessionManager(schema_dir=ROOT / "schemas", analyzer_factory=lambda: ContinuousAnalyzer())
        manager.start_mode("continuous")
        connection = FakeConnection()
        connection.incoming.put_nowait(encode_audio_frame(AudioChunk(0, 0.0, b"\x00\x00" * 240)))
        connection.incoming.put_nowait(json.dumps({"type": "stop"}))
        config = RealtimeSTTConfig(
            endpoint="wss://example.invalid/realtime",
            api_key="test-only",
            model="gpt-transcribe",
            language="ja",
            prompt="test",
            keywords=(),
            timeout_seconds=1.0,
            finalization_mode="server_vad_bounded",
            periodic_commit_seconds=0.005,
        )

        async def run_gateway():
            gateway = LiveWebSocketGateway(manager, stt_config=config)
            with patch("prototype.live_transport.OpenAIRealtimeTranscriptionClient", lambda cfg: FakeVADProvider(cfg, commit_final="should not be used")):
                await asyncio.wait_for(gateway(connection), timeout=2.0)

        asyncio.run(run_gateway())
        current = manager.current()
        self.assertIsNotNone(current)
        snapshot = current.snapshot()
        self.assertEqual(snapshot["live_state"]["runtime_state"], "ended")
        self.assertEqual(snapshot["live_state"]["final_utterance_count"], 0)
        self.assertEqual(len([event for event in connection.sent if event.get("type") == "stt_committing"]), 0)
        current.close()

    def test_hybrid_fallback_requires_active_vad_speech(self) -> None:
        config = RealtimeSTTConfig(
            endpoint="wss://example.invalid/realtime",
            api_key="test-only",
            model="gpt-transcribe",
            language="ja",
            prompt="test",
            keywords=(),
            timeout_seconds=1.0,
            finalization_mode="server_vad_bounded",
        )
        provider = FakeVADProvider(config)
        provider.vad_speech_active = False
        self.assertFalse(
            provider.should_commit_bounded_fallback(has_audio_buffer=True, meaningful_audio=True)
        )
        provider.vad_speech_active = True
        self.assertTrue(
            provider.should_commit_bounded_fallback(has_audio_buffer=True, meaningful_audio=True)
        )

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
