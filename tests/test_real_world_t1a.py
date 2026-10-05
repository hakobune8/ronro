from __future__ import annotations

import unittest

from prototype.errors import PrototypeError
from prototype.real_world_t1a import (
    T1A_SNAPSHOT_MINUTES,
    T1A_SOURCE,
    T1A_SAFETY_KEYS,
    T1ABrowserGateEvidence,
    T1AExecutionRunner,
    T1ARunnerState,
    run_synthetic_t1a_dry_run,
)


class RealWorldT1ATests(unittest.TestCase):
    def test_live_runner_is_hard_gated_by_browser_provenance(self) -> None:
        runner = T1AExecutionRunner(evaluation_session_id="t1a-gate")
        self.assertEqual(runner.state, T1ARunnerState.WAITING_FOR_BROWSER_GATE)
        with self.assertRaises(PrototypeError):
            runner.start_source_playback()
        with self.assertRaises(PrototypeError):
            runner.mark_browser_gate_passed(
                {
                    "actual_track_is_blackhole": True,
                    "fresh_session": True,
                    "source_matching_finals": 2,
                    "pause_stopped_meaningful_finals": True,
                    "resume_restored_source_finals": True,
                    "demo_contamination_count": 0,
                }
            )
        self.assertEqual(runner.state, T1ARunnerState.WAITING_FOR_BROWSER_GATE)

    def test_live_runner_records_source_playback_and_checkpoints(self) -> None:
        runner = T1AExecutionRunner(evaluation_session_id="t1a-run")
        runner.mark_browser_gate_passed(
            T1ABrowserGateEvidence(
                actual_track_is_blackhole=True,
                fresh_session=True,
                source_matching_finals=3,
                pause_stopped_meaningful_finals=True,
                resume_restored_source_finals=True,
                demo_contamination_count=0,
            )
        )
        instruction = runner.ready_instruction()
        self.assertEqual(instruction["source"]["start_time"], "01:24:00")
        runner.start_source_playback()
        self.assertEqual(runner.state, T1ARunnerState.RUNNING)
        for minute in T1A_SNAPSHOT_MINUTES:
            self.assertEqual(runner.due_snapshot_minutes(minute * 60), [minute])
            runner.add_snapshot(minute, snapshot={"state": {"graph": {"revision": minute}}, "map": {}, "live_state": {}})
            self.assertEqual(runner.due_snapshot_minutes(minute * 60), [])
        runner.begin_draining()
        result = runner.complete(
            final_snapshot={"state": {"graph": {"revision": 15}}, "live_state": {"rendered_revision": 15}},
            safety={key: 0 for key in T1A_SAFETY_KEYS},
        )
        self.assertEqual(runner.state, T1ARunnerState.COMPLETED)
        self.assertEqual(sorted(result["snapshots"]), ["10", "15", "5"])
        self.assertFalse(result["source_media_persisted"])
        self.assertFalse(result["complete_transcript_persisted"])

    def test_dry_run_does_not_claim_browser_gate(self) -> None:
        result = run_synthetic_t1a_dry_run()
        self.assertEqual(result["mode"], "synthetic_dry_run")
        self.assertEqual(result["state"], T1ARunnerState.COMPLETED.value)
        self.assertEqual(result["browser_gate"]["status"], "not_evaluated")
        self.assertEqual(sorted(result["snapshots"]), ["10", "15", "5"])
        self.assertEqual(result["safety"]["evidence_loss"], 0)
        self.assertEqual(result["source"]["duration_seconds"], 900)
        self.assertTrue(result["dry_run"]["report_generated"])

    def test_source_metadata_is_fixed(self) -> None:
        self.assertEqual(T1A_SOURCE["test_id"], "T1-A")
        self.assertEqual(T1A_SOURCE["start_time"], "01:24:00")
        self.assertEqual(T1A_SOURCE["end_time"], "01:39:00")
        self.assertEqual(T1A_SOURCE["duration_seconds"], 900)


if __name__ == "__main__":
    unittest.main()
