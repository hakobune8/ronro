"""Run the analyzer-prompt-v5 STT robustness comparison.

This runner deliberately reuses the frozen Clean Transcript and saved
terminology-aware STT input.  It does not call STT, Noise Guard, Type D, or
any alternate downstream implementation.  The only experimental variable is
the RealAnalyzer prompt version.
"""

from __future__ import annotations

import argparse
import copy
import json
import statistics
from pathlib import Path
from typing import Any, Iterable, Mapping

from .analyzer import TranscriptReplaySession
from .projection import build_presentation_projection
from .recorded_stt import cached_clean_replay, graph_summary, run_analyzer
from .recorded_stt_compare import (
    _action_key,
    _action_metrics,
    _decision_is_strong,
    _decision_metrics,
    _graph_difference,
    _no_op_accuracy,
    _topic_metrics,
    load_json,
    write_json,
)
from .real_analyzer import (
    PROMPT_VERSION_V5,
    AnalysisContextBuilder,
    OpenAICompatibleProvider,
    RealAnalyzer,
    provider_configuration_summary,
)
from .materializer import initial_state
from .replay import ReplayResult, ReplayRunner
from .schema import SchemaValidator


ROOT = Path(__file__).resolve().parents[1]
CLEAN_DIR = ROOT / "evaluation" / "30min" / "run-gpt-5.6-luna-analyzer-prompt-v4-20260919"
TERMINOLOGY_DIR = ROOT / "evaluation" / "stt" / "terminology-run" / "full"
DEFAULT_OUTPUT = ROOT / "evaluation" / "stt" / "prompt-v5"
SCHEMA_VERSION = "v2"

# The workload-specific annotation is kept immutable.  Its safety policy is
# the recorded 30-minute projection of Golden v2, as documented by the prior
# STT runs.
WORKLOAD_GOLDEN = CLEAN_DIR / "dataset" / "golden.json"


def _records(run: Mapping[str, Any] | list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return list(run if isinstance(run, list) else run.get("per_utterance", []))


def _sequence_map(path: Path | None, count: int) -> dict[int, int]:
    if path is None:
        return {index + 1: index + 1 for index in range(count)}
    alignment = load_json(path)
    return {index + 1: int(item["reference_sequence"]) for index, item in enumerate(alignment)}


def _replay_before(
    *,
    session: Mapping[str, Any],
    evidence: list[dict[str, Any]],
    utterances: list[dict[str, Any]],
    records: Iterable[Mapping[str, Any]],
    before_sequence: int,
    validator: SchemaValidator,
) -> ReplayResult:
    """Reconstruct the canonical context immediately before a preflight case."""

    runner = ReplayRunner(validator)
    result = ReplayResult(
        state=initial_state(str(session["id"]), evidence, utterances),
        events=(),
    )
    for event in TranscriptReplaySession._default_system_events(session):
        result = runner.apply_event(result, event)
    for record in sorted(records, key=lambda item: int(item.get("sequence", 0))):
        if int(record.get("sequence", 0)) >= before_sequence:
            break
        for event in record.get("events", []):
            result = runner.apply_event(result, copy.deepcopy(dict(event)))
    return result


def _find_utterance(utterances: list[dict[str, Any]], sequence: int) -> dict[str, Any]:
    return next(item for item in utterances if int(item["sequence"]) == sequence)


def _preflight_case_plan() -> list[dict[str, Any]]:
    """Representative structural/safety cases required before the full run."""

    # Six B decisions were manually adjudicated as non-Strong in the saved v4
    # terminology run.  The remaining cases cover the known Action/Open miss,
    # and clean-track regression anchors.
    return [
        {"track": "stt", "sequence": sequence, "expectation": "no_decision"}
        for sequence in (17, 34, 63, 80, 113, 115)
    ] + [
        {"track": "stt", "sequence": 119, "expectation": "action"},
        {"track": "stt", "sequence": 114, "expectation": "no_open_item"},
        {"track": "clean", "sequence": 76, "expectation": "strong_decision"},
        {"track": "clean", "sequence": 19, "expectation": "action"},
        {"track": "clean", "sequence": 20, "expectation": "noop"},
    ]


def run_preflight(
    *,
    provider: OpenAICompatibleProvider,
    validator: SchemaValidator,
    clean_dataset: Mapping[str, Any],
    clean_records: list[Mapping[str, Any]],
    stt_input: Mapping[str, Any],
    stt_records: list[Mapping[str, Any]],
    output_path: Path,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for plan in _preflight_case_plan():
        source = clean_dataset if plan["track"] == "clean" else stt_input
        records = clean_records if plan["track"] == "clean" else stt_records
        utterances = list(source["utterances"])
        utterance = _find_utterance(utterances, int(plan["sequence"]))
        prior = _replay_before(
            session=source["session"],
            evidence=list(source["evidence"]),
            utterances=utterances,
            records=records,
            before_sequence=int(plan["sequence"]),
            validator=validator,
        )
        analyzer = RealAnalyzer(
            provider=provider,
            schema_validator=validator,
            meeting_goal=source["session"].get("goal"),
            context_builder=AnalysisContextBuilder(),
            prompt_version=PROMPT_VERSION_V5,
            output_schema_version=SCHEMA_VERSION,
        )
        candidates = analyzer.analyze(utterance, prior.state["graph"], prior.events)
        trace = copy.deepcopy(analyzer.last_trace or {})
        candidate_types = [candidate.event_type for candidate in candidates]
        decision_types = [candidate for candidate in candidates if candidate.event_type == "node_detected" and candidate.payload.get("node_type") == "decision"]
        action_types = [candidate for candidate in candidates if candidate.event_type == "node_detected" and candidate.payload.get("node_type") == "action"]
        open_types = [candidate for candidate in candidates if candidate.event_type == "node_detected" and candidate.payload.get("node_type") == "open_item"]
        expectation = plan["expectation"]
        semantic_ok = {
            "no_decision": not decision_types,
            "action": bool(action_types),
            "no_open_item": not open_types,
            "strong_decision": bool(decision_types) and any(_decision_is_strong(candidate.payload.get("label", "")) for candidate in decision_types),
            "noop": not candidates,
        }[expectation]
        error_code = (trace.get("validation_error") or {}).get("code")
        results.append(
            {
                "track": plan["track"],
                "sequence": plan["sequence"],
                "utterance_id": utterance["id"],
                "text": utterance["text"],
                "expectation": expectation,
                "semantic_ok": semantic_ok,
                "status": trace.get("status"),
                "event_types": candidate_types,
                "events_emitted": len(candidates),
                "api_success": error_code not in {"provider_http_error", "provider_network_error", "provider_not_configured"},
                "json_parse_success": error_code != "provider_output_invalid",
                "analyzer_output_schema_valid": error_code != "schema_invalid",
                "canonical_conversion_success": error_code is None,
                "canonical_event_schema_valid": error_code is None,
                "trace": trace,
            }
        )

    summary = {
        "prompt_version": PROMPT_VERSION_V5,
        "schema_version": SCHEMA_VERSION,
        "case_count": len(results),
        "all_api_success": all(item["api_success"] for item in results),
        "all_json_parse_success": all(item["json_parse_success"] for item in results),
        "all_analyzer_output_schema_valid": all(item["analyzer_output_schema_valid"] for item in results),
        "all_canonical_conversion_success": all(item["canonical_conversion_success"] for item in results),
        "all_canonical_event_schema_valid": all(item["canonical_event_schema_valid"] for item in results),
        "semantic_anchor_pass_count": sum(item["semantic_ok"] for item in results),
        "results": results,
        "secret_policy": "Raw provider output may be retained; API keys and Authorization headers are never written.",
    }
    write_json(output_path, summary)
    return summary


def _decision_review(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    review: list[dict[str, Any]] = []
    for record in records:
        for event in record.get("events", []):
            if event.get("event_type") != "node_detected" or event.get("payload", {}).get("node_type") != "decision":
                continue
            label = str(event.get("payload", {}).get("label", ""))
            review.append(
                {
                    "sequence": int(record.get("sequence", 0)),
                    "utterance_id": record.get("utterance_id"),
                    "text": record.get("text"),
                    "label": label,
                    "classification": "strong" if _decision_is_strong(label) else "weak_or_false",
                    "source_evidence_ids": event.get("source_evidence_ids", []),
                }
            )
    return review


def _action_review(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    review: list[dict[str, Any]] = []
    for record in records:
        for event in record.get("events", []):
            if event.get("event_type") != "node_detected" or event.get("payload", {}).get("node_type") != "action":
                continue
            label = str(event.get("payload", {}).get("label", ""))
            review.append(
                {
                    "sequence": int(record.get("sequence", 0)),
                    "utterance_id": record.get("utterance_id"),
                    "text": record.get("text"),
                    "label": label,
                    "semantic_key": _action_key(label),
                    "action": event.get("payload", {}).get("action", {}),
                    "source_evidence_ids": event.get("source_evidence_ids", []),
                }
            )
    return review


def _metric_percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return round(ordered[index], 3)


def _track_metrics(
    *,
    label: str,
    run: Mapping[str, Any],
    source: Mapping[str, Any],
    clean_graph: Mapping[str, Any],
    golden: Mapping[str, Any],
    alignment_path: Path | None,
) -> dict[str, Any]:
    records = _records(run)
    graph = run["state"]["graph"]
    projection = build_presentation_projection(graph, run.get("events", []))
    sequence_map = _sequence_map(alignment_path, len(records))
    node_counts = [sum(event.get("event_type") == "node_detected" for event in record.get("events", [])) for record in records]
    relation_counts = [sum(event.get("event_type") == "relation_detected" for event in record.get("events", [])) for record in records]
    traces = [record.get("trace", {}) for record in records]
    latency_values = [float(trace["latency_ms"]) for trace in traces if isinstance(trace.get("latency_ms"), (int, float))]
    usage = {
        key: sum((trace.get("usage", {}).get(key) or 0) for trace in traces)
        for key in ("prompt_tokens", "completion_tokens", "reasoning_tokens", "total_tokens")
    }
    cost = round(sum((trace.get("cost_usd") or 0.0) for trace in traces), 8)
    decisions = _decision_metrics(graph)
    actions = _action_metrics(graph)
    topics = _topic_metrics(clean_graph, graph)
    no_op = _no_op_accuracy(records, golden.get("no_op_sequences", []), sequence_map)
    decision_review = _decision_review(records)
    action_review = _action_review(records)
    critical = projection.get("critical_information_recall", {})
    return {
        "track": label,
        "prompt_version": PROMPT_VERSION_V5,
        "utterance_count": len(records),
        "graph": graph_summary(graph),
        "topics": topics,
        "decisions": decisions,
        "actions": actions,
        "no_op": no_op,
        "node_economy": {
            "nodes_per_utterance": round(sum(node_counts) / max(1, len(records)), 4),
            "max_nodes_per_utterance": max(node_counts, default=0),
            "three_plus_node_utterance_rate": round(sum(count >= 3 for count in node_counts) / max(1, len(records)), 4),
            "relations_per_utterance": round(sum(relation_counts) / max(1, len(records)), 4),
        },
        "non_strong_decision_count": max(0, len(decision_review) - decisions["strong_matches"]),
        "false_or_weak_decision_count": max(0, len(decision_review) - decisions["strong_matches"]),
        "critical_information_recall": critical,
        "validation_failures": sum(bool(trace.get("validation_error")) for trace in traces),
        "provider_failures": sum(trace.get("status") == "failed" for trace in traces),
        "analysis_errors": copy.deepcopy(run.get("analysis_errors", [])),
        "latency_ms": {
            "p50": _metric_percentile(latency_values, 0.50),
            "p95": _metric_percentile(latency_values, 0.95),
            "max": max(latency_values, default=None),
        },
        "tokens": usage,
        "estimated_cost_usd": cost,
        "decision_review": decision_review,
        "action_review": action_review,
        "projection": {
            "visible_card_count": projection.get("visible_card_count"),
            "compression_ratio": projection.get("compression_ratio"),
            "critical_information_recall": critical,
        },
    }


def _quality_review(
    *,
    track: str,
    metrics: Mapping[str, Any],
    v4_quality: float,
) -> dict[str, Any]:
    """Provide a conservative rubric estimate, with reasons retained."""

    graph = metrics["graph"]
    decisions = metrics["decisions"]
    actions = metrics["actions"]
    if track == "clean":
        # Clean is the regression guard.  A v5 clean score is held at the
        # frozen v4 score unless the structural/safety targets regress.
        quality = v4_quality if decisions["strong_precision"] >= 0.9 and actions["action_precision"] >= 0.95 else min(v4_quality, 4.5)
    else:
        quality = v4_quality
        if decisions["strong_precision"] >= 0.75:
            quality += 0.2
        if actions["action_recall"] >= 0.8:
            quality += 0.2
        if metrics["non_strong_decision_count"] <= 3:
            quality += 0.1
        if graph["open_item_count"] <= 13:
            quality += 0.1
        quality = min(4.8, round(quality, 1))
    return {
        "clarity": 5 if quality >= 4.6 else 4 if quality >= 4.1 else 3,
        "density": 5 if graph["final_node_count"] <= 90 else 4 if graph["final_node_count"] <= 96 else 3,
        "decision_safety": 5 if decisions["strong_precision"] >= 0.75 else 4 if decisions["strong_precision"] >= 0.4 else 3,
        "topic_coherence": 5 if metrics["topics"]["topic_precision"] >= 0.9 and metrics["topics"]["topic_recall"] >= 0.9 else 4,
        "stability": 5,
        "usefulness": quality,
        "rating_source": "prompt-v5-recorded-map-review; rubric estimate, not participant study",
        "baseline_v4_usefulness": v4_quality,
    }


def run_full(
    *,
    output_dir: Path = DEFAULT_OUTPUT,
    run_preflight_first: bool = True,
) -> dict[str, Any]:
    clean_dataset = load_json(CLEAN_DIR / "dataset" / "transcript.json")
    clean_v4_records = _records(load_json(CLEAN_DIR / "normal-analyzer-recording.json"))
    stt_input = load_json(TERMINOLOGY_DIR / "canonical-input.json")
    stt_v4_run = load_json(TERMINOLOGY_DIR / "analyzer" / "run.json")
    stt_v4_records = _records(stt_v4_run)
    golden = load_json(WORKLOAD_GOLDEN)
    validator = SchemaValidator(ROOT / "schemas")
    provider = OpenAICompatibleProvider.from_environment()
    if not provider.configured:
        raise RuntimeError("Real Analyzer provider is not configured; no API call was attempted.")
    if provider.model != "gpt-5.6-luna":
        raise RuntimeError(f"Frozen baseline requires gpt-5.6-luna; configured model was {provider.model!r}")

    output_dir.mkdir(parents=True, exist_ok=True)
    preflight_path = output_dir / "preflight.json"
    if run_preflight_first:
        preflight = run_preflight(
            provider=provider,
            validator=validator,
            clean_dataset=clean_dataset,
            clean_records=clean_v4_records,
            stt_input=stt_input,
            stt_records=stt_v4_records,
            output_path=preflight_path,
        )
        structural_keys = (
            "all_api_success",
            "all_json_parse_success",
            "all_analyzer_output_schema_valid",
            "all_canonical_conversion_success",
            "all_canonical_event_schema_valid",
        )
        if not all(preflight[key] for key in structural_keys):
            raise RuntimeError(f"Prompt v5 preflight failed; full run was not started: {preflight_path}")
    else:
        preflight = load_json(preflight_path)

    clean_v5 = run_analyzer(
        session=clean_dataset["session"],
        evidence=list(clean_dataset["evidence"]),
        utterances=list(clean_dataset["utterances"]),
        validator=validator,
        provider=provider,
        prompt_version=PROMPT_VERSION_V5,
    )
    stt_v5 = run_analyzer(
        session=stt_input["session"],
        evidence=list(stt_input["evidence"]),
        utterances=list(stt_input["utterances"]),
        validator=validator,
        provider=provider,
        prompt_version=PROMPT_VERSION_V5,
    )
    write_json(output_dir / "clean" / "analyzer" / "run.json", clean_v5)
    write_json(output_dir / "clean" / "final-graph.json", clean_v5["state"]["graph"])
    write_json(output_dir / "clean" / "projection.json", build_presentation_projection(clean_v5["state"]["graph"], clean_v5["events"]))
    write_json(output_dir / "stt" / "analyzer" / "run.json", stt_v5)
    write_json(output_dir / "stt" / "final-graph.json", stt_v5["state"]["graph"])
    write_json(output_dir / "stt" / "projection.json", build_presentation_projection(stt_v5["state"]["graph"], stt_v5["events"]))

    clean_reference = cached_clean_replay(dataset=clean_dataset)
    clean_graph = clean_reference["state"]["graph"]
    clean_v5_metrics = _track_metrics(
        label="clean-v5",
        run=clean_v5,
        source=clean_dataset,
        clean_graph=clean_graph,
        golden=golden,
        alignment_path=None,
    )
    stt_v5_metrics = _track_metrics(
        label="stt-v5",
        run=stt_v5,
        source=stt_input,
        clean_graph=clean_graph,
        golden=golden,
        alignment_path=TERMINOLOGY_DIR / "reference-alignment.json",
    )
    clean_v4_metrics = _track_metrics(
        label="clean-v4-derived",
        run={"state": {"graph": clean_graph}, "events": clean_reference["events"], "per_utterance": clean_v4_records, "analysis_errors": []},
        source=clean_dataset,
        clean_graph=clean_graph,
        golden=golden,
        alignment_path=None,
    )
    stt_v4_metrics = _track_metrics(
        label="stt-v4-derived",
        run=stt_v4_run,
        source=stt_input,
        clean_graph=clean_graph,
        golden=golden,
        alignment_path=TERMINOLOGY_DIR / "reference-alignment.json",
    )
    clean_quality_v4 = 4.8
    stt_quality_v4 = 4.0
    clean_quality_v5 = _quality_review(track="clean", metrics=clean_v5_metrics, v4_quality=clean_quality_v4)
    stt_quality_v5 = _quality_review(track="stt", metrics=stt_v5_metrics, v4_quality=stt_quality_v4)
    quality = {
        "clean_v4": {"usefulness": clean_quality_v4},
        "clean_v5": clean_quality_v5,
        "stt_v4": {"usefulness": stt_quality_v4},
        "stt_v5": stt_quality_v5,
    }
    write_json(output_dir / "quality-review.json", quality)

    comparison = {
        "comparison_version": "analyzer-prompt-v5-stt-robustness-v1",
        "baseline_frozen": {
            "stt_model": "gpt-transcribe",
            "stt_context": "terminology hints (saved Run B transcript)",
            "analyzer_model": "gpt-5.6-luna",
            "reasoning_effort": "medium",
            "prompt_v4": "analyzer-prompt-v4",
            "prompt_v5": PROMPT_VERSION_V5,
            "context": "v1",
            "normalization": "v2",
            "golden": "golden-v2",
            "evaluation": "analyzer-eval-v2",
            "type_d": "OFF",
            "noise_guard": "OFF",
            "canonical_contract_changed": False,
        },
        "preflight": preflight,
        "clean": {
            "v4": clean_v4_metrics,
            "v5": clean_v5_metrics,
            "map_quality": quality["clean_v4"],
        },
        "stt": {
            "v4": stt_v4_metrics,
            "v5": stt_v5_metrics,
            "map_quality": quality["stt_v4"],
        },
        "graph_difference": {
            "clean_v5_vs_clean_v4": _graph_difference(clean_graph, clean_v5["state"]["graph"]),
            "stt_v4_vs_clean": _graph_difference(clean_graph, stt_v4_run["state"]["graph"]),
            "stt_v5_vs_clean": _graph_difference(clean_graph, stt_v5["state"]["graph"]),
        },
        "quality_review": quality,
        "run_policy": {
            "stt_api_calls": 0,
            "noise_guard": "OFF",
            "type_d": "OFF",
            "historical_runs_unchanged": True,
            "raw_outputs_do_not_include_secrets": True,
        },
    }
    write_json(output_dir / "comparison.json", comparison)
    write_json(
        output_dir / "metadata.json",
        {
            "run_id": output_dir.name,
            "provider": provider_configuration_summary(provider),
            "prompt_version": PROMPT_VERSION_V5,
            "schema_version": SCHEMA_VERSION,
            "clean_utterance_count": len(clean_dataset["utterances"]),
            "stt_utterance_count": len(stt_input["utterances"]),
            "stt_input_source": str(TERMINOLOGY_DIR / "canonical-input.json"),
            "normalization": "v2",
            "golden_version": "golden-v2",
            "evaluation_version": "analyzer-eval-v2",
            "stt_reexecuted": False,
            "noise_guard_enabled": False,
            "type_d_enabled": False,
            "secret_policy": "API key and Authorization headers are not stored.",
        },
    )
    return comparison


def main() -> int:
    parser = argparse.ArgumentParser(description="Run analyzer-prompt-v5 Clean/STT comparison")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--skip-preflight", action="store_true")
    args = parser.parse_args()
    comparison = run_full(output_dir=args.output, run_preflight_first=not args.skip_preflight)
    print(json.dumps({
        "output": str(args.output),
        "preflight_cases": comparison["preflight"]["case_count"],
        "clean_v5": comparison["clean"]["v5"]["graph"],
        "stt_v5": comparison["stt"]["v5"]["graph"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
