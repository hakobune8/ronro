"""Synthetic-only final PDF contract checks."""

from __future__ import annotations

import copy
import io
import json
import unittest
from pathlib import Path

from pypdf import PdfReader

from evaluation.tooling.semantic_hypothesis_review import build_case
from prototype.replay import ReplayRunner
from prototype.schema import SchemaValidator
from prototype.service_errors import ServiceStoreError
from prototype.service_final_record import prepare_final_record, render_final_pdf
from tests.test_service_store import event


ROOT = Path(__file__).resolve().parents[1]


class FinalRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        corpus = json.loads((ROOT / "evaluation/relation-corpus/corpus.json").read_text())
        classes = json.loads((ROOT / "evaluation/relation-corpus/minimal_model_classification.json").read_text())
        cls.cases = {case["id"]: case for case in corpus["controlled_cases"]}
        cls.classifications = {pair["id"]: pair["classification"] for pair in classes["pairs"]}
        cls.runner = ReplayRunner(SchemaValidator(ROOT / "schemas"))

    def _ended(self, case_id="R5", *, incomplete=False, extra_nodes=0):
        result, ids = build_case(self.cases[case_id], self.classifications)
        session_id = result.state["graph"]["session_id"]
        for index in range(extra_nodes):
            sequence = len(result.events) + 1
            label = (f"合成論点{index + 1}: " +
                     ("詳細な技術条件を確認する。" * 35 if index == extra_nodes - 1 else
                      "議論の条件を確認する"))
            result = self.runner.apply_event(result, event(
                session_id, sequence, "node_detected",
                {"node_type": "idea", "label": label}, actor="analyzer",
                evidence_ids=[result.state["evidence"][0]["id"]],
            ))
        first = len(result.events) + 1
        result = self.runner.apply_event(result, event(
            session_id, first, "session_finalizing",
            {"last_evidence_sequence": len(result.state["evidence"])},
        ))
        result = self.runner.apply_event(result, event(
            session_id, first + 1, "session_ended",
            {"drain_status": "partial" if incomplete else "complete",
             "final_graph_revision": first, "pending_analysis": incomplete},
        ))
        return result, ids

    def test_final_record_uses_same_canvas_and_preserves_state(self):
        result, ids = self._ended()
        record = prepare_final_record(
            result, final_revision=result.state["graph"]["revision"],
            schema_validator=self.runner.schema_validator,
        )
        self.assertEqual(record["canvas"]["revision"], record["revision"])
        self.assertEqual(record["canvas"]["version"], "semantic-canvas-v2")
        self.assertEqual(record["nodes"][ids["r5-n1"]]["status"], "confirmed")
        self.assertEqual(record["nodes"][ids["r5-n3"]]["action"]["owner"], "田中")
        pdf = render_final_pdf(record)
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertEqual(pdf, render_final_pdf(record))
        extracted = "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
        self.assertIn("会議後の論点図", extracted)
        self.assertIn("田中", extracted)
        self.assertIn("2026-10-15", extracted)
        self.assertIn("確定", extracted)

    def test_incomplete_record_distinguishes_possible_gap_from_pause(self):
        result, _ = self._ended("R4", incomplete=True)
        record = prepare_final_record(
            result, final_revision=result.state["graph"]["revision"],
            schema_validator=self.runner.schema_validator,
            capture_intervals=[
                {"kind": "paused", "opened_at": "pause", "closed_at": "resume"},
                {"kind": "capture_unavailable", "opened_at": "10:02", "closed_at": "10:04"},
            ],
        )
        self.assertEqual(record["gaps"], [{"start": "10:02", "end": "10:04"}])
        extracted = "".join(page.extract_text() for page in PdfReader(io.BytesIO(render_final_pdf(record))).pages)
        self.assertIn("10:02", extracted)
        self.assertNotIn("pause", extracted)

    def test_unended_or_mismatched_graph_is_rejected(self):
        result, _ = build_case(self.cases["R3"], self.classifications)
        with self.assertRaises(ServiceStoreError):
            prepare_final_record(result, final_revision=result.state["graph"]["revision"],
                                 schema_validator=self.runner.schema_validator)
        ended, _ = self._ended("R3")
        with self.assertRaises(ServiceStoreError):
            prepare_final_record(ended, final_revision=ended.state["graph"]["revision"] - 1,
                                 schema_validator=self.runner.schema_validator)
        corrupt = copy.deepcopy(ended)
        corrupt.events[-1]["payload"]["final_graph_revision"] = 0
        with self.assertRaises(ServiceStoreError):
            prepare_final_record(corrupt, final_revision=corrupt.state["graph"]["revision"],
                                 schema_validator=self.runner.schema_validator)

    def test_many_nodes_paginate_without_dropping_canonical_detail(self):
        result, _ = self._ended("R5", extra_nodes=55)
        record = prepare_final_record(
            result, final_revision=result.state["graph"]["revision"],
            schema_validator=self.runner.schema_validator,
        )
        self.assertEqual(len(record["nodes"]), 60)
        reader = PdfReader(io.BytesIO(render_final_pdf(record)))
        self.assertGreater(len(reader.pages), 2)
        extracted = "".join(page.extract_text() for page in reader.pages)
        self.assertIn("合成論点55", extracted)
        self.assertIn("詳細な技術条件を確認する", extracted)
