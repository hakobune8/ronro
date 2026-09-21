"""Recorded STT Spike runner.

This module composes the real STT adapter with the existing, frozen Analyzer /
Event Store / Materializer / Presentation Projection pipeline.  It is an
evaluation runner, not a streaming implementation: only final transcription
segments are passed to the Analyzer and every run writes derived artifacts.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import statistics
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

from .analyzer import TranscriptReplaySession
from .layout import StableLayout
from .projection import build_presentation_projection
from .real_analyzer import PROMPT_VERSION_V4, OpenAICompatibleProvider, RealAnalyzer, provider_configuration_summary
from .replay import ReplayRunner
from .schema import SchemaValidator
from .stt import (
    OpenAICompatibleTranscriber,
    STTFailure,
    STTResult,
    canonical_transcript_documents,
    character_error_rate,
    normalize_segments,
    whitespace_word_error_rate,
    stt_result_from_dict,
    audio_duration_seconds,
    transcribe_recorded_audio,
)


ROOT = Path(__file__).resolve().parents[1]
CLEAN_DATASET = ROOT / "evaluation" / "30min" / "run-gpt-5.6-luna-analyzer-prompt-v4-20260919" / "dataset" / "transcript.json"
CLEAN_RECORDING = ROOT / "evaluation" / "30min" / "run-gpt-5.6-luna-analyzer-prompt-v4-20260919" / "normal-analyzer-recording.json"
DEFAULT_OUTPUT = ROOT / "evaluation" / "stt" / "runs" / "recorded-stt-spike-v1"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_clean_dataset(path: Path = CLEAN_DATASET) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def make_session(dataset: Mapping[str, Any], session_id: str) -> dict[str, Any]:
    session = copy.deepcopy(dict(dataset["session"]))
    session["id"] = session_id
    return session


def run_analyzer(
    *,
    session: Mapping[str, Any],
    evidence: list[dict[str, Any]],
    utterances: list[dict[str, Any]],
    validator: SchemaValidator,
    provider: OpenAICompatibleProvider,
    prompt_version: str = PROMPT_VERSION_V4,
) -> dict[str, Any]:
    runner = ReplayRunner(validator)
    analyzer = RealAnalyzer(
        provider=provider,
        schema_validator=validator,
        meeting_goal=session.get("goal"),
        prompt_version=prompt_version,
        output_schema_version="v2",
    )
    replay = TranscriptReplaySession.from_documents(
        session=session,
        evidence=evidence,
        utterances=utterances,
        replay_runner=runner,
        analyzer=analyzer,
        replay_mode="recorded-stt-real",
    )
    per_utterance: list[dict[str, Any]] = []
    for utterance in replay.utterances:
        before = len(replay.result.events)
        replay.step()
        per_utterance.append({
            "utterance_id": utterance["id"],
            "sequence": utterance["sequence"],
            "text": utterance["text"],
            "events": copy.deepcopy(list(replay.result.events)[before:]),
            "trace": copy.deepcopy(analyzer.last_trace or {}),
        })
    return {
        "provider": provider_configuration_summary(provider),
        "prompt_version": prompt_version,
        "schema_version": "v2",
        "per_utterance": per_utterance,
        "events": copy.deepcopy(list(replay.result.events)),
        "state": copy.deepcopy(replay.result.state),
        "analysis_errors": copy.deepcopy(replay.analysis_errors),
        "run_history": copy.deepcopy(analyzer.run_history),
    }


def cached_clean_replay(
    *,
    dataset: Mapping[str, Any],
    recording_path: Path = CLEAN_RECORDING,
    utterance_limit: int | None = None,
) -> dict[str, Any]:
    """Replay the frozen Clean Transcript analyzer recording without new LLM calls."""

    recording = json.loads(recording_path.read_text(encoding="utf-8"))
    utterances = list(dataset["utterances"][:utterance_limit] if utterance_limit else dataset["utterances"])
    evidence_ids = {evidence_id for utterance in utterances for evidence_id in utterance.get("evidence_ids", [])}
    records = [
        record for record in recording
        if any(evidence_id in evidence_ids for event in record.get("events", []) for evidence_id in event.get("source_evidence_ids", []))
    ]
    selected_evidence = [evidence for evidence in dataset["evidence"] if evidence.get("id") in evidence_ids]
    events: list[dict[str, Any]] = TranscriptReplaySession._default_system_events(dataset["session"])
    events.extend(copy.deepcopy(event) for record in records for event in record.get("events", []))
    runner = ReplayRunner(SchemaValidator(ROOT / "schemas"))
    result = runner.replay_events(
        session_id=dataset["session"]["id"],
        evidence=selected_evidence,
        utterances=utterances,
        events=events,
    )
    return {
        "provider": {"provider": "openai-compatible-cache", "model": "gpt-5.6-luna", "configured": True},
        "prompt_version": PROMPT_VERSION_V4,
        "events": list(result.events),
        "state": result.state,
        "recording": records,
    }


def _normalized_label(value: str) -> str:
    return re.sub(r"[\s　。、・:：「」『』（）()\-—!?！？]", "", str(value)).lower()


def _same_meaning(left: str, right: str) -> bool:
    a, b = _normalized_label(left), _normalized_label(right)
    return bool(a and b and (a in b or b in a))


def graph_summary(graph: Mapping[str, Any]) -> dict[str, Any]:
    nodes = [node for node in graph.get("nodes", []) if node.get("status") != "archived"]
    active = [node for node in nodes if node.get("status") not in {"parked", "resolved"}]
    by_type = {node_type: [node for node in nodes if node.get("type") == node_type] for node_type in ("topic", "decision", "action", "open_item")}
    current_id = graph.get("current_topic", {}).get("primary_topic_id")
    current = next((node for node in nodes if node.get("id") == current_id), None)
    return {
        "topic_count": len(by_type["topic"]),
        "final_node_count": len(nodes),
        "active_node_count": len(active),
        "nodes_per_topic": round(len(nodes) / max(1, len(by_type["topic"])), 4),
        "decision_count": len(by_type["decision"]),
        "candidate_decision_count": sum(node.get("status") == "candidate" for node in by_type["decision"]),
        "confirmed_decision_count": sum(node.get("status") == "confirmed" for node in by_type["decision"]),
        "action_count": len(by_type["action"]),
        "open_item_count": len(by_type["open_item"]),
        "open_item_active_count": sum(node.get("status") not in {"resolved", "archived"} for node in by_type["open_item"]),
        "parking_count": sum(node.get("status") == "parked" for node in nodes),
        "relation_count": len(graph.get("edges", [])),
        "current_topic": current.get("label") if current else None,
    }


def _labels(graph: Mapping[str, Any], node_type: str | None = None) -> list[str]:
    return [
        str(node.get("label", ""))
        for node in graph.get("nodes", [])
        if node.get("status") != "archived" and (node_type is None or node.get("type") == node_type)
    ]


def graph_difference(clean_graph: Mapping[str, Any], stt_graph: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for node_type, label in (("topic", "Topic"), ("decision", "Decision"), ("action", "Action"), ("open_item", "Open Item")):
        clean = _labels(clean_graph, node_type)
        stt = _labels(stt_graph, node_type)
        used: set[int] = set()
        missing: list[str] = []
        for candidate in clean:
            match = next((index for index, actual in enumerate(stt) if index not in used and _same_meaning(candidate, actual)), None)
            if match is None:
                missing.append(candidate)
            else:
                used.add(match)
        extra = [actual for index, actual in enumerate(stt) if index not in used]
        result[f"missing_{label.lower().replace(' ', '_')}"] = missing
        result[f"extra_{label.lower().replace(' ', '_')}"] = extra
    clean_current = str(clean_graph.get("current_topic", {}).get("primary_topic_id") or "")
    stt_current = str(stt_graph.get("current_topic", {}).get("primary_topic_id") or "")
    clean_current_label = next((str(node.get("label")) for node in clean_graph.get("nodes", []) if node.get("id") == clean_current), None)
    stt_current_label = next((str(node.get("label")) for node in stt_graph.get("nodes", []) if node.get("id") == stt_current), None)
    result["wrong_current_topic"] = bool(clean_current_label and stt_current_label and not _same_meaning(clean_current_label, stt_current_label))
    return result


def critical_information_recall(clean_graph: Mapping[str, Any], stt_graph: Mapping[str, Any]) -> dict[str, Any]:
    required = []
    for node_type in ("decision", "action", "open_item"):
        required.extend((node_type, label) for label in _labels(clean_graph, node_type))
    current_id = clean_graph.get("current_topic", {}).get("primary_topic_id")
    current_label = next((str(node.get("label")) for node in clean_graph.get("nodes", []) if node.get("id") == current_id), None)
    if current_label:
        required.append(("current_topic", current_label))
    found = 0
    missing: list[dict[str, str]] = []
    for node_type, label in required:
        target_type = None if node_type == "current_topic" else node_type
        if any(_same_meaning(label, str(node.get("label", ""))) for node in stt_graph.get("nodes", []) if node.get("status") != "archived" and (target_type is None or node.get("type") == target_type)):
            found += 1
        else:
            missing.append({"type": node_type, "label": label})
    return {"matched": found, "total": len(required), "recall": round(found / max(1, len(required)), 4), "missing": missing}


def analyzer_metrics(run: Mapping[str, Any], utterance_count: int) -> dict[str, Any]:
    traces = [item.get("trace", {}) for item in run.get("per_utterance", [])]
    node_counts = [sum(event.get("event_type") == "node_detected" for event in item.get("events", [])) for item in run.get("per_utterance", [])]
    latencies = [float(trace["latency_ms"]) for trace in traces if isinstance(trace.get("latency_ms"), (int, float))]
    def percentile(values: list[float], fraction: float) -> float | None:
        if not values:
            return None
        values = sorted(values)
        index = min(len(values) - 1, max(0, int(round((len(values) - 1) * fraction))))
        return round(values[index], 3)
    return {
        "utterance_count": utterance_count,
        "event_count": len(run.get("events", [])) - 2 if len(run.get("events", [])) >= 2 else len(run.get("events", [])),
        "accepted_node_count": sum(node_counts),
        "accepted_nodes_per_utterance": round(sum(node_counts) / max(1, utterance_count), 4),
        "max_nodes_per_utterance": max(node_counts, default=0),
        "three_plus_node_utterance_rate": round(sum(count >= 3 for count in node_counts) / max(1, utterance_count), 4),
        "validation_failures": sum(bool(trace.get("validation_error")) for trace in traces),
        "provider_failures": sum(trace.get("status") == "failed" for trace in traces),
        "no_op_count": sum(trace.get("status") == "noop" for trace in traces),
        "latency_ms": {"p50": percentile(latencies, 0.50), "p95": percentile(latencies, 0.95), "max": max(latencies, default=None)},
        "tokens": {
            key: sum((trace.get("usage", {}).get(key) or 0) for trace in traces)
            for key in ("prompt_tokens", "completion_tokens", "reasoning_tokens", "total_tokens")
        },
        "estimated_cost_usd": round(sum((trace.get("cost_usd") or 0.0) for trace in traces), 8),
    }


def align_reference_texts(dataset: Mapping[str, Any], normalized: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    reference = list(dataset["utterances"])
    normalized_items = list(normalized)
    aligned: list[dict[str, Any]] = []
    # The synthetic recording uses fixed 15-second reference slots, but STT
    # providers are free to place speech boundaries inside a slot and may
    # split/merge one slot.  For evaluation labels, preserve the monotonic
    # transcript order rather than treating provider timestamps as semantic
    # utterance boundaries.  Absolute timestamps remain in the trace sidecar.
    for item_index, item in enumerate(normalized_items):
        if len(normalized_items) == 1:
            index = 0
        else:
            index = round(item_index * (len(reference) - 1) / (len(normalized_items) - 1))
        index = min(len(reference) - 1, max(0, index))
        aligned.append({
            "stt_utterance_id": item.get("id"),
            "reference_utterance_id": reference[index]["id"],
            "reference_text": reference[index]["text"],
            "stt_text": item.get("text", ""),
            "reference_sequence": reference[index]["sequence"],
            "audio_start": item.get("audio_start"),
            "audio_end": item.get("audio_end"),
        })
    return aligned


def semantic_stt_errors(aligned: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    keyword_groups = {
        "topic_keyword_error": (("Discussion Map", "ディスカッションマップ", "Map"), ("MVP", "スマホ", "Visual", "料金", "価格", "Architecture", "Transcript", "Privacy", "オンライン", "レイアウト")),
        "negation_error": (("外さない", "含めない", "しない", "なくて", "対象外", "なし"), ("入れ", "含め", "する", "あり")),
        "decision_phrase_error": (("外しましょう", "進めましょう", "採用しましょう", "決めましょう", "にしましょう", "外す案"), ("外す", "進める", "採用", "決める")),
        "action_phrase_error": (("作ります", "確認します", "整理します", "調べます", "お願いします", "対応します"), ("作る", "確認", "整理", "調べ")),
        "reference_error": (("それ", "これ", "その案", "この方向", "さっき", "今回はなし"), ()),
    }
    errors: dict[str, list[dict[str, Any]]] = {key: [] for key in keyword_groups}
    for item in aligned:
        reference = str(item["reference_text"])
        hypothesis = str(item["stt_text"])
        for category, (needles, _) in keyword_groups.items():
            if any(needle in reference for needle in needles) and not any(needle in hypothesis for needle in needles):
                errors[category].append(dict(item))
        if any(needle in reference for needle in ("外さない", "含めない", "しない", "対象外", "なし")):
            if any(positive in hypothesis for positive in ("入れましょう", "含めましょう", "します", "あり")):
                errors.setdefault("critical_negation_inversion", []).append(dict(item))
    counts = {key: len(value) for key, value in errors.items()}
    return {"counts": counts, "cases": errors}


def build_run_artifacts(
    *,
    audio_path: Path,
    output_dir: Path,
    model: str | None = None,
    run_analyzer_calls: bool = True,
    reference_limit: int | None = None,
    saved_stt_result: Path | None = None,
) -> dict[str, Any]:
    dataset = load_clean_dataset()
    output_dir.mkdir(parents=True, exist_ok=True)
    if saved_stt_result:
        stt_result = stt_result_from_dict(json.loads(saved_stt_result.read_text(encoding="utf-8")))
    else:
        transcriber = OpenAICompatibleTranscriber.from_environment()
        if model:
            transcriber = OpenAICompatibleTranscriber(
                endpoint=transcriber.endpoint,
                api_key=transcriber.api_key,
                model=model,
                timeout_seconds=transcriber.timeout_seconds,
            )
        stt_result = transcribe_recorded_audio(
            transcriber,
            audio_path,
            chunk_seconds=600.0,
            chunk_dir=output_dir / "raw" / "chunks",
        )
    raw = stt_result.to_dict(include_raw_response=True)
    write_json(output_dir / "raw" / "stt-result.json", raw)
    normalized, normalization_diagnostics = normalize_segments(stt_result.segments, id_prefix="stt-utt")
    if reference_limit:
        normalized = normalized[:reference_limit]
    session_id = f"recorded-stt-{audio_path.stem}"
    evidence, utterances, trace = canonical_transcript_documents(
        normalized,
        session_id=session_id,
        session_started_at=dataset["session"]["started_at"],
    )
    write_json(output_dir / "normalized-utterances.json", [item.to_dict() for item in normalized])
    write_json(output_dir / "normalization-diagnostics.json", normalization_diagnostics)
    write_json(output_dir / "canonical-input.json", {"session": make_session(dataset, session_id), "evidence": evidence, "utterances": utterances})
    write_json(output_dir / "evidence-audio-trace.json", trace)
    aligned = align_reference_texts(dataset, [item.to_dict() for item in normalized])
    reference_text = "".join(item["reference_text"] for item in aligned)
    stt_text = "".join(item["stt_text"] for item in aligned)
    whitespace_wer = whitespace_word_error_rate(reference_text, stt_text)
    lexical = {
        "character_error_rate": character_error_rate(reference_text, stt_text),
        "word_error_rate": None,
        "whitespace_word_error_rate_diagnostic": whitespace_wer,
        "word_error_rate_note": "Japanese text has no whitespace tokenization in this dataset; CER is primary and WER is not reported.",
    }
    write_json(output_dir / "reference-alignment.json", aligned)
    write_json(output_dir / "stt-error-analysis.json", {"lexical": lexical, "semantic": semantic_stt_errors(aligned)})
    result: dict[str, Any] = {
        "stt": stt_result.to_dict(include_raw_response=False),
        "audio_duration_seconds": round(audio_duration_seconds(audio_path), 3),
        "normalization": {"segment_count": len(stt_result.segments), "utterance_count": len(normalized), "diagnostics": normalization_diagnostics},
        "lexical": lexical,
        "semantic_errors": semantic_stt_errors(aligned),
    }
    if run_analyzer_calls:
        validator = SchemaValidator(ROOT / "schemas")
        provider = OpenAICompatibleProvider.from_environment()
        if not provider.configured:
            raise STTFailure("analyzer_not_configured", "Real Analyzer provider is not configured")
        session = make_session(dataset, session_id)
        analyzer_run = run_analyzer(session=session, evidence=evidence, utterances=utterances, validator=validator, provider=provider)
        write_json(output_dir / "analyzer" / "run.json", analyzer_run)
        projection = build_presentation_projection(analyzer_run["state"]["graph"], analyzer_run["events"], layout=StableLayout())
        write_json(output_dir / "projection.json", projection)
        result["analyzer"] = {
            "metrics": analyzer_metrics(analyzer_run, len(utterances)),
            "provider": analyzer_run["provider"],
            "analysis_errors": analyzer_run["analysis_errors"],
            "graph_summary": graph_summary(analyzer_run["state"]["graph"]),
            "projection": {"visible_node_count": len(projection.get("visible_node_ids", [])), "lane_count": len(projection.get("lanes", []))},
        }
    write_json(output_dir / "run-summary.json", result)
    return result


def run_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Recorded STT Spike")
    parser.add_argument("audio", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model")
    parser.add_argument("--skip-analyzer", action="store_true")
    parser.add_argument("--saved-stt-result", type=Path, help="Reuse a saved raw/stt-result.json without another STT call")
    args = parser.parse_args(argv)
    result = build_run_artifacts(
        audio_path=args.audio,
        output_dir=args.output,
        model=args.model,
        run_analyzer_calls=not args.skip_analyzer,
        saved_stt_result=args.saved_stt_result,
    )
    print(json.dumps({
        "output": str(args.output),
        "provider": result["stt"]["provider"],
        "model": result["stt"]["model"],
        "segment_count": result["normalization"]["segment_count"],
        "utterance_count": result["normalization"]["utterance_count"],
        "cer": result["lexical"]["character_error_rate"],
        "wer": result["lexical"]["word_error_rate"],
        "audio_duration_seconds": result.get("audio_duration_seconds"),
        "analyzer": result.get("analyzer", {}).get("metrics"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
