"""Synthetic Core contract for the RFC-0009 Spot adapter boundary.

The controlled corpus supplies accepted Events, not Analyzer accuracy claims.
This freezes the meaning of replay, Human correction, Canvas and final PDF
before Core is packaged for a separate Content repository.
"""

from __future__ import annotations

import copy
import io
import json
import unittest
from pathlib import Path

from pypdf import PdfReader

from evaluation.tooling.semantic_hypothesis_review import build_case
from prototype.commands import HumanCommandHandler
from prototype.layout import StableLayout, map_projection
from prototype.replay import ReplayRunner, canonical_json
from prototype.schema import SchemaValidator
from prototype.service_final_record import prepare_final_record, render_final_pdf


ROOT = Path(__file__).resolve().parents[1]


def _system_event(session_id: str, sequence: int, kind: str, payload: dict) -> dict:
    return {
        "event_id": f"spot-core-{sequence}", "session_id": session_id,
        "sequence": sequence, "event_type": kind,
        "occurred_at": "2026-09-23T01:05:00Z", "actor": "system",
        "source_evidence_ids": [], "payload": payload,
    }


class SpotCoreContractTests(unittest.TestCase):
    def test_human_correction_replays_into_same_canvas_and_pdf_without_transcript(self) -> None:
        corpus = json.loads((ROOT / "evaluation/relation-corpus/corpus.json").read_text(encoding="utf-8"))
        case = next(case for case in corpus["controlled_cases"] if case["id"] == "R5")
        classes = json.loads((ROOT / "evaluation/relation-corpus/minimal_model_classification.json").read_text(
            encoding="utf-8"))
        classifications = {pair["id"]: pair["classification"] for pair in classes["pairs"]}
        accepted, ids = build_case(case, classifications)
        validator = SchemaValidator(ROOT / "schemas")
        runner = ReplayRunner(validator)
        session_id = accepted.state["graph"]["session_id"]

        # A Final transcript can contain words not promoted into Canonical Nodes.
        evidence = copy.deepcopy(accepted.state["evidence"])
        evidence[0]["text"] += " 検証用の非採用発話B7X9。"
        accepted = runner.replay_events(
            session_id=session_id, evidence=evidence,
            utterances=accepted.state["utterances"], events=accepted.events,
        )
        old_relation = {"source_node_id": ids["r5-n1"], "target_node_id": ids["r5-n3"],
                        "relation_type": "discussion_provenance"}
        corrected = HumanCommandHandler(runner).handle(accepted, {
            "command_type": "correct_relation", "old_relation": old_relation,
            "new_relation": None, "declared_independent": True,
            "expected_revision": accepted.state["graph"]["revision"],
            "occurred_at": "2026-09-23T01:00:00Z", "source_evidence_ids": [],
        }).result
        self.assertEqual(corrected.events[-1]["actor"], "human")
        self.assertEqual(corrected.events[-1]["event_type"], "correct_relation")
        self.assertFalse(any(edge["source_node_id"] == ids["r5-n1"] and
                             edge["target_node_id"] == ids["r5-n3"]
                             for edge in corrected.state["graph"]["edges"]))

        finalizing = len(corrected.events) + 1
        ended = runner.apply_event(corrected, _system_event(
            session_id, finalizing, "session_finalizing",
            {"last_evidence_sequence": len(evidence)},
        ))
        ended = runner.apply_event(ended, _system_event(
            session_id, finalizing + 1, "session_ended",
            {"drain_status": "complete", "final_graph_revision": finalizing,
             "pending_analysis": False},
        ))
        cold = runner.replay_events(
            session_id=session_id, evidence=evidence,
            utterances=ended.state["utterances"], events=ended.events,
        )
        self.assertEqual(canonical_json(ended.state), canonical_json(cold.state))
        live_canvas = map_projection(ended.state, ended.events, StableLayout())["semantic_canvas"]
        self.assertEqual(live_canvas,
                         map_projection(cold.state, cold.events, StableLayout())["semantic_canvas"])

        record = prepare_final_record(ended, final_revision=finalizing + 1,
                                      schema_validator=validator)
        self.assertEqual(record["canvas"], live_canvas)
        self.assertEqual(record["nodes"][ids["r5-n1"]]["status"], "confirmed")
        self.assertEqual(record["nodes"][ids["r5-n3"]]["action"]["owner"], "田中")
        self.assertEqual(record["nodes"][ids["r5-n3"]]["action"]["due_date"], "2026-10-15")
        self.assertFalse(any(edge["source_node_id"] == ids["r5-n1"] and
                             edge["target_node_id"] == ids["r5-n3"]
                             for edge in record["canvas"]["edges"]))
        pdf = render_final_pdf(record)
        self.assertEqual(pdf, render_final_pdf(record))
        text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
        self.assertIn("2026-10-15", text)
        self.assertNotIn("非採用発話B7X9", text)


if __name__ == "__main__":
    unittest.main()
