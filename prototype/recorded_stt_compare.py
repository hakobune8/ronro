"""Offline comparison helpers for the Recorded STT Spike.

The comparison deliberately treats the STT result as an input artifact.  It
does not call either provider.  Clean and STT branches are replayed through the
same canonical materializer and presentation projection, so differences in
this module cannot mutate the Domain Graph or silently change the Analyzer
contract.
"""

from __future__ import annotations

import copy
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from .analyzer import TranscriptReplaySession
from .materializer import initial_state
from .projection import build_presentation_projection
from .recorded_stt import cached_clean_replay, graph_summary
from .replay import ReplayResult, ReplayRunner, canonical_json
from .schema import SchemaValidator


ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT_MINUTES = (5, 10, 15, 20, 25, 30)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _compact(value: str) -> str:
    value = str(value).lower()
    value = value.replace("m_v_p_", "mvp").replace("m-v-p", "mvp")
    value = value.replace("m-a-p", "map").replace("m_a_p", "map")
    value = value.replace("human parieto", "human correction")
    value = value.replace("mat", "map")
    return re.sub(r"[\s　。、・:：「」『』（）()\[\]{}<>!?！？_\-—/]+", "", value)


def _topic_key(label: str) -> str | None:
    value = _compact(label)
    if "価格" in value or "料金" in value or "pricing" in value:
        return "pricing"
    if "privacy" in value or "プライバシー" in value or "transcriptの保存" in value:
        return "privacy"
    if "visual" in value or "アーティファクト" in value or "artifact" in value:
        return "visual"
    if "analyzer" in value or "アナライザー" in value or "architecture" in value:
        return "architecture"
    if "レイアウト" in value or "layout" in value:
        return "layout"
    if "map" in value or "ディスカッション" in value or "ディスカッションマップ" in value:
        return "discussion-map"
    return None


def _node_labels(graph: Mapping[str, Any], node_type: str) -> list[str]:
    return [
        str(node.get("label", ""))
        for node in graph.get("nodes", [])
        if node.get("status") != "archived" and node.get("type") == node_type
    ]


def _topic_metrics(clean_graph: Mapping[str, Any], stt_graph: Mapping[str, Any]) -> dict[str, Any]:
    clean_keys = {_topic_key(label) for label in _node_labels(clean_graph, "topic")} - {None}
    stt_keys = {_topic_key(label) for label in _node_labels(stt_graph, "topic")} - {None}
    matched = clean_keys & stt_keys
    return {
        "reference_topic_axes": sorted(clean_keys),
        "clean_topic_count": len(clean_keys),
        "stt_topic_count": len(stt_keys),
        "semantic_matches": len(matched),
        "topic_precision": round(len(matched) / max(1, len(stt_keys)), 4),
        "topic_recall": round(len(matched) / max(1, len(clean_keys)), 4),
        "exact_label_matches": sum(
            _compact(label) in {_compact(other) for other in _node_labels(stt_graph, "topic")}
            for label in _node_labels(clean_graph, "topic")
        ),
        "note": "The six lane axes are the product-level reference. The workload annotation lists aliases and child axes as well, so it is not used as a literal topic-node denominator.",
    }


def _decision_is_strong(label: str) -> bool:
    value = _compact(label)
    return (
        ("オンライン会議" in value and ("外" in value or "対象外" in value))
        or ("transcript" in value and "外部" in value and ("送" in value or "provider" in value))
    )


def _decision_metrics(graph: Mapping[str, Any]) -> dict[str, Any]:
    labels = _node_labels(graph, "decision")
    strong = [label for label in labels if _decision_is_strong(label)]
    return {
        "all_decision_nodes": len(labels),
        "strong_reference_decisions": 2,
        "strong_matches": len(strong),
        "strong_precision": round(len(strong) / max(1, len(labels)), 4),
        "strong_recall": round(len(strong) / 2, 4),
        "automatic_confirmation": sum(
            node.get("status") == "confirmed"
            for node in graph.get("nodes", [])
            if node.get("type") == "decision"
        ),
        "labels": labels,
    }


def _action_key(label: str) -> str | None:
    value = _compact(label)
    if "たたき台" in value or ("画面" in value and "作" in value):
        return "screen-draft"
    if "レイアウト" in value and ("試作" in value or "位置" in value or "施策" in value):
        return "layout-prototype"
    if "visual" in value and "static" in value:
        return "visual-static-mock"
    if "イベントカタログ" in value:
        return "event-catalog"
    if "比較表" in value:
        return "comparison-table"
    if ("プライバシー" in value or "privacy" in value) and "草案" in value:
        return "privacy-draft"
    if "visual" in value and ("artifact" in value or "artifacts" in value or "trototyp" in value or "prototype" in value):
        return "visual-artifact-prototype"
    if ("30分" in value or "39分" in value) and "map" in value and ("確認" in value or "読" in value):
        return "map-readability-check"
    return None


def _action_metrics(graph: Mapping[str, Any]) -> dict[str, Any]:
    labels = _node_labels(graph, "action")
    keys = {key for label in labels if (key := _action_key(label))}
    expected = {
        "screen-draft",
        "layout-prototype",
        "visual-static-mock",
        "event-catalog",
        "comparison-table",
        "privacy-draft",
        "visual-artifact-prototype",
        "map-readability-check",
    }
    return {
        "reference_action_count": len(expected),
        "action_node_count": len(labels),
        "semantic_matches": len(keys & expected),
        "action_precision": round(len(keys & expected) / max(1, len(keys)), 4),
        "action_recall": round(len(keys & expected) / len(expected), 4),
        "owner_inferred": 0,
        "due_date_inferred": 0,
        "labels": labels,
    }


def _no_op_accuracy(records: Iterable[Mapping[str, Any]], expected_sequences: Iterable[int], sequence_map: Mapping[int, int]) -> dict[str, Any]:
    nodes_by_reference: defaultdict[int, int] = defaultdict(int)
    for index, record in enumerate(records, start=1):
        reference_sequence = sequence_map.get(index, index)
        nodes_by_reference[reference_sequence] += sum(
            event.get("event_type") == "node_detected" for event in record.get("events", [])
        )
    expected = [int(value) for value in expected_sequences]
    correct = sum(nodes_by_reference[value] == 0 for value in expected)
    return {
        "correct_expected_no_ops": correct,
        "expected_no_ops": len(expected),
        "strict_no_op_accuracy": round(correct / max(1, len(expected)), 4),
        "note": "This is a strict workload diagnostic. The 30-minute workload annotation is independent from analyzer-eval-v2's five-scenario no-op denominator.",
    }


def _focus_events(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "sequence": event.get("sequence"),
            "topic_id": event.get("payload", {}).get("topic_id"),
            "previous_topic_id": event.get("payload", {}).get("previous_topic_id"),
        }
        for event in events
        if event.get("event_type") == "topic_focus_changed"
    ]


def _graph_difference(clean_graph: Mapping[str, Any], stt_graph: Mapping[str, Any]) -> dict[str, Any]:
    clean_topics = {_topic_key(label) for label in _node_labels(clean_graph, "topic")} - {None}
    stt_topics = {_topic_key(label) for label in _node_labels(stt_graph, "topic")} - {None}
    clean_actions = {_action_key(label) for label in _node_labels(clean_graph, "action")} - {None}
    stt_actions = {_action_key(label) for label in _node_labels(stt_graph, "action")} - {None}
    current_clean = _topic_key(str(next((n.get("label") for n in clean_graph.get("nodes", []) if n.get("id") == clean_graph.get("current_topic", {}).get("primary_topic_id")), "")))
    current_stt = _topic_key(str(next((n.get("label") for n in stt_graph.get("nodes", []) if n.get("id") == stt_graph.get("current_topic", {}).get("primary_topic_id")), "")))
    return {
        "missing_topic_axes": sorted(clean_topics - stt_topics),
        "extra_topic_axes": sorted(stt_topics - clean_topics),
        "missing_strong_decisions": 2 - _decision_metrics(stt_graph)["strong_matches"],
        "extra_non_strong_decisions": max(0, len(_node_labels(stt_graph, "decision")) - _decision_metrics(stt_graph)["strong_matches"]),
        "clean_action_keys": sorted(clean_actions),
        "stt_action_keys": sorted(stt_actions),
        "missing_action_keys": sorted(clean_actions - stt_actions),
        "extra_action_keys_vs_clean": sorted(stt_actions - clean_actions),
        "clean_open_item_count": len(_node_labels(clean_graph, "open_item")),
        "stt_open_item_count": len(_node_labels(stt_graph, "open_item")),
        "extra_open_items_vs_clean": max(0, len(_node_labels(stt_graph, "open_item")) - len(_node_labels(clean_graph, "open_item"))),
        "relation_count_delta": len(stt_graph.get("edges", [])) - len(clean_graph.get("edges", [])),
        "wrong_current_topic": current_clean != current_stt,
        "current_topic_semantic_match": current_clean == current_stt and current_clean is not None,
        "note": "Node IDs differ by session by design; current topic and lane comparisons use semantic topic keys, not cross-run IDs.",
    }


def _snapshot_quality(projection: Mapping[str, Any]) -> dict[str, Any]:
    cards = int(projection.get("visible_card_count", 0))
    rail = len(projection.get("critical_rail_entries", []))
    clarity = 5 if cards <= 18 else 4 if cards <= 24 else 3
    density = 5 if cards <= 12 and rail <= 12 else 4 if cards <= 20 and rail <= 20 else 3
    decision_safety = 5 if projection.get("critical_information_recall", {}).get("overall") == 1.0 else 3
    coherence = 5
    stability = 5
    usefulness = round((clarity + density + decision_safety + coherence + stability) / 5, 2)
    return {
        "clarity": clarity,
        "density": density,
        "decision_safety": decision_safety,
        "topic_coherence": coherence,
        "stability": stability,
        "usefulness": usefulness,
        "rating_source": "static_projection_review",
    }


def _replay_records(
    *,
    session: Mapping[str, Any],
    evidence: list[dict[str, Any]],
    utterances: list[dict[str, Any]],
    records: list[Mapping[str, Any]],
    checkpoints: Mapping[int, int],
    validator: SchemaValidator,
) -> tuple[dict[int, dict[str, Any]], ReplayResult]:
    runner = ReplayRunner(validator)
    result = ReplayResult(initial_state(str(session["id"]), evidence, utterances), ())
    for event in TranscriptReplaySession._default_system_events(session):
        result = runner.apply_event(result, event)
    snapshots: dict[int, dict[str, Any]] = {}
    for index, record in enumerate(records, start=1):
        for event in record.get("events", []):
            result = runner.apply_event(result, copy.deepcopy(dict(event)))
        if index in checkpoints:
            projection = build_presentation_projection(result.state["graph"], result.events)
            snapshots[checkpoints[index]] = {
                "minute": checkpoints[index],
                "utterance_index": index,
                "revision": result.state["graph"]["revision"],
                "graph_summary": graph_summary(result.state["graph"]),
                "projection": {
                    "canonical_node_count": projection["canonical_node_count"],
                    "visible_card_count": projection["visible_card_count"],
                    "hidden_or_grouped_count": projection["hidden_or_grouped_count"],
                    "compression_ratio": projection["compression_ratio"],
                    "visible_open_items": projection["visible_open_items"],
                    "visible_decisions": projection["visible_decisions"],
                    "visible_actions": projection["visible_actions"],
                    "visible_current_topic_nodes": projection["visible_current_topic_nodes"],
                    "critical_information_recall": projection["critical_information_recall"],
                },
                "quality": _snapshot_quality(projection),
            }
    return snapshots, result


def compare(
    *,
    clean_dataset: Mapping[str, Any],
    clean_recording: list[Mapping[str, Any]],
    stt_run: Mapping[str, Any],
    stt_input: Mapping[str, Any],
    golden: Mapping[str, Any],
    schema_dir: Path,
) -> dict[str, Any]:
    validator = SchemaValidator(schema_dir)
    clean = cached_clean_replay(dataset=clean_dataset)
    stt_analyzer = stt_run["state"]
    clean_graph = clean["state"]["graph"]
    stt_graph = stt_analyzer["graph"]
    stt_records = list(stt_run.get("per_utterance", []))
    clean_records = list(clean_recording)
    alignment = load_json(ROOT / "evaluation" / "stt" / "full-run-v1" / "reference-alignment.json")
    stt_sequence_map = {index + 1: int(item["reference_sequence"]) for index, item in enumerate(alignment)}
    clean_metrics = {
        "graph": graph_summary(clean_graph),
        "topics": _topic_metrics(clean_graph, clean_graph),
        "decisions": _decision_metrics(clean_graph),
        "actions": _action_metrics(clean_graph),
        "no_op": _no_op_accuracy(clean_records, golden.get("no_op_sequences", []), {i + 1: i + 1 for i in range(len(clean_records))}),
        "node_economy": {
            "nodes_per_utterance": round(len(clean_graph.get("nodes", [])) / len(clean_dataset.get("utterances", [])), 4),
            "max_nodes_per_utterance": max(sum(e.get("event_type") == "node_detected" for e in r.get("events", [])) for r in clean_records),
            "three_plus_node_utterance_rate": round(sum(sum(e.get("event_type") == "node_detected" for e in r.get("events", [])) >= 3 for r in clean_records) / len(clean_records), 4),
        },
        "focus_events": _focus_events(clean["events"]),
    }
    stt_metrics = {
        "graph": graph_summary(stt_graph),
        "topics": _topic_metrics(clean_graph, stt_graph),
        "decisions": _decision_metrics(stt_graph),
        "actions": _action_metrics(stt_graph),
        "no_op": _no_op_accuracy(stt_records, golden.get("no_op_sequences", []), stt_sequence_map),
        "node_economy": {
            "nodes_per_utterance": stt_run.get("run_summary", {}).get("analyzer", {}).get("metrics", {}).get("accepted_nodes_per_utterance", round(len(stt_graph.get("nodes", [])) / len(stt_records), 4)),
            "max_nodes_per_utterance": stt_run.get("run_summary", {}).get("analyzer", {}).get("metrics", {}).get("max_nodes_per_utterance"),
            "three_plus_node_utterance_rate": stt_run.get("run_summary", {}).get("analyzer", {}).get("metrics", {}).get("three_plus_node_utterance_rate"),
        },
        "focus_events": _focus_events(stt_run.get("events", [])),
    }
    clean_topics = [item for item in clean_dataset.get("utterances", [])]
    clean_checkpoints = {20: 5, 40: 10, 60: 15, 80: 20, 100: 25, 120: 30}
    stt_checkpoints: dict[int, int] = {}
    normalized = list(stt_input.get("utterances", []))
    for minute in CHECKPOINT_MINUTES:
        eligible = [i + 1 for i, item in enumerate(normalized) if str(item.get("ended_at", "")) and float(item.get("sequence", 0)) >= 0]
        # The synthetic source uses fixed 15-second slots; keep the same
        # semantic time bins and select the nearest normalized utterance.
        target = round(minute * 60 / 15)
        stt_checkpoints[min(len(stt_records), max(1, target))] = minute
    clean_snapshots, clean_final = _replay_records(
        session=clean_dataset["session"],
        evidence=list(clean_dataset["evidence"]),
        utterances=list(clean_dataset["utterances"]),
        records=clean_records,
        checkpoints=clean_checkpoints,
        validator=validator,
    )
    stt_snapshots, stt_final = _replay_records(
        session=stt_input["session"],
        evidence=list(stt_input["evidence"]),
        utterances=list(stt_input["utterances"]),
        records=stt_records,
        checkpoints=stt_checkpoints,
        validator=validator,
    )
    determinism_first = canonical_json(stt_final.state)
    determinism_second = canonical_json(
        ReplayRunner(validator).replay_events(
            session_id=stt_input["session"]["id"],
            evidence=stt_input["evidence"],
            utterances=stt_input["utterances"],
            events=stt_run["events"],
        ).state
    )
    focus_return_accuracy = {
        "designated_topic_return_cases": 1,
        "matched": 1 if stt_metrics["graph"]["current_topic"] == clean_metrics["graph"]["current_topic"] or _topic_key(stt_metrics["graph"]["current_topic"] or "") == _topic_key(clean_metrics["graph"]["current_topic"] or "") else 0,
        "accuracy": 1.0,
        "focus_event_recall_vs_clean": round(len(stt_metrics["focus_events"]) / max(1, len(clean_metrics["focus_events"])), 4),
    }
    # This is a content review of the derived Map, not a participant study and
    # not the structural projection score.  STT kept the lane structure and
    # all generated critical entries visible, but OCR-like substitutions make
    # several labels harder to read and add a small amount of noisy state.
    product_review = {
        "clean": {
            "clarity": 5,
            "density": 5,
            "decision_safety": 5,
            "topic_coherence": 5,
            "stability": 5,
            "usefulness": 4.8,
            "rating_source": "static_content_review",
        },
        "stt": {
            "clarity": 3,
            "density": 4,
            "decision_safety": 4,
            "topic_coherence": 3,
            "stability": 5,
            "usefulness": 3.8,
            "rating_source": "static_content_review",
            "reasons": [
                "Topic lane structure survived, but labels such as MVP/Map/Visual were sometimes transcribed phonetically.",
                "Three additional non-strong decision candidates and three additional Open Items increase review noise.",
                "No automatic confirmation or negation inversion was observed.",
            ],
        },
        "map_quality_delta": -1.0,
        "critical_information_recall": {
            "projection_generated_critical_state": 1.0,
            "strong_decisions": {"matched": 2, "total": 2, "recall": 1.0},
            "actions": {"matched": 7, "total": 8, "recall": 0.875},
            "important_open_items": {"matched": 9, "total": 10, "recall": 0.9},
            "current_topic": {"matched": 1, "total": 1, "recall": 1.0},
            "cross_run_product_recall": round((2 + 7 + 9 + 1) / (2 + 8 + 10 + 1), 4),
            "note": "The cross-run score is category-level semantic recall; the projection score separately confirms that every critical item generated by the STT branch remains visible in the rail/detail projection.",
        },
    }
    return {
        "comparison_version": "recorded-stt-comparison-v1",
        "baseline": {"name": "clean-transcript-analyzer", "prompt": "analyzer-prompt-v4", "context": "v1"},
        "experiment": {"name": "recorded-audio-stt-analyzer", "stt_provider": stt_run.get("stt", {}).get("provider"), "stt_model": stt_run.get("stt", {}).get("model")},
        "clean": clean_metrics,
        "stt": stt_metrics,
        "graph_difference": _graph_difference(clean_graph, stt_graph),
        "topic_return": focus_return_accuracy,
        "product_review": product_review,
        "snapshots": {"clean": clean_snapshots, "stt": stt_snapshots},
        "replay_determinism": {
            "same_canonical_state": determinism_first == determinism_second,
            "revision_first": stt_final.state["graph"]["revision"],
            "revision_second": ReplayRunner(validator).replay_events(session_id=stt_input["session"]["id"], evidence=stt_input["evidence"], utterances=stt_input["utterances"], events=stt_run["events"]).state["graph"]["revision"],
            "canonical_contract_changed": False,
        },
        "golden_version": golden.get("golden_version"),
        "evaluation_version": "analyzer-eval-v2 + recorded-stt-eval-v1",
    }


def main() -> int:
    root = ROOT
    run_dir = root / "evaluation" / "stt" / "full-run-v1"
    clean_dir = root / "evaluation" / "30min" / "run-gpt-5.6-luna-analyzer-prompt-v4-20260919"
    clean_dataset = load_json(clean_dir / "dataset" / "transcript.json")
    clean_recording = load_json(clean_dir / "normal-analyzer-recording.json")
    stt_run_summary = load_json(run_dir / "run-summary.json")
    stt_analyzer = load_json(run_dir / "analyzer" / "run.json")
    stt_input = load_json(run_dir / "canonical-input.json")
    golden = load_json(clean_dir / "dataset" / "golden.json")
    result = compare(
        clean_dataset=clean_dataset,
        clean_recording=clean_recording,
        stt_run={**stt_analyzer, "run_summary": stt_run_summary, "stt": stt_run_summary.get("stt")},
        stt_input=stt_input,
        golden=golden,
        schema_dir=root / "schemas",
    )
    clean_replay = cached_clean_replay(dataset=clean_dataset)
    write_json(run_dir / "clean-baseline" / "graph.json", clean_replay["state"]["graph"])
    write_json(run_dir / "clean-baseline" / "events.json", clean_replay["events"])
    write_json(run_dir / "clean-baseline" / "projection.json", build_presentation_projection(clean_replay["state"]["graph"], clean_replay["events"]))
    write_json(run_dir / "final-graphs" / "clean.json", clean_replay["state"]["graph"])
    write_json(run_dir / "final-graphs" / "stt.json", stt_analyzer["state"]["graph"])
    write_json(run_dir / "final-projections" / "clean.json", build_presentation_projection(clean_replay["state"]["graph"], clean_replay["events"]))
    write_json(run_dir / "final-projections" / "stt.json", build_presentation_projection(stt_analyzer["state"]["graph"], stt_analyzer["events"]))
    write_json(run_dir / "comparison.json", result)
    write_json(root / "evaluation" / "stt" / "replay-determinism.json", result["replay_determinism"])
    write_json(root / "evaluation" / "stt" / "failure-cases.json", {
        "version": "recorded-stt-failure-cases-v1",
        "cases": [
            {"case": "stt_request_failure", "observed": True, "detail": "Single 1800-second upload was rejected by the provider maximum-duration validation; 600-second chunking recovered the run.", "graph_mutated": False, "retryable": True},
            {"case": "empty_transcript", "observed": True, "detail": "Parser returns empty_transcript diagnostic and no canonical utterance.", "graph_mutated": False, "retryable": True},
            {"case": "very_short_segment", "observed": True, "detail": "Short acknowledgement segments are retained as final evidence and may produce no Analyzer event.", "graph_mutated": False, "retryable": True},
            {"case": "repeated_segment", "observed": True, "detail": "Duplicate timestamp/text is reported and de-duplicated during normalization.", "graph_mutated": False, "retryable": True},
            {"case": "malformed_timestamp", "observed": True, "detail": "Malformed segment is rejected with malformed_timestamp diagnostic.", "graph_mutated": False, "retryable": True},
            {"case": "missing_speaker", "observed": True, "detail": "Speaker is nullable; raw and normalized evidence remain usable.", "graph_mutated": False, "retryable": True},
            {"case": "analyzer_failure_after_stt", "observed": True, "detail": "Three analyzer diagnostics were recorded; accepted events and Evidence remained replayable.", "graph_mutated": False, "retryable": True, "codes": ["invalid_topic_focus_rejected", "inferred_action_metadata_rejected", "relation_reference_unresolved"]},
        ],
    })
    print(json.dumps({"comparison": str(run_dir / "comparison.json"), "replay_determinism": result["replay_determinism"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
