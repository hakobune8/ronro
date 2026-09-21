from __future__ import annotations

import copy
import threading
import time
import unittest
from pathlib import Path

from prototype.analyzer import CandidateEvent
from prototype.live_queue import LiveAnalyzerRuntime, LiveQueueItem, LiveUtteranceQueue, QueueError
from prototype.replay import ReplayRunner, semantic_equal
from prototype.schema import SchemaValidator


ROOT = Path(__file__).resolve().parents[1]


def _evidence(session_id: str, sequence: int, text: str) -> dict[str, object]:
    return {
        "id": f"evidence:{session_id}:{sequence}",
        "session_id": session_id,
        "sequence": sequence,
        "timestamp": f"2026-09-20T00:00:{sequence:02d}Z",
        "speaker": None,
        "text": text,
    }


def _utterance(session_id: str, sequence: int, evidence_id: str, text: str) -> dict[str, object]:
    timestamp = f"2026-09-20T00:00:{sequence:02d}Z"
    return {
        "id": f"utterance:{session_id}:{sequence}",
        "session_id": session_id,
        "sequence": sequence,
        "evidence_ids": [evidence_id],
        "text": text,
        "started_at": timestamp,
        "ended_at": timestamp,
    }


class QueueAnalyzer:
    provider_name = "test"
    model = "queue-test"
    prompt_version = "analyzer-prompt-v4"

    def __init__(self, *, delay: float = 0.0, fail_texts: set[str] | None = None) -> None:
        self.delay = delay
        self.fail_texts = fail_texts or set()
        self.calls: list[dict[str, object]] = []
        self.last_trace = None

    def analyze(self, utterance, current_graph, recent_events):
        if self.delay:
            time.sleep(self.delay)
        self.calls.append(
            {
                "sequence": utterance["sequence"],
                "graph": copy.deepcopy(current_graph),
                "events": copy.deepcopy(list(recent_events)),
            }
        )
        if utterance["text"] in self.fail_texts:
            self.last_trace = {
                "validation_error": {"code": "provider_failure", "message": "synthetic failure"},
                "critical_errors": [],
            }
            return []
        self.last_trace = None
        return [
            CandidateEvent(
                event_id=f"analyzer:{utterance['session_id']}:{utterance['sequence']}",
                session_id=utterance["session_id"],
                event_type="node_detected",
                occurred_at=utterance["ended_at"],
                source_evidence_ids=tuple(utterance["evidence_ids"]),
                payload={"node_type": "idea", "label": utterance["text"]},
            )
        ]


class TopicThenIdeaAnalyzer(QueueAnalyzer):
    def analyze(self, utterance, current_graph, recent_events):
        self.calls.append(
            {
                "sequence": utterance["sequence"],
                "graph": copy.deepcopy(current_graph),
                "events": copy.deepcopy(list(recent_events)),
            }
        )
        self.last_trace = None
        node_type = "topic" if utterance["sequence"] == 1 else "idea"
        return [
            CandidateEvent(
                event_id=f"context:{utterance['session_id']}:{utterance['sequence']}",
                session_id=utterance["session_id"],
                event_type="node_detected",
                occurred_at=utterance["ended_at"],
                source_evidence_ids=tuple(utterance["evidence_ids"]),
                payload={"node_type": node_type, "label": utterance["text"]},
            )
        ]


class BlockingAnalyzer(QueueAnalyzer):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def analyze(self, utterance, current_graph, recent_events):
        if utterance["sequence"] == 2:
            self.started.set()
            if not self.release.wait(timeout=3):
                raise RuntimeError("blocking analyzer timed out")
        return super().analyze(utterance, current_graph, recent_events)


class TwoPhaseBlockingAnalyzer(QueueAnalyzer):
    def __init__(self) -> None:
        super().__init__()
        self.first_started = threading.Event()
        self.first_release = threading.Event()
        self.second_started = threading.Event()
        self.second_release = threading.Event()
        self.calls_for_sequence_two = 0

    def analyze(self, utterance, current_graph, recent_events):
        if utterance["sequence"] == 2:
            self.calls_for_sequence_two += 1
            if self.calls_for_sequence_two == 1:
                self.first_started.set()
                if not self.first_release.wait(timeout=3):
                    raise RuntimeError("first analyzer phase timed out")
            else:
                self.second_started.set()
                if not self.second_release.wait(timeout=3):
                    raise RuntimeError("second analyzer phase timed out")
        return super().analyze(utterance, current_graph, recent_events)


def make_runtime(analyzer, *, session_id: str = "queue-test", **kwargs) -> LiveAnalyzerRuntime:
    validator = SchemaValidator(ROOT / "schemas")
    runner = ReplayRunner(validator)
    session = {
        "id": session_id,
        "title": "Queue test",
        "goal": "Queue test",
        "created_at": "2026-09-20T00:00:00Z",
        "started_at": "2026-09-20T00:00:00Z",
        "ended_at": None,
    }
    from prototype.analyzer import TranscriptReplaySession

    initial = TranscriptReplaySession.from_documents(
        session=session,
        evidence=[],
        utterances=[],
        replay_runner=runner,
        analyzer=analyzer,
        replay_mode="live",
    ).result
    return LiveAnalyzerRuntime(
        session_id=session_id,
        schema_validator=validator,
        replay_runner=runner,
        initial_result=initial,
        analyzer=analyzer,
        **kwargs,
    )


def enqueue(runtime: LiveAnalyzerRuntime, sequence: int, text: str | None = None) -> LiveQueueItem:
    text = text or f"idea-{sequence}"
    evidence = _evidence(runtime.session_id, sequence, text)
    utterance = _utterance(runtime.session_id, sequence, evidence["id"], text)
    return runtime.register_utterance(
        evidence=evidence,
        utterance=utterance,
        audio_end_at=utterance["ended_at"],
    )


class LiveQueueTests(unittest.TestCase):
    def test_queue_states_fifo_depth_and_delayed_status(self) -> None:
        queue = LiveUtteranceQueue(delayed_after_seconds=0.01, critical_after_seconds=0.05)
        queue.enqueue(LiveQueueItem("q2", 2, "e2", "two", "now"))
        queue.enqueue(LiveQueueItem("q1", 1, "e1", "one", "now"))
        self.assertEqual(queue.snapshot()["max_depth"], 2)
        time.sleep(0.02)
        self.assertEqual(queue.snapshot()["delayed_state"], "delayed")
        item = queue.claim_next(timeout=0.1)
        self.assertEqual(item.utterance_sequence, 1)
        queue.fail(item.queue_item_id, "test_failure", "expected")
        self.assertEqual(queue.snapshot()["failed"], 1)
        item2 = queue.claim_next(timeout=0.1)
        self.assertEqual(item2.utterance_sequence, 2)
        queue.complete(item2.queue_item_id)
        self.assertEqual(queue.snapshot()["completed"], 1)
        self.assertEqual(queue.snapshot()["last_completed_sequence"], 2)

    def test_queue_does_not_accept_duplicate_sequence_or_retry_completed(self) -> None:
        queue = LiveUtteranceQueue()
        queue.enqueue(LiveQueueItem("q1", 1, "e1", "one", "now"))
        with self.assertRaises(QueueError):
            queue.enqueue(LiveQueueItem("q1b", 1, "e1b", "one", "now"))
        item = queue.claim_next(timeout=0.1)
        queue.complete(item.queue_item_id)
        with self.assertRaises(QueueError):
            queue.retry(item.queue_item_id)

    def test_burst_3_10_20_has_no_loss_and_is_fifo(self) -> None:
        for count in (3, 10, 20):
            analyzer = QueueAnalyzer(delay=0.001)
            runtime = make_runtime(analyzer, session_id=f"burst-{count}")
            try:
                items = [enqueue(runtime, sequence) for sequence in range(1, count + 1)]
                for item in items:
                    completed = runtime.wait(item.queue_item_id, timeout=5)
                    self.assertEqual(completed.state, "completed")
                snapshot = runtime.queue.snapshot()
                self.assertEqual(snapshot["completed"], count)
                self.assertEqual(snapshot["failed"], 0)
                self.assertEqual(len(runtime.result.state["evidence"]), count)
                self.assertEqual(
                    [call["sequence"] for call in analyzer.calls],
                    list(range(1, count + 1)),
                )
                self.assertEqual(runtime.result.state["graph"]["revision"], 2 + count)
                self.assertEqual(snapshot["last_completed_sequence"], count)
            finally:
                runtime.close()

    def test_failure_does_not_stop_following_items_and_retry_preserves_identity(self) -> None:
        analyzer = QueueAnalyzer(fail_texts={"bad"})
        runtime = make_runtime(analyzer, session_id="failure-continue")
        try:
            failed = enqueue(runtime, 1, "bad")
            good = enqueue(runtime, 2, "good")
            self.assertEqual(runtime.wait(failed.queue_item_id, timeout=2).state, "failed")
            self.assertEqual(runtime.wait(good.queue_item_id, timeout=2).state, "completed")
            self.assertEqual(len(runtime.result.state["graph"]["nodes"]), 1)
            self.assertEqual(runtime.queue.snapshot()["failed"], 1)
            analyzer.fail_texts.clear()
            retried = runtime.retry(failed.queue_item_id)
            self.assertEqual(retried.evidence_id, failed.evidence_id)
            self.assertEqual(retried.utterance_sequence, failed.utterance_sequence)
            completed = runtime.wait(retried.queue_item_id, timeout=2)
            self.assertEqual(completed.state, "completed")
            self.assertEqual(completed.retry_count, 1)
            # Retry is an append-at-current-state operation; it does not
            # insert an old Event before the already committed sequence 2.
            analyzer_events = [event for event in runtime.result.events if event["actor"] == "analyzer"]
            self.assertEqual(
                [event["source_evidence_ids"][0] for event in analyzer_events],
                ["evidence:failure-continue:2", "evidence:failure-continue:1"],
            )
        finally:
            runtime.close()

    def test_latest_graph_context_is_loaded_at_processing_time(self) -> None:
        analyzer = TopicThenIdeaAnalyzer()
        runtime = make_runtime(analyzer, session_id="latest-context")
        try:
            first = enqueue(runtime, 1, "料金体系")
            self.assertEqual(runtime.wait(first.queue_item_id, timeout=2).state, "completed")
            second = enqueue(runtime, 2, "月額案")
            self.assertEqual(runtime.wait(second.queue_item_id, timeout=2).state, "completed")
            second_call = analyzer.calls[-1]
            self.assertEqual(len(second_call["graph"]["nodes"]), 1)
            self.assertEqual(second_call["graph"]["nodes"][0]["label"], "料金体系")
        finally:
            runtime.close()

    def test_human_command_interleave_reanalyzes_once_and_preserves_correction(self) -> None:
        analyzer = BlockingAnalyzer()
        runtime = make_runtime(analyzer, session_id="human-interleave")
        try:
            first = enqueue(runtime, 1, "料金体系")
            self.assertEqual(runtime.wait(first.queue_item_id, timeout=2).state, "completed")
            topic_id = runtime.result.state["graph"]["nodes"][0]["id"]
            second = enqueue(runtime, 2, "月額案")
            self.assertTrue(analyzer.started.wait(timeout=2))
            runtime.execute_command(
                {
                    "command_type": "rename_node",
                    "node_id": topic_id,
                    "label": "料金モデル",
                    "expected_revision": runtime.result.state["graph"]["revision"],
                    "occurred_at": "2026-09-20T00:01:00Z",
                }
            )
            analyzer.release.set()
            completed = runtime.wait(second.queue_item_id, timeout=3)
            self.assertEqual(completed.state, "completed")
            self.assertEqual(completed.reanalysis_count, 1)
            self.assertEqual(runtime.result.state["graph"]["nodes"][0]["label"], "料金モデル")
            self.assertTrue(any(call["graph"]["nodes"][0]["label"] == "料金モデル" for call in analyzer.calls[1:]))
        finally:
            runtime.close()

    def test_second_revision_change_fails_without_stale_analyzer_event(self) -> None:
        analyzer = TwoPhaseBlockingAnalyzer()
        runtime = make_runtime(analyzer, session_id="revision-conflict")
        try:
            first = enqueue(runtime, 1, "料金体系")
            self.assertEqual(runtime.wait(first.queue_item_id, timeout=2).state, "completed")
            topic_id = runtime.result.state["graph"]["nodes"][0]["id"]
            second = enqueue(runtime, 2, "月額案")
            self.assertTrue(analyzer.first_started.wait(timeout=2))
            runtime.execute_command(
                {
                    "command_type": "rename_node",
                    "node_id": topic_id,
                    "label": "料金モデル",
                    "expected_revision": runtime.result.state["graph"]["revision"],
                    "occurred_at": "2026-09-20T00:01:00Z",
                }
            )
            analyzer.first_release.set()
            self.assertTrue(analyzer.second_started.wait(timeout=2))
            runtime.execute_command(
                {
                    "command_type": "rename_node",
                    "node_id": topic_id,
                    "label": "価格モデル",
                    "expected_revision": runtime.result.state["graph"]["revision"],
                    "occurred_at": "2026-09-20T00:02:00Z",
                }
            )
            analyzer.second_release.set()
            failed = runtime.wait(second.queue_item_id, timeout=3)
            self.assertEqual(failed.state, "failed")
            self.assertEqual(failed.error["code"], "revision_conflict")
            self.assertFalse(any(event["actor"] == "analyzer" for event in runtime.result.events[3:]))
        finally:
            runtime.close()

    def test_replay_of_live_event_stream_is_deterministic(self) -> None:
        analyzer = QueueAnalyzer()
        runtime = make_runtime(analyzer, session_id="replay-determinism")
        try:
            items = [enqueue(runtime, sequence) for sequence in range(1, 4)]
            for item in items:
                self.assertEqual(runtime.wait(item.queue_item_id, timeout=2).state, "completed")
            replayed = runtime.replay_runner.replay_events(
                session_id=runtime.session_id,
                evidence=runtime.result.state["evidence"],
                utterances=runtime.result.state["utterances"],
                events=runtime.result.events,
            )
            self.assertTrue(semantic_equal(replayed.state, runtime.result.state))
            self.assertEqual(replayed.events, runtime.result.events)
        finally:
            runtime.close()


if __name__ == "__main__":
    unittest.main()
