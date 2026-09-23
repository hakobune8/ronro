import copy
import json
import unittest
from pathlib import Path

from prototype.analyzer import TranscriptReplaySession
from prototype.display_labels import content_hash, display_projection, validate_label
from prototype.layout import StableLayout, map_projection
from prototype.real_analyzer import RealAnalyzer, StaticJsonProvider
from prototype.replay import ReplayRunner
from prototype.schema import SchemaValidator

ROOT = Path(__file__).resolve().parents[1]


class DisplayLabelTests(unittest.TestCase):
    def test_live_v3_is_explicit_opt_in(self):
        from unittest.mock import patch
        from prototype.live_session import LiveOneUtteranceSession
        v = SchemaValidator(ROOT / "schemas")
        with patch.dict("os.environ", {"REAL_ANALYZER_OUTPUT_SCHEMA_VERSION":"v3"}):
            s = LiveOneUtteranceSession(session_id="display-test", schema_validator=v, replay_runner=ReplayRunner(v))
            self.assertEqual(s.analyzer.output_schema_version, "v3")
            s.close()

    def run_case(self, hint, *, version="v3", omit=False):
        validator = SchemaValidator(ROOT / "schemas")
        intent = dict(kind="node", node_type="topic", label="資料の確認方法を検討する", existing_node_id=None, source_evidence_ids=["e1"])
        if not omit:
            intent["display_label"] = hint
        analyzer = RealAnalyzer(provider=StaticJsonProvider([{"events": [intent]}]), schema_validator=validator,
                                prompt_version="analyzer-prompt-v4", output_schema_version=version)
        evidence = dict(id="e1", session_id="s1", kind="transcript", source_type="live_stt", text="資料の確認方法を検討します", captured_at="2026-09-23T00:00:00Z")
        utterance = dict(id="u1", session_id="s1", sequence=1, evidence_ids=["e1"], text=evidence["text"], started_at=evidence["captured_at"], ended_at=evidence["captured_at"], is_final=True)
        session = TranscriptReplaySession.from_documents(session=dict(id="s1"), evidence=[evidence], utterances=[utterance], analyzer=analyzer, replay_runner=ReplayRunner(validator))
        session.step()
        self.assertEqual(analyzer.last_trace["status"], "success")
        self.assertEqual(len(session.result.state["graph"]["nodes"]), 1, session.analysis_errors)
        return session

    def test_valid_hint_never_enters_canonical_event_or_graph(self):
        s = self.run_case("資料確認の方法を検討する")
        self.assertNotIn("display_label", json.dumps(s.result.state))
        self.assertNotIn("display_label", json.dumps(s.result.events))
        self.assertEqual(len(s.analyzer.run_history), 1)
        values = display_projection(s.result.state["graph"], s.result.presentation)
        self.assertEqual(next(iter(values.values()))["text"], "資料確認の方法を検討する")

    def test_missing_and_invalid_never_drop_canonical_node(self):
        for hint in (None, "", "   ", 123, {}, "長" * 73, "その他", "<script>"):
            with self.subTest(hint=hint):
                s = self.run_case(hint)
                value = next(iter(display_projection(s.result.state["graph"], s.result.presentation).values()))
                self.assertTrue(value["fallback"])
                self.assertEqual(value["text"], s.result.state["graph"]["nodes"][0]["label"])
        self.run_case(None, omit=True)

    def test_v2_unchanged_and_old_fixture_compatible(self):
        s = self.run_case(None, version="v2", omit=True)
        self.assertEqual(s.result.presentation, {})
        self.assertTrue(next(iter(display_projection(s.result.state["graph"]).values()))["fallback"])

    def test_sidecar_roundtrip_and_stale_content(self):
        s = self.run_case("資料確認の方法を検討する")
        restored = s.replay_runner.replay_events(session_id="s1", evidence=s.evidence, utterances=s.utterances, events=s.result.events, presentation=json.loads(json.dumps(s.result.presentation)))
        self.assertEqual(s.result.state, restored.state)
        self.assertEqual(display_projection(s.result.state["graph"], s.result.presentation), display_projection(restored.state["graph"], restored.presentation))
        restored.state["graph"]["nodes"][0]["label"] = "人が変更した本文"
        self.assertTrue(next(iter(display_projection(restored.state["graph"], restored.presentation).values()))["fallback"])

    def test_selection_slots_flow_and_overflow_unchanged(self):
        s = self.run_case("資料確認の方法を検討する")
        a = map_projection(s.result.state, s.result.events, StableLayout())
        b = map_projection(s.result.state, s.result.events, StableLayout(), s.result.presentation)
        for k in ("display_labels", "presentation"):
            a.pop(k); b.pop(k)
        self.assertEqual(a, b)

    def test_negation_provisional_estimate_proposal_concern_number(self):
        for text in ("資料を判読できない", "暫定9.5と推定", "新方式を提案", "安全性に懸念", "主要14箇所を確認"):
            node = dict(type="idea", label=text)
            self.assertEqual(validate_label(text, node)[0], text)
        self.assertIsNone(validate_label("資料を判読できる", dict(label="資料を判読できない"))[0])
        self.assertIsNone(validate_label("値は確定9.5", dict(label="値は暫定9.5"))[0])
        self.assertIsNone(validate_label("15箇所を確認", dict(label="14箇所を確認"))[0])

    def test_execution_metadata_from_canonical_attributes_only(self):
        node = dict(id="a1", type="action", label="資料を作成する", action=dict(owner="山田さん", due_date="2026-09-26"))
        for text in ("佐藤さんが資料を作成する", "資料を2026-09-27までに作成", "担当：佐藤", "期限：明日"):
            self.assertIsNone(validate_label(text, node)[0])
        view = display_projection(dict(nodes=[node]))["a1"]
        self.assertEqual(view["owner"], "山田さん")
        self.assertEqual(view["due_date"], "2026-09-26")

    def test_provider_schema_v3_nullable_and_v2_unchanged(self):
        v = SchemaValidator(ROOT / "schemas")
        for name in ("nodeIntentNonAction", "nodeIntentAction"):
            self.assertNotIn("display_label", v.analyzer_output_v2_schema["$defs"][name]["properties"])
            self.assertEqual(v.analyzer_output_v3_schema["$defs"][name]["properties"]["display_label"]["type"], ["string", "null"])

    def test_reset_drops_sidecar(self):
        s = self.run_case("資料確認の方法を検討する")
        s.reset()
        self.assertEqual(s.result.presentation, {})

    def test_tense_completion_progress_and_plan_do_not_collapse(self):
        pairs = (("新方式を提案した", "新方式を提案する"),
                 ("新方式が提案された", "新方式を提案"),
                 ("新方式を提案する", "新方式を提案した"),
                 ("資料は確認済み", "資料は確認予定"),
                 ("資料は未確認", "資料は確認済み"),
                 ("現場は対策中", "現場は対策が必要"))
        for canonical, invalid in pairs:
            self.assertIsNone(validate_label(invalid, dict(label=canonical))[0])
            self.assertEqual(validate_label(canonical, dict(label=canonical))[0], canonical)

    def test_hint_does_not_change_canonical_result(self):
        old = self.run_case(None, version="v2", omit=True)
        new = self.run_case("資料確認の方法を検討する")
        self.assertEqual(old.result.state, new.result.state)
        self.assertEqual(old.result.events, new.result.events)

    def test_unsupported_time_and_owner_are_rejected(self):
        node = dict(type="action", label="資料を作成する", action=dict(owner=None, due_date=None))
        self.assertIsNone(validate_label("山田さんが資料を作成する", node)[0])
        self.assertIsNone(validate_label("9月26日までに資料を作成する", node)[0])
        self.assertIsNone(validate_label("佐藤が資料を作成する", node)[0])
        self.assertIsNone(validate_label("明日までに資料を作成する", node)[0])
        self.assertIsNone(validate_label("資料を作成する", dict(label="資料を作成するか検討"))[0])

    def test_duplicate_hint_first_write_wins(self):
        from prototype.display_labels import record_hint
        from prototype.analyzer import CandidateEvent
        s = self.run_case("資料確認の方法を検討する")
        before = copy.deepcopy(s.result.presentation)
        event = s.result.events[-1]
        record_hint(s.result, CandidateEvent(event_id=event["event_id"], session_id="s1", event_type="node_detected", occurred_at=event["occurred_at"], source_evidence_ids=("e1",), payload=event["payload"], presentation={"display_label":"別の本文を検討"}))
        self.assertEqual(before, s.result.presentation)

    def test_no_record_for_rejected_or_absent_node(self):
        from prototype.display_labels import record_hint
        from prototype.analyzer import CandidateEvent
        s = self.run_case("資料確認の方法を検討する")
        before = copy.deepcopy(s.result.presentation)
        record_hint(s.result, CandidateEvent(event_id="not-accepted", session_id="s1", event_type="node_detected", occurred_at="2026-09-23T00:00:00Z", source_evidence_ids=("e1",), payload={}, presentation={"display_label":"存在しない"}))
        self.assertEqual(before, s.result.presentation)

    def test_persistent_status_and_structured_owner_due_survive(self):
        nodes = [dict(id=str(i), type=t, status=status, label="資料を確認する") for i,(t,status) in enumerate((("decision","candidate"),("decision","confirmed"),("open_item","unresolved"),("action","active")))]
        nodes[-1]["action"] = dict(owner="山田さん", due_date="2026-09-26")
        graph = dict(nodes=nodes, last_event_sequence=9)
        records = {n["id"]:dict(version="display-label-v1", content_hash=content_hash(n), sequence=1, display_label="資料を確認") for n in nodes}
        before = copy.deepcopy(graph)
        values = display_projection(graph, records)
        self.assertEqual(graph, before)
        self.assertTrue(all(not v["fallback"] for v in values.values()))
        self.assertEqual(values['3']['owner'], "山田さん")
        self.assertEqual(values['3']['due_date'], "2026-09-26")

    def test_malformed_sidecar_falls_back(self):
        s = self.run_case("資料確認の方法を検討する")
        graph = s.result.state["graph"]
        for malformed in ([], {graph['nodes'][0]['id']: []}, {graph['nodes'][0]['id']: dict(version='display-label-v1',content_hash=content_hash(graph['nodes'][0]),sequence='invalid',display_label='短文')}):
            self.assertTrue(next(iter(display_projection(graph, malformed).values()))['fallback'])

    def test_live_queue_accepts_and_exports_sidecar(self):
        from dataclasses import replace
        from tests.test_live_queue import QueueAnalyzer, make_runtime, enqueue
        class WithHint(QueueAnalyzer):
            def analyze(self, *args):
                return [replace(c, presentation={'display_label': c.payload['label']}) for c in super().analyze(*args)]
        runtime = make_runtime(WithHint())
        try:
            item = enqueue(runtime, 1)
            self.assertEqual(runtime.wait(item.queue_item_id, timeout=5).state, 'completed')
            snapshot = runtime.snapshot()
            self.assertEqual(len(snapshot['map']['presentation']), 1)
            self.assertFalse(next(iter(snapshot['map']['display_labels'].values()))['fallback'])
            self.assertNotIn('display_label', json.dumps(snapshot['state']))
        finally:
            runtime.close()

    def test_polite_passive_negative_and_progress_states(self):
        for canonical, changed in (
            ("手順を提案しました", "手順を提案します"),
            ("手順が提案されている", "手順が提案された"),
            ("資料は確認済みではない", "資料は確認済み"),
            ("資料は確認済み", "資料は確認済みではない"),
            ("方法を検討している", "方法を検討する"),
            ("値を試算した", "値を試算する"),
        ):
            self.assertIsNone(validate_label(changed, dict(label=canonical))[0])
            self.assertEqual(validate_label(canonical, dict(label=canonical))[0], canonical)

    def test_comparator_direction_and_scope_preserved(self):
        canonical = "会場Aより広く会場Bより狭い"
        for changed in ("会場Aより広い", "会場Bより広く会場Aより狭い", "会場は広い"):
            self.assertIsNone(validate_label(changed, dict(label=canonical))[0])
        self.assertEqual(validate_label(canonical, dict(label=canonical))[0], canonical)
        self.assertIsNone(validate_label("14箇所を対策中", dict(label="主要14箇所を対策中"))[0])

    def test_legacy_policy_keeps_saved_replay_and_new_policy_rejects(self):
        node = dict(id="n", type="idea", label="会場Aより広く会場Bより狭い")
        graph = dict(nodes=[node],last_event_sequence=1)
        record = dict(version="display-label-v1", sequence=1,content_hash=content_hash(node),display_label="広い会場")
        self.assertFalse(display_projection(graph, {"n":record})["n"]["fallback"])
        record["policy"] = "display-label-policy-v2"
        self.assertTrue(display_projection(graph, {"n":record})["n"]["fallback"])

    def test_generated_newline_is_not_semantic_truncation(self):
        text = "会場Aより広く\n会場Bより狭い"
        accepted, reason = validate_label(text, dict(label="会場Aより広く会場Bより狭い"))
        self.assertEqual(accepted, "会場Aより広く 会場Bより狭い")
        self.assertEqual(reason, "accepted")
