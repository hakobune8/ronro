"""Offline evaluation harness for the opt-in Type D decision layer.

The harness deliberately does not call an LLM.  It builds a small canonical
Graph-like context from annotated proposal fixtures, compares the frozen
normal Analyzer behavior (agreement-only -> no-op) with the deterministic
TypeDDecisionLayer, validates emitted events, and records proposal-window
trade-offs.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any, Mapping

from .schema import SchemaValidator
from .type_d_decision import TypeDDecisionLayer


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "evaluation" / "type-d-spike" / "dataset.json"
DEFAULT_OUTPUT = ROOT / "evaluation" / "runs" / "type-d-multiturn-spike-v1"
WINDOWS = (
    "last_1_semantic_event",
    "last_2_semantic_events",
    "current_topic_latest_proposal",
)
HUMAN_EVENTS = {
    "confirm_decision",
    "revoke_decision",
    "rename_node",
    "archive_node",
    "merge_nodes",
    "move_to_parking_lot",
    "restore_from_parking_lot",
    "update_action",
    "set_current_topic",
    "undo_last_correction",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_case(case: Mapping[str, Any]) -> dict[str, Any]:
    session_id = str(case["session_id"])
    topic = case["topic"]
    current_topic_id = str(case.get("current_topic_id") or topic["id"])
    topics = [topic, *case.get("additional_topics", [])]
    evidence: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    recent_events: list[dict[str, Any]] = []

    for index, topic_item in enumerate(topics, start=1):
        nodes.append(
            {
                "id": topic_item["id"],
                "session_id": session_id,
                "type": "topic",
                "label": topic_item["label"],
                "status": "active",
                "source_event_ids": [],
                "evidence_ids": [],
            }
        )

    for index, proposal in enumerate(case.get("proposals", []), start=1):
        event_id = f"proposal:{session_id}:{index:02d}"
        evidence_id = proposal["evidence_id"]
        topic_id = proposal.get("topic_id", topic["id"])
        evidence.append(
            {
                "id": evidence_id,
                "session_id": session_id,
                "sequence": index,
                "timestamp": f"2026-09-21T12:00:{index:02d}Z",
                "speaker": "A",
                "text": proposal["label"],
            }
        )
        nodes.append(
            {
                "id": proposal["id"],
                "session_id": session_id,
                "type": proposal["type"],
                "label": proposal["label"],
                "status": "active",
                "source_event_ids": [event_id],
                "evidence_ids": [evidence_id],
            }
        )
        relation_type = "has_option" if proposal["type"] == "option" else "contains"
        edges.append(
            {
                "id": f"edge:{session_id}:{relation_type}:{topic_id}:{proposal['id']}",
                "source_node_id": topic_id,
                "target_node_id": proposal["id"],
                "type": relation_type,
                "source_event_ids": [event_id],
            }
        )
        recent_events.append(
            {
                "event_id": event_id,
                "session_id": session_id,
                "sequence": index,
                "event_type": "node_detected",
                "occurred_at": f"2026-09-21T12:00:{index:02d}Z",
                "actor": "analyzer",
                "source_evidence_ids": [evidence_id],
                "payload": {"node_type": proposal["type"], "label": proposal["label"]},
            }
        )

    existing_candidate = case.get("existing_candidate")
    if existing_candidate:
        evidence_id = existing_candidate["evidence_id"]
        event_id = f"candidate:{session_id}:01"
        evidence.append(
            {
                "id": evidence_id,
                "session_id": session_id,
                "sequence": len(evidence) + 1,
                "timestamp": "2026-09-21T12:00:10Z",
                "speaker": "A",
                "text": existing_candidate["label"],
            }
        )
        nodes.append(
            {
                "id": existing_candidate["id"],
                "session_id": session_id,
                "type": "decision",
                "label": existing_candidate["label"],
                "status": "candidate",
                "source_event_ids": [event_id],
                "evidence_ids": [evidence_id],
            }
        )
        edges.append(
            {
                "id": f"edge:{session_id}:contains:{topic['id']}:{existing_candidate['id']}",
                "source_node_id": topic["id"],
                "target_node_id": existing_candidate["id"],
                "type": "contains",
                "source_event_ids": [event_id],
            }
        )
        recent_events.append(
            {
                "event_id": event_id,
                "session_id": session_id,
                "sequence": len(recent_events) + 1,
                "event_type": "node_detected",
                "occurred_at": "2026-09-21T12:00:10Z",
                "actor": "analyzer",
                "source_evidence_ids": [evidence_id],
                "payload": {"node_type": "decision", "label": existing_candidate["label"]},
            }
        )

    agreement = case["agreement"]
    evidence.append(
        {
            "id": agreement["evidence_id"],
            "session_id": session_id,
            "sequence": agreement["sequence"],
            "timestamp": "2026-09-21T12:00:20Z",
            "speaker": agreement["speaker"],
            "text": agreement["text"],
        }
    )
    graph = {
        "session_id": session_id,
        "revision": 0,
        "last_event_sequence": len(recent_events),
        "nodes": nodes,
        "edges": edges,
        "current_topic": {
            "primary_topic_id": current_topic_id,
            "mode": "derived",
            "source_event_ids": [],
        },
    }
    utterance = {
        "id": agreement["id"],
        "session_id": session_id,
        "sequence": agreement["sequence"],
        "evidence_ids": [agreement["evidence_id"]],
        "text": agreement["text"],
        "started_at": "2026-09-21T12:00:20Z",
        "ended_at": "2026-09-21T12:00:20Z",
    }
    return {
        "case": copy.deepcopy(dict(case)),
        "evidence": evidence,
        "utterance": utterance,
        "graph": graph,
        "recent_events": recent_events,
    }


def candidate_events(layer: TypeDDecisionLayer, built: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates = layer.analyze(
        built["utterance"],
        built["graph"],
        built["recent_events"],
    )
    return [candidate.to_event(index) for index, candidate in enumerate(candidates, start=1)]


def decision_count(events: list[dict[str, Any]]) -> int:
    return sum(
        event.get("event_type") == "node_detected"
        and event.get("payload", {}).get("node_type") == "decision"
        for event in events
    )


def evaluate_variant(
    cases: list[Mapping[str, Any]],
    *,
    validator: SchemaValidator,
    proposal_window: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    case_results: list[dict[str, Any]] = []
    for case in cases:
        built = build_case(case)
        layer = TypeDDecisionLayer(proposal_window=proposal_window)
        first = candidate_events(layer, built)
        first_trace = copy.deepcopy(layer.last_trace)
        second = candidate_events(TypeDDecisionLayer(proposal_window=proposal_window), built)
        for event in first:
            validator.validate_event(event)
        deterministic = first == second
        expected = case["expected"]
        predicted = decision_count(first) > 0
        automatic_confirmation = any(
            event.get("event_type") in HUMAN_EVENTS for event in first
        )
        ambiguous_rejected = bool(expected.get("ambiguous")) and not predicted
        existing_duplicate = bool(expected.get("existing_candidate")) and predicted
        case_results.append(
            {
                "case_id": case["case_id"],
                "category": case["category"],
                "proposal_window": proposal_window,
                "expected_candidate": bool(expected.get("candidate")),
                "predicted_candidate": predicted,
                "candidate_event_count": decision_count(first),
                "false_candidate": predicted and not bool(expected.get("candidate")),
                "ambiguous": bool(expected.get("ambiguous")),
                "ambiguous_rejected": ambiguous_rejected,
                "existing_candidate": bool(expected.get("existing_candidate")),
                "existing_candidate_duplicate": existing_duplicate,
                "automatic_confirmation": automatic_confirmation,
                "deterministic": deterministic,
                "trace": first_trace,
                "events": first,
            }
        )

    expected_positive = sum(item["expected_candidate"] for item in case_results)
    predicted_positive = sum(item["predicted_candidate"] for item in case_results)
    true_positive = sum(
        item["expected_candidate"] and item["predicted_candidate"]
        for item in case_results
    )
    ambiguous_total = sum(item["ambiguous"] for item in case_results)
    duplicate_total = sum(item["existing_candidate"] for item in case_results)
    summary = {
        "case_count": len(case_results),
        "expected_positive": expected_positive,
        "predicted_positive": predicted_positive,
        "true_positive": true_positive,
        "type_d_precision": round(true_positive / predicted_positive, 4) if predicted_positive else None,
        "type_d_recall": round(true_positive / expected_positive, 4) if expected_positive else None,
        "false_candidate_count": sum(item["false_candidate"] for item in case_results),
        "ambiguous_reference_rejection_accuracy": round(
            sum(item["ambiguous_rejected"] for item in case_results) / ambiguous_total, 4
        ) if ambiguous_total else None,
        "ambiguous_cases": ambiguous_total,
        "existing_candidate_duplicate_rate": round(
            sum(item["existing_candidate_duplicate"] for item in case_results) / duplicate_total, 4
        ) if duplicate_total else None,
        "existing_candidate_cases": duplicate_total,
        "automatic_confirmation": sum(item["automatic_confirmation"] for item in case_results),
        "determinism_failures": sum(not item["deterministic"] for item in case_results),
        "candidate_increase_over_normal": predicted_positive,
    }
    return case_results, summary


def run(args: argparse.Namespace) -> int:
    dataset = read_json(args.dataset)
    cases = dataset.get("cases", [])
    validator = SchemaValidator(args.schema_dir)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Normal Analyzer v4 treats agreement-only utterances as no-op.  The
    # baseline is therefore deterministic and requires no API call.
    baseline_cases = [
        {
            "case_id": case["case_id"],
            "expected_candidate": bool(case["expected"].get("candidate")),
            "predicted_candidate": False,
            "false_candidate": False,
            "automatic_confirmation": False,
        }
        for case in cases
    ]
    positives = sum(item["expected_candidate"] for item in baseline_cases)
    baseline_summary = {
        "case_count": len(cases),
        "expected_positive": positives,
        "predicted_positive": 0,
        "true_positive": 0,
        "type_d_precision": None,
        "type_d_recall": 0.0 if positives else None,
        "false_candidate_count": 0,
        "ambiguous_reference_rejection_accuracy": 1.0,
        "existing_candidate_duplicate_rate": 0.0,
        "automatic_confirmation": 0,
        "candidate_increase_over_normal": 0,
    }
    default_results, default_summary = evaluate_variant(
        cases,
        validator=validator,
        proposal_window="current_topic_latest_proposal",
    )
    window_comparison: dict[str, Any] = {}
    for window in WINDOWS:
        _, window_summary = evaluate_variant(cases, validator=validator, proposal_window=window)
        window_comparison[window] = window_summary

    metadata = {
        "run_id": output_dir.name,
        "run_kind": "type_d_multiturn_decision_spike",
        "dataset_version": dataset.get("dataset_version"),
        "case_count": len(cases),
        "model": "gpt-5.6-luna",
        "reasoning_effort": "medium",
        "prompt_version": "analyzer-prompt-v4",
        "context_strategy": "v1",
        "golden_version": "golden-v2",
        "evaluation_version": "analyzer-eval-v2",
        "additional_llm_calls": 0,
        "canonical_contract_changed": False,
        "normal_analyzer_baseline": "agreement-only -> events: []",
        "recommended_proposal_window": "current_topic_latest_proposal",
    }
    write_json(output_dir / "metadata.json", metadata)
    write_json(output_dir / "baseline.json", {"summary": baseline_summary, "cases": baseline_cases})
    write_json(output_dir / "multiturn-cases.json", default_results)
    summary = {
        "run_id": output_dir.name,
        "baseline_normal_analyzer": baseline_summary,
        "multiturn_default": default_summary,
        "proposal_window_comparison": window_comparison,
        "map_impact": {
            "baseline_candidate_decisions": 0,
            "multiturn_candidate_decisions": default_summary["predicted_positive"],
            "false_candidates": default_summary["false_candidate_count"],
            "additional_human_confirmation_targets": default_summary["predicted_positive"],
        },
    }
    write_json(output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline Type D decision spike")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--schema-dir", type=Path, default=ROOT / "schemas")
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())

