"""The packaged Analyzer must preserve prototype intent semantics without IO."""

from __future__ import annotations

import unittest
from pathlib import Path

from prototype.analysis_engine import RealAnalyzer as CoreAnalyzer
from prototype.analysis_engine import StaticJsonProvider
from prototype.analyzer import CandidateEvent as LegacyCandidateEvent
from prototype.candidate_event import CandidateEvent
from prototype.real_analyzer import RealAnalyzer as LegacyAnalyzer
from prototype.schema import SchemaValidator


class CoreAnalyzerBoundaryTests(unittest.TestCase):
    def test_candidate_event_identity_and_legacy_output_match(self) -> None:
        self.assertIs(LegacyCandidateEvent, CandidateEvent)
        output = {"events": [
            {"kind": "node", "node_type": "topic", "label": "避難所の水",
             "source_evidence_ids": ["evd-1"]},
            {"kind": "node", "node_type": "option", "label": "倉庫の水を再配置する",
             "source_evidence_ids": ["evd-1"]},
            {"kind": "relation", "source": {"new_node_index": 0},
             "target": {"new_node_index": 1}, "relation_type": "has_option",
             "source_evidence_ids": ["evd-1"]},
        ]}
        validator = SchemaValidator(Path(__file__).resolve().parents[1] / "schemas")
        utterance = {"id": "utt-1", "session_id": "s-real", "sequence": 1,
                     "evidence_ids": ["evd-1"],
                     "text": "避難所の水について、倉庫の水を再配置する案を検討します。",
                     "started_at": "2026-09-19T10:00:00Z",
                     "ended_at": "2026-09-19T10:00:00Z"}
        graph = {"nodes": [], "edges": [], "current_topic": {}}
        results = []
        for cls in (CoreAnalyzer, LegacyAnalyzer):
            analyzer = cls(provider=StaticJsonProvider([output]), schema_validator=validator)
            candidates = analyzer.analyze(utterance, graph, [])
            self.assertEqual(analyzer.last_trace["status"], "success")
            results.append([candidate.to_event(index) for index, candidate in enumerate(candidates, 1)])
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(results[0]), 3)
        self.assertEqual(results[0][-1]["payload"]["relation_type"], "has_option")


if __name__ == "__main__":
    unittest.main()
