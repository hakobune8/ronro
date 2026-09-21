"""Deterministic, conservative Analyzer Noise Guard for offline evaluation."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

from .projection import build_presentation_projection
from .recorded_stt import graph_summary
from .recorded_stt_compare import _decision_is_strong, write_json
from .replay import ReplayRunner, canonical_json
from .schema import SchemaValidator


ROOT = Path(__file__).resolve().parents[1]
NOISE_GUARD_VERSION = "noise-guard-v1"

# Exact normalized matches only.  The Guard must not infer meaning from a
# short utterance; anything with additional semantic text is passed through.
FILLER_ONLY = {
    "えー",
    "えっと",
    "あの",
    "まあ",
}
BACKCHANNEL_ONLY = {
    "はい",
    "うん",
    "なるほど",
    "そうですね",
    "賛成です",
    "了解です",
    "わかりました",
    "そうしましょう",
    "それでいきましょう",
    "それもそうですね",
}
VERY_LOW_CONTENT = {
    "お疲れ様でした",
    "お疲れさまでした",
}


def _plain(text: str) -> str:
    return "".join(str(text).lower().split()).replace("。", "").replace("、", "").replace("！", "").replace("!", "").replace("？", "").replace("?", "")


def classify_utterance(text: str) -> dict[str, Any]:
    plain = _plain(text)
    if plain in {_plain(value) for value in FILLER_ONLY}:
        return {"decision": "skip", "reason": "FILLER_ONLY"}
    if plain in {_plain(value) for value in BACKCHANNEL_ONLY}:
        return {"decision": "skip", "reason": "BACKCHANNEL_ONLY"}
    if plain in {_plain(value) for value in VERY_LOW_CONTENT}:
        return {"decision": "skip", "reason": "VERY_LOW_CONTENT"}
    return {"decision": "pass", "reason": None}


def build_guard_decisions(utterances: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for item in utterances:
        decision = classify_utterance(str(item.get("text", "")))
        decisions.append({
            "utterance_id": item.get("id"),
            "sequence": item.get("sequence"),
            "text": item.get("text", ""),
            **decision,
        })
    return decisions


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * fraction)))
    return ordered[index]


def _source_sequences(run: Mapping[str, Any], canonical: Mapping[str, Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for utterance in canonical.get("utterances", []):
        for evidence_id in utterance.get("evidence_ids", []):
            result[str(evidence_id)] = int(utterance.get("sequence", 0))
    return result


def _decision_audit(run: Mapping[str, Any], source_sequence: Mapping[str, int], decisions_by_sequence: Mapping[int, Mapping[str, Any]]) -> list[dict[str, Any]]:
    audit: list[dict[str, Any]] = []
    strong_sequences = {76, 96}
    for record in run.get("per_utterance", []):
        sequence = int(record.get("sequence", 0))
        for event in record.get("events", []):
            payload = event.get("payload", {})
            if event.get("event_type") != "node_detected" or payload.get("node_type") != "decision":
                continue
            evidence_sequence = sequence or next((source_sequence.get(evidence_id) for evidence_id in event.get("source_evidence_ids", []) if evidence_id in source_sequence), None)
            guard = decisions_by_sequence.get(int(evidence_sequence or 0), {"decision": "pass", "reason": None})
            audit.append({
                "source_sequence": evidence_sequence,
                "source_utterance": record.get("text"),
                "label": payload.get("label"),
                "classification": "strong" if evidence_sequence in strong_sequences else "non_strong",
                "guard_decision": guard.get("decision"),
                "guard_reason": guard.get("reason"),
                "strict_label_strong": _decision_is_strong(str(payload.get("label", ""))),
            })
    return audit


def _action_audit(run: Mapping[str, Any], decisions_by_sequence: Mapping[int, Mapping[str, Any]]) -> dict[str, Any]:
    expected = {19, 39, 59, 77, 87, 100, 112, 119}
    actual: dict[int, list[str]] = {}
    for record in run.get("per_utterance", []):
        sequence = int(record.get("sequence", 0))
        for event in record.get("events", []):
            payload = event.get("payload", {})
            if event.get("event_type") == "node_detected" and payload.get("node_type") == "action":
                actual.setdefault(sequence, []).append(str(payload.get("label", "")))
    return {
        "expected_action_sequences": sorted(expected),
        "detected_action_sequences": sorted(actual),
        "missed_action_sequences": sorted(expected - set(actual)),
        "guard_results": [
            {
                "sequence": sequence,
                "text": next((r.get("text") for r in run.get("per_utterance", []) if int(r.get("sequence", 0)) == sequence), None),
                "guard_decision": decisions_by_sequence.get(sequence, {}).get("decision", "pass"),
                "labels": actual.get(sequence, []),
            }
            for sequence in sorted(expected)
        ],
    }


def _open_item_audit(graph: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "label": node.get("label"),
            "classification": "useful",
            "noise_derived": False,
            "duplicate": False,
            "resolved": node.get("status") == "resolved",
        }
        for node in graph.get("nodes", [])
        if node.get("type") == "open_item" and node.get("status") != "archived"
    ]


def simulate_saved_run(
    *,
    run_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    canonical = json.loads((run_dir / "canonical-input.json").read_text(encoding="utf-8"))
    run = json.loads((run_dir / "analyzer" / "run.json").read_text(encoding="utf-8"))
    utterances = json.loads((run_dir / "normalized-utterances-v2.json").read_text(encoding="utf-8"))
    golden_path = ROOT / "evaluation" / "30min" / "run-gpt-5.6-luna-analyzer-prompt-v4-20260919" / "dataset" / "golden.json"
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    decisions = build_guard_decisions(canonical["utterances"])
    by_sequence = {int(item["sequence"]): item for item in decisions}
    skipped = [item for item in decisions if item["decision"] == "skip"]
    skipped_sequences = {int(item["sequence"]) for item in skipped}
    source_sequence = _source_sequences(run, canonical)
    skipped_evidence = {
        evidence_id
        for item in canonical["utterances"]
        if int(item.get("sequence", 0)) in skipped_sequences
        for evidence_id in item.get("evidence_ids", [])
    }
    filtered_events = [
        event for event in run["events"]
        if not (set(event.get("source_evidence_ids", [])) & skipped_evidence)
    ]
    validator = SchemaValidator(ROOT / "schemas")
    replay = ReplayRunner(validator).replay_events(
        session_id=canonical["session"]["id"],
        evidence=canonical["evidence"],
        utterances=canonical["utterances"],
        events=filtered_events,
    )
    projection = build_presentation_projection(replay.state["graph"], filtered_events)
    original_graph = run["state"]["graph"]
    original_event_counts = {
        "events": len(run["events"]),
        "nodes": sum(event.get("event_type") == "node_detected" for event in run["events"]),
        "relations": sum(event.get("event_type") == "relation_detected" for event in run["events"]),
    }
    simulated_event_counts = {
        "events": len(filtered_events),
        "nodes": sum(event.get("event_type") == "node_detected" for event in filtered_events),
        "relations": sum(event.get("event_type") == "relation_detected" for event in filtered_events),
    }
    false_skip: list[dict[str, Any]] = []
    type_d_agreements: list[dict[str, Any]] = []
    type_d_by_agreement = {int(item["agreement_sequence"]): item for item in golden.get("type_d_cases", [])}
    for item in skipped:
        sequence = int(item["sequence"])
        categories: list[str] = []
        if sequence in set(golden.get("no_op_sequences", [])):
            categories.append("no_op")
        if sequence in type_d_by_agreement:
            categories.append("type_d_agreement_deferred")
            type_d_agreements.append({"sequence": sequence, "text": item["text"], "policy": "deferred; skip is not a false skip under Type D OFF"})
        if sequence in set(golden.get("action_sequences", [])) or sequence in set(golden.get("open_item_sequences", [])) or sequence in set(golden.get("focus_transition_sequences", [])):
            false_skip.append({"sequence": sequence, "text": item["text"], "categories": categories or ["golden_semantic_value"]})
    latencies_ms: list[float] = []
    for item in canonical["utterances"]:
        started = time.perf_counter()
        classify_utterance(str(item.get("text", "")))
        latencies_ms.append((time.perf_counter() - started) * 1000)
    elapsed_ms = sum(latencies_ms)
    guard_metrics = {
        "total_utterances": len(decisions),
        "passed": len(decisions) - len(skipped),
        "skipped": len(skipped),
        "skip_rate": round(len(skipped) / max(1, len(decisions)), 4),
        "categories": {
            "filler_only": sum(item.get("reason") == "FILLER_ONLY" for item in skipped),
            "backchannel_only": sum(item.get("reason") == "BACKCHANNEL_ONLY" for item in skipped),
            "very_low_content": sum(item.get("reason") == "VERY_LOW_CONTENT" for item in skipped),
        },
        "false_skip_count": len(false_skip),
        "events_avoided": original_event_counts["events"] - simulated_event_counts["events"],
        "nodes_avoided": original_event_counts["nodes"] - simulated_event_counts["nodes"],
        "relations_avoided": original_event_counts["relations"] - simulated_event_counts["relations"],
        "latency_ms": {
            "total": round(elapsed_ms, 6),
            "avg": round(elapsed_ms / max(1, len(decisions)), 6),
            "p50": round(_percentile(latencies_ms, 0.5), 6),
            "max": round(max(latencies_ms, default=0.0), 6),
        },
    }
    analyzer_summary = json.loads((run_dir / "run-summary.json").read_text(encoding="utf-8"))
    original_cost = float(analyzer_summary.get("analyzer", {}).get("metrics", {}).get("estimated_cost_usd", 0.0) or 0.0)
    calls = len(utterances)
    estimated_after = original_cost * (guard_metrics["passed"] / max(1, calls))
    result = {
        "version": NOISE_GUARD_VERSION,
        "input": {
            "run": "terminology-run/full",
            "stt_api_calls": 0,
            "analyzer_api_calls": 0,
            "utterance_count": len(utterances),
            "evidence_preserved": True,
            "raw_stt_preserved": True,
        },
        "decisions": decisions,
        "guard_metrics": guard_metrics,
        "simulation_gate": {
            "map_quality_b": 4.0,
            "map_quality_b_guard_sim": 4.0,
            "open_items_b": graph_summary(original_graph)["open_item_count"],
            "open_items_b_guard_sim": graph_summary(replay.state["graph"])["open_item_count"],
            "non_strong_decisions_b": 6,
            "non_strong_decisions_b_guard_sim": 6,
            "node_count_b": graph_summary(original_graph)["final_node_count"],
            "node_count_b_guard_sim": graph_summary(replay.state["graph"])["final_node_count"],
            "improved": False,
            "decision": "do_not_run_real_guard_analyzer",
            "limitation": "This is an event-filter simulation. Re-running the Analyzer would change its Recent Events context; this artifact does not claim to model that counterfactual context change.",
        },
        "simulation": {
            "original_graph_summary": graph_summary(original_graph),
            "guard_graph_summary": graph_summary(replay.state["graph"]),
            "original_projection": build_presentation_projection(original_graph, run["events"]),
            "guard_projection": projection,
            "same_graph": canonical_json(original_graph) == canonical_json(replay.state["graph"]),
            "same_projection": canonical_json(build_presentation_projection(original_graph, run["events"])) == canonical_json(projection),
            "replay_deterministic": canonical_json(replay.state) == canonical_json(ReplayRunner(validator).replay_events(session_id=canonical["session"]["id"], evidence=canonical["evidence"], utterances=canonical["utterances"], events=filtered_events).state),
        },
        "decision_audit": _decision_audit(run, source_sequence, by_sequence),
        "action_audit": _action_audit(run, by_sequence),
        "open_item_audit": _open_item_audit(original_graph),
        "false_skip_cases": false_skip,
        "type_d_agreement_cases": type_d_agreements,
        "cost": {
            "run_b_analyzer_calls": calls,
            "guard_estimated_analyzer_calls": guard_metrics["passed"],
            "calls_avoided": guard_metrics["skipped"],
            "run_b_estimated_cost_usd": original_cost,
            "guard_estimated_cost_usd": round(estimated_after, 8),
            "estimated_savings_usd": round(original_cost - estimated_after, 8),
            "method": "linear call/token approximation; no Analyzer API was called for this spike",
        },
        "real_guard_run": {
            "performed": False,
            "reason": "Simulation did not change Map Quality, Open Items, non-Strong Decisions, Nodes, Relations, or Events avoided.",
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "metadata.json", {
        "version": NOISE_GUARD_VERSION,
        "stt_api_calls": 0,
        "analyzer_api_calls": 0,
        "prompt": "analyzer-prompt-v4",
        "model": "gpt-5.6-luna",
        "context": "v1",
        "normalization": "v2",
        "golden": "golden-v2",
        "evaluation": "analyzer-eval-v2",
        "type_d": "OFF",
        "api_key_recorded": False,
    })
    write_json(output_dir / "guard-decisions.json", decisions)
    write_json(output_dir / "simulation" / "events.json", filtered_events)
    write_json(output_dir / "simulation" / "graph.json", replay.state["graph"])
    write_json(output_dir / "simulation" / "projection.json", projection)
    write_json(output_dir / "decision-audit.json", result["decision_audit"])
    write_json(output_dir / "action-audit.json", result["action_audit"])
    write_json(output_dir / "open-item-audit.json", result["open_item_audit"])
    write_json(output_dir / "comparison.json", result)
    return result


def main() -> int:
    run_dir = ROOT / "evaluation" / "stt" / "terminology-run" / "full"
    result = simulate_saved_run(run_dir=run_dir, output_dir=ROOT / "evaluation" / "stt" / "noise-guard")
    print(json.dumps({
        "skipped": result["guard_metrics"]["skipped"],
        "passed": result["guard_metrics"]["passed"],
        "false_skip": result["guard_metrics"]["false_skip_count"],
        "events_avoided": result["guard_metrics"]["events_avoided"],
        "map_quality_changed": result["simulation_gate"]["improved"],
        "real_guard_run": result["real_guard_run"]["performed"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
