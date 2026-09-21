"""Offline comparison for the terminology-aware STT run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .projection import build_presentation_projection
from .recorded_stt import cached_clean_replay, graph_summary
from .recorded_stt_compare import (
    _action_metrics,
    _decision_metrics,
    _focus_events,
    _graph_difference,
    _no_op_accuracy,
    _topic_metrics,
    load_json,
    write_json,
)
from .stt_terminology_run import (
    BASELINE_RUN,
    CLEAN_DATASET,
    ROOT,
    technical_term_accuracy,
)


def _branch_metrics(
    *,
    clean_graph: Mapping[str, Any],
    analyzer_run: Mapping[str, Any],
    records: list[Mapping[str, Any]],
    alignment: list[Mapping[str, Any]],
    golden: Mapping[str, Any],
    normalized_count: int,
) -> dict[str, Any]:
    graph = analyzer_run["state"]["graph"]
    sequence_map = {index + 1: int(item["reference_sequence"]) for index, item in enumerate(alignment)}
    node_counts = [sum(event.get("event_type") == "node_detected" for event in item.get("events", [])) for item in records]
    return {
        "graph": graph_summary(graph),
        "topics": _topic_metrics(clean_graph, graph),
        "decisions": _decision_metrics(graph),
        "actions": _action_metrics(graph),
        "no_op": _no_op_accuracy(records, golden.get("no_op_sequences", []), sequence_map),
        "node_economy": {
            "nodes_per_utterance": round(sum(node_counts) / max(1, normalized_count), 4),
            "max_nodes_per_utterance": max(node_counts, default=0),
            "three_plus_node_utterance_rate": round(sum(count >= 3 for count in node_counts) / max(1, len(node_counts)), 4),
        },
        "focus_events": _focus_events(analyzer_run.get("events", [])),
        "validation_failures": sum(bool(item.get("trace", {}).get("validation_error")) for item in records),
        "provider_failures": sum(item.get("trace", {}).get("status") == "failed" for item in records),
        "latency_ms": analyzer_run.get("run_history", []) and {
            "p50": analyzer_run.get("run_history", [])[len(analyzer_run.get("run_history", [])) // 2].get("latency_ms")
        } or None,
    }


def _term_side(path: Path, dataset: Mapping[str, Any]) -> dict[str, Any]:
    alignment = load_json(path / "reference-alignment.json")
    return technical_term_accuracy(dataset, alignment)


def _clean_term_side(dataset: Mapping[str, Any]) -> dict[str, Any]:
    alignment = [
        {
            "reference_sequence": item["sequence"],
            "reference_text": item["text"],
            "stt_text": item["text"],
        }
        for item in dataset.get("utterances", [])
    ]
    return technical_term_accuracy(dataset, alignment)


def main() -> int:
    dataset = load_json(CLEAN_DATASET)
    golden = load_json(ROOT / "evaluation" / "30min" / "run-gpt-5.6-luna-analyzer-prompt-v4-20260919" / "dataset" / "golden.json")
    clean = cached_clean_replay(dataset=dataset)
    clean_graph = clean["state"]["graph"]
    baseline_analyzer = load_json(BASELINE_RUN / "analyzer" / "run.json")
    baseline_input = load_json(BASELINE_RUN / "canonical-input.json")
    baseline_alignment = load_json(BASELINE_RUN / "reference-alignment.json")
    terminology_dir = ROOT / "evaluation" / "stt" / "terminology-run" / "full"
    terminology_analyzer = load_json(terminology_dir / "analyzer" / "run.json")
    terminology_input = load_json(terminology_dir / "canonical-input.json")
    terminology_alignment = load_json(terminology_dir / "reference-alignment.json")

    clean_records = load_json(ROOT / "evaluation" / "30min" / "run-gpt-5.6-luna-analyzer-prompt-v4-20260919" / "normal-analyzer-recording.json")
    baseline_summary = load_json(BASELINE_RUN / "run-summary.json")
    terminology_summary = load_json(terminology_dir / "run-summary.json")
    clean_metrics = _branch_metrics(
        clean_graph=clean_graph,
        analyzer_run={"state": clean["state"], "events": clean["events"]},
        records=clean_records,
        alignment=[{"reference_sequence": i + 1} for i in range(len(clean_records))],
        golden=golden,
        normalized_count=len(dataset["utterances"]),
    )
    baseline_metrics = _branch_metrics(
        clean_graph=clean_graph,
        analyzer_run=baseline_analyzer,
        records=list(baseline_analyzer["per_utterance"]),
        alignment=baseline_alignment,
        golden=golden,
        normalized_count=119,
    )
    terminology_metrics = _branch_metrics(
        clean_graph=clean_graph,
        analyzer_run=terminology_analyzer,
        records=list(terminology_analyzer["per_utterance"]),
        alignment=terminology_alignment,
        golden=golden,
        normalized_count=120,
    )

    clean_projection = build_presentation_projection(clean_graph, clean["events"])
    baseline_projection = load_json(BASELINE_RUN / "final-projections" / "stt.json")
    terminology_projection = load_json(terminology_dir / "final-projections" / "terminology.json")
    write_json(terminology_dir / "final-projections" / "clean.json", clean_projection)
    write_json(terminology_dir / "final-projections" / "baseline-a.json", baseline_projection)
    write_json(terminology_dir / "final-graphs" / "clean.json", clean_graph)
    write_json(terminology_dir / "final-graphs" / "baseline-a.json", baseline_analyzer["state"]["graph"])

    comparison = {
        "comparison_version": "stt-terminology-comparison-v1",
        "baseline_frozen": {
            "analyzer_model": "gpt-5.6-luna",
            "analyzer_reasoning": "medium",
            "prompt": "analyzer-prompt-v4",
            "context": "v1",
            "normalization": "v2",
            "golden": "golden-v2",
            "evaluation": "analyzer-eval-v2",
            "type_d": "OFF",
            "noise_guard": "OFF",
        },
        "clean": {
            "map_quality": 4.8,
            "graph": graph_summary(clean_graph),
            "projection": {
                "visible_card_count": clean_projection.get("visible_card_count"),
                "compression_ratio": clean_projection.get("compression_ratio"),
            },
            "technical_terms": _clean_term_side(dataset),
        },
        "run_a_baseline_diarized": {
            "stt_model": baseline_summary["stt"]["model"],
            "raw_segment_count": baseline_summary["normalization"]["segment_count"],
            "normalized_utterance_count_v2": 119,
            "cer": baseline_summary["lexical"]["character_error_rate"],
            "technical_terms": _term_side(BASELINE_RUN, dataset),
            "semantic_errors": baseline_summary.get("semantic_errors"),
            "analyzer": baseline_metrics,
            "graph_difference_vs_clean": _graph_difference(clean_graph, baseline_analyzer["state"]["graph"]),
            "map_quality": 3.8,
            "projection": {
                "visible_card_count": baseline_projection.get("visible_card_count"),
                "compression_ratio": baseline_projection.get("compression_ratio"),
                "critical_information_recall": baseline_projection.get("critical_information_recall"),
            },
            "speaker_attribution": {"available": True, "source": "gpt-4o-transcribe-diarize"},
        },
        "run_b_terminology_aware": {
            "stt_model": terminology_summary["stt"]["model"],
            "raw_segment_count": terminology_summary["normalization"]["raw_segment_count"],
            "normalized_utterance_count_v2": terminology_summary["normalization"]["utterance_count"],
            "cer": terminology_summary["lexical"]["character_error_rate"],
            "technical_terms": terminology_summary["technical_terms"],
            "semantic_errors": terminology_summary.get("semantic_errors"),
            "analyzer": terminology_metrics,
            "graph_difference_vs_clean": _graph_difference(clean_graph, terminology_analyzer["state"]["graph"]),
            "map_quality": 4.0,
            "map_quality_rationale": [
                "Six Topic lanes and Current Topic survived, so the map remains structurally usable.",
                "Terminology improved relative to A, but phonetic residuals (スマホV, MAT, ERとASCRIT, スタキック) reduce label faithfulness.",
                "Eight candidate decisions and seven actions increase the visible/rail density over A.",
            ],
            "projection": {
                "visible_card_count": terminology_projection.get("visible_card_count"),
                "compression_ratio": terminology_projection.get("compression_ratio"),
                "critical_information_recall": terminology_projection.get("critical_information_recall"),
            },
            "speaker_attribution": {"available": False, "source": "gpt-transcribe JSON response; speaker=null"},
        },
        "critical_information_recall": {
            "run_a_projection": baseline_projection.get("critical_information_recall", {}).get("overall"),
            "run_b_projection": terminology_projection.get("critical_information_recall", {}).get("overall"),
            "interpretation": "Projection recall is 1.0 for both because every generated critical category remains visible. Cross-run semantic content still needs human label adjudication; this metric is not a substitute for label quality.",
        },
        "latency_and_cost": {
            "run_a_stt_processing_ms": baseline_summary["stt"]["processing_ms"],
            "run_a_stt_rtf": round((baseline_summary["stt"]["processing_ms"] / 1000) / baseline_summary["audio_duration_seconds"], 4),
            "run_b_stt_processing_ms": terminology_summary["processing_ms"],
            "run_b_stt_wall_ms": terminology_summary["wall_processing_ms"],
            "run_b_stt_rtf": terminology_summary["real_time_factor"],
            "run_a_analyzer": baseline_metrics.get("latency_ms"),
            "run_b_analyzer": terminology_summary.get("analyzer", {}).get("metrics", {}).get("latency_ms"),
            "run_b_stt_estimated_cost_usd": round(30.0 * 0.0045, 4),
            "run_b_stt_cost_note": "Estimated from the official gpt-transcribe list price of $0.0045/min; API usage did not expose billable audio units in this adapter response.",
        },
        "canonical_contract_changed": False,
        "noise_guard_enabled": False,
    }
    write_json(terminology_dir / "comparison.json", comparison)
    print(json.dumps({
        "comparison": str(terminology_dir / "comparison.json"),
        "run_a": {"cer": comparison["run_a_baseline_diarized"]["cer"], "map_quality": 3.8},
        "run_b": {"cer": comparison["run_b_terminology_aware"]["cer"], "map_quality": 4.0},
        "run_b_terms": {k: v["accuracy"] for k, v in comparison["run_b_terminology_aware"]["technical_terms"]["terms"].items() if v["occurrence_count"]},
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
