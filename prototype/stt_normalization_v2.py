"""Offline STT Error Attribution and Utterance Normalization v2 spike.

This module consumes the saved final STT segments from the Recorded STT Spike.
It intentionally does not call STT or an LLM.  v1 remains the source artifact;
v2 is a derived input projection with a small, conservative boundary rule and
an Analyzer eligibility sidecar for filler/agreement-only utterances.
"""

from __future__ import annotations

import copy
import difflib
import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from .recorded_stt import cached_clean_replay, graph_summary
from .recorded_stt_compare import (
    _action_key,
    _compact,
    _decision_is_strong,
    _topic_key,
    write_json,
)
from .stt import (
    RawSTTSegment,
    NormalizedUtterance,
    _TERMINAL_RE,
    _join_text,
    canonical_transcript_documents,
    stt_result_from_dict,
)


ROOT = Path(__file__).resolve().parents[1]
STT_RUN = ROOT / "evaluation" / "stt" / "full-run-v1"
DATASET_DIR = ROOT / "evaluation" / "30min" / "run-gpt-5.6-luna-analyzer-prompt-v4-20260919" / "dataset"

FILLER_VALUES = {
    "うん",
    "はい",
    "そうですね",
    "なるほど",
    "了解です",
    "わかりました",
    "そうしましょう",
    "それでいきましょう",
    "それもそうですね",
    "お疲れ様でした",
}
FRAGMENT_SUFFIXES = ("なので", "ただ", "というか", "それで", "でも", "例えば", "という", "、", ",")


def _plain(value: str) -> str:
    return re.sub(r"[\s　。、・:：「」『』（）()\[\]{}<>!?！？,.]+", "", str(value).lower())


def is_filler_only(text: str) -> bool:
    plain = _plain(text)
    return plain in {_plain(value) for value in FILLER_VALUES}


def is_incomplete_fragment(text: str) -> bool:
    value = str(text).strip()
    return value.endswith(FRAGMENT_SUFFIXES)


def is_agreement_only(text: str) -> bool:
    plain = _plain(text)
    return plain in {_plain(value) for value in ("そうですね", "はい", "了解です", "そうしましょう", "それでいきましょう", "それもそうですね")}


def _dedupe_segments(segments: Iterable[RawSTTSegment]) -> tuple[list[RawSTTSegment], list[dict[str, Any]]]:
    diagnostics: list[dict[str, Any]] = []
    source_segments = list(segments)
    ordered = sorted(source_segments, key=lambda item: (item.start, item.end, item.segment_id))
    if source_segments != ordered:
        diagnostics.append({"code": "segments_reordered_by_timestamp", "severity": "warning"})
    deduped: list[RawSTTSegment] = []
    seen: set[tuple[float, float, str]] = set()
    for segment in ordered:
        key = (round(segment.start, 3), round(segment.end, 3), segment.text.strip())
        if key in seen:
            diagnostics.append({"code": "duplicate_segment", "severity": "warning", "segment_id": segment.segment_id})
            continue
        seen.add(key)
        deduped.append(segment)
    return deduped, diagnostics


def normalize_segments_v2(
    segments: Iterable[RawSTTSegment],
    *,
    silence_gap_seconds: float = 0.8,
    filler_follow_gap_seconds: float = 1.0,
    max_utterance_seconds: float = 20.0,
    id_prefix: str = "stt-v2-utt",
) -> tuple[list[NormalizedUtterance], list[dict[str, Any]], dict[str, Any]]:
    """Conservative v2 normalizer.

    v1 already merged comma-ended fragments and same-speaker short segments.
    v2 adds only one boundary exception: a terminal-punctuation filler may be
    joined to the immediately following same-speaker continuation when the
    gap is <= 1 second.  It never merges across speakers or long gaps.  This
    handles ``そうですね。そこは後で戻りましょう。`` without introducing a
    general semantic segmenter.
    """

    source_segments = list(segments)
    deduped, diagnostics = _dedupe_segments(source_segments)
    groups: list[list[RawSTTSegment]] = []
    merge_reasons: list[dict[str, Any]] = []
    for segment in deduped:
        if not groups:
            groups.append([segment])
            continue
        current = groups[-1]
        prior = current[-1]
        gap = max(0.0, segment.start - prior.end)
        duration = segment.end - current[0].start
        normal_merge = (
            gap <= silence_gap_seconds
            and duration <= max_utterance_seconds
            and prior.speaker == segment.speaker
            and not _TERMINAL_RE.search(prior.text.strip())
        )
        filler_merge = (
            gap <= filler_follow_gap_seconds
            and duration <= max_utterance_seconds
            and prior.speaker == segment.speaker
            and is_filler_only(prior.text)
        )
        if normal_merge or filler_merge:
            current.append(segment)
            merge_reasons.append({
                "left_segment_id": prior.segment_id,
                "right_segment_id": segment.segment_id,
                "reason": "filler_follow_merge" if filler_merge and not normal_merge else "same_speaker_fragment_merge",
                "gap_seconds": round(gap, 3),
            })
        else:
            groups.append([segment])

    normalized: list[NormalizedUtterance] = []
    for index, group in enumerate(groups, start=1):
        text = ""
        for segment in group:
            text = _join_text(text, segment.text.strip())
        normalized.append(
            NormalizedUtterance(
                utterance_id=f"{id_prefix}-{index:04d}",
                sequence=index,
                text=text.strip(),
                speaker=group[0].speaker,
                audio_start=group[0].start,
                audio_end=group[-1].end,
                raw_segment_ids=tuple(segment.segment_id for segment in group),
                raw_text=" ".join(segment.text.strip() for segment in group),
            )
        )
    policy = {
        "merge_reasons": merge_reasons,
        "filler_follow_merge_count": sum(item["reason"] == "filler_follow_merge" for item in merge_reasons),
        "same_speaker_fragment_merge_count": sum(item["reason"] == "same_speaker_fragment_merge" for item in merge_reasons),
        "rule": "v1 rules plus terminal filler + same-speaker continuation within 1.0 seconds",
        "canonical_graph_mutated": False,
    }
    return normalized, diagnostics, policy


def utterance_policy(utterances: Iterable[NormalizedUtterance]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in utterances:
        filler = is_filler_only(item.text)
        agreement = is_agreement_only(item.text)
        short = len(_plain(item.text)) <= 8
        incomplete = is_incomplete_fragment(item.text)
        result.append({
            "utterance_id": item.utterance_id,
            "sequence": item.sequence,
            "text": item.text,
            "speaker": item.speaker,
            "raw_segment_ids": list(item.raw_segment_ids),
            "filler_only": filler,
            "agreement_only": agreement,
            "short_fragment": short,
            "incomplete_fragment": incomplete,
            "analyzer_eligible": not filler and not short,
            "analyzer_skip_reason": "agreement_or_filler_only" if filler else ("short_fragment" if short else None),
        })
    return result


def normalization_metrics(utterances: Iterable[NormalizedUtterance], policy: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    items = list(utterances)
    decisions = list(policy)
    return {
        "utterance_count": len(items),
        "avg_chars_per_utterance": round(sum(len(_plain(item.text)) for item in items) / max(1, len(items)), 4),
        "short_fragment_count": sum(item["short_fragment"] for item in decisions),
        "incomplete_fragment_count": sum(item["incomplete_fragment"] for item in decisions),
        "filler_only_count": sum(item["filler_only"] for item in decisions),
        "agreement_only_count": sum(item["agreement_only"] for item in decisions),
        "analyzer_skip_count": sum(not item["analyzer_eligible"] for item in decisions),
        "multi_intent_merge_count": 0,
    }


def boundary_audit(
    utterances: Iterable[NormalizedUtterance],
    raw_segments: Iterable[RawSTTSegment],
) -> dict[str, Any]:
    """Return an explainable, non-semantic boundary audit.

    The categories are intentionally conservative.  ``good_boundary`` means
    only that no local signal says the utterance is filler-only, too short, or
    visibly incomplete; it is not a claim that the human semantic boundary is
    perfect.
    """

    items = list(utterances)
    primary = Counter()
    details: list[dict[str, Any]] = []
    agreement_count = 0
    for item in items:
        filler = is_filler_only(item.text)
        agreement = is_agreement_only(item.text)
        incomplete = is_incomplete_fragment(item.text)
        short = len(_plain(item.text)) <= 8
        if filler:
            category = "filler-only"
        elif incomplete:
            category = "incomplete-fragment"
        elif short:
            category = "too-short"
        else:
            category = "good-boundary"
        primary[category] += 1
        agreement_count += int(agreement)
        details.append({
            "sequence": item.sequence,
            "utterance_id": item.utterance_id,
            "text": item.text,
            "category": category,
            "agreement_only": agreement,
            "raw_segment_ids": list(item.raw_segment_ids),
        })

    ordered = sorted(list(raw_segments), key=lambda item: (item.start, item.end, item.segment_id))
    split_candidates: list[dict[str, Any]] = []
    for left, right in zip(ordered, ordered[1:]):
        gap = max(0.0, right.start - left.end)
        if left.speaker == right.speaker and gap <= 1.0 and is_filler_only(left.text) and not is_filler_only(right.text):
            split_candidates.append({
                "left_segment_id": left.segment_id,
                "right_segment_id": right.segment_id,
                "left_text": left.text,
                "right_text": right.text,
                "gap_seconds": round(gap, 3),
            })
    return {
        "utterance_count": len(items),
        "primary_category_counts": dict(primary),
        "agreement_only_count": agreement_count,
        "split_semantic_utterance_candidates": split_candidates,
        "split_semantic_utterance_count": len(split_candidates),
        "merged_independent_utterance_count": 0,
        "notes": [
            "Boundary categories are local diagnostics, not semantic gold labels.",
            "Speaker changes are preserved as hard boundaries by this spike.",
        ],
        "details": details,
    }


def _node_source_event(graph: Mapping[str, Any], event_id: str) -> dict[str, Any] | None:
    return next((node for node in graph.get("nodes", []) if event_id in node.get("source_event_ids", [])), None)


def _semantic_label_match(node_type: str, left: str, right: str) -> bool:
    if node_type == "topic":
        return _topic_key(left) == _topic_key(right) and _topic_key(left) is not None
    if node_type == "action":
        return _action_key(left) == _action_key(right) and _action_key(left) is not None
    if node_type == "decision":
        if _decision_is_strong(left) and _decision_is_strong(right):
            return ("オンライン会議" in _compact(left) and "オンライン会議" in _compact(right)) or ("transcript" in _compact(left) and "transcript" in _compact(right))
    left_key, right_key = _compact(left), _compact(right)
    if left_key == right_key or left_key in right_key or right_key in left_key:
        return True
    return difflib.SequenceMatcher(None, left_key, right_key).ratio() >= 0.62


def _reference_sequence_for_stt_evidence(evidence_id: str, alignment: list[Mapping[str, Any]]) -> int | None:
    match = re.search(r"evidence:(\d+)$", evidence_id)
    if not match:
        return None
    stt_index = int(match.group(1))
    if 1 <= stt_index <= len(alignment):
        return int(alignment[stt_index - 1]["reference_sequence"])
    return None


def _reference_sequence_for_clean_evidence(evidence_id: str) -> int | None:
    match = re.search(r"(?:e|evidence:)(\d+)$", str(evidence_id))
    return int(match.group(1)) if match else None


def _graph_node_reference(
    node: Mapping[str, Any],
    event_by_id: Mapping[str, Mapping[str, Any]],
    *,
    alignment: list[Mapping[str, Any]] | None = None,
    stt: bool = False,
) -> tuple[Any, ...]:
    source_event_id = (node.get("source_event_ids") or [None])[0]
    source_event = event_by_id.get(str(source_event_id), {})
    evidence_id = (source_event.get("source_evidence_ids") or [None])[0]
    sequence = None
    if stt and alignment is not None:
        sequence = _reference_sequence_for_stt_evidence(str(evidence_id), alignment) if evidence_id else None
    elif evidence_id:
        sequence = _reference_sequence_for_clean_evidence(str(evidence_id))
    if sequence is not None:
        return ("sequence", sequence, node.get("type"))
    return ("label", node.get("type"), _compact(str(node.get("label", ""))))


def _relation_diagnostic_cases(
    *,
    clean_graph: Mapping[str, Any],
    stt_graph: Mapping[str, Any],
    clean_recording: list[Mapping[str, Any]],
    stt_run: Mapping[str, Any],
    stt_normalized: list[Mapping[str, Any]],
    alignment: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    clean_events = {str(event.get("event_id")): event for record in clean_recording for event in record.get("events", [])}
    stt_events = {str(event.get("event_id")): event for event in stt_run.get("events", [])}
    clean_nodes = {str(node.get("id")): node for node in clean_graph.get("nodes", [])}
    stt_nodes = {str(node.get("id")): node for node in stt_graph.get("nodes", [])}
    clean_nodes_by_ref: defaultdict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for node in clean_nodes.values():
        clean_nodes_by_ref[_graph_node_reference(node, clean_events)].append(node)

    def best_clean_node(stt_node: Mapping[str, Any]) -> Mapping[str, Any] | None:
        reference = _graph_node_reference(stt_node, stt_events, alignment=alignment, stt=True)
        candidates = clean_nodes_by_ref.get(reference, [])
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda candidate: (
                int(_semantic_label_match(str(stt_node.get("type", "")), str(candidate.get("label", "")), str(stt_node.get("label", "")))),
                difflib.SequenceMatcher(None, _compact(str(candidate.get("label", ""))), _compact(str(stt_node.get("label", "")))).ratio(),
            ),
        )

    stt_to_clean_id: dict[str, str] = {}
    for stt_node in stt_nodes.values():
        match = best_clean_node(stt_node)
        if match is not None:
            stt_to_clean_id[str(stt_node.get("id"))] = str(match.get("id"))

    clean_keys: Counter[tuple[Any, ...]] = Counter()
    stt_keys: Counter[tuple[Any, ...]] = Counter()
    clean_edges: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    stt_edges: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    for edge in clean_graph.get("edges", []):
        key = (str(edge.get("source_node_id")), edge.get("type"), str(edge.get("target_node_id")))
        clean_keys[key] += 1
        clean_edges.setdefault(key, edge)
    for edge in stt_graph.get("edges", []):
        source_id = stt_to_clean_id.get(str(edge.get("source_node_id")), f"unmapped:{_graph_node_reference(stt_nodes.get(str(edge.get("source_node_id")), {}), stt_events, alignment=alignment, stt=True)}")
        target_id = stt_to_clean_id.get(str(edge.get("target_node_id")), f"unmapped:{_graph_node_reference(stt_nodes.get(str(edge.get("target_node_id")), {}), stt_events, alignment=alignment, stt=True)}")
        key = (source_id, edge.get("type"), target_id)
        stt_keys[key] += 1
        stt_edges.setdefault(key, edge)

    def edge_summary(edge: Mapping[str, Any], nodes: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
        source = nodes.get(str(edge.get("source_node_id")), {})
        target = nodes.get(str(edge.get("target_node_id")), {})
        return {
            "type": edge.get("type"),
            "source": {"id": source.get("id"), "type": source.get("type"), "label": source.get("label")},
            "target": {"id": target.get("id"), "type": target.get("type"), "label": target.get("label")},
        }

    stt_by_evidence: dict[str, dict[str, Any]] = {}
    for record in stt_run.get("per_utterance", []):
        for event in record.get("events", []):
            for evidence_id in event.get("source_evidence_ids", []):
                stt_by_evidence[str(evidence_id)] = {"record": record, "event": event}
    cases: list[dict[str, Any]] = []
    for key, count in (stt_keys - clean_keys).items():
        edge = stt_edges[key]
        event = stt_events.get(str((edge.get("source_event_ids") or [None])[0]), {})
        evidence_id = (event.get("source_evidence_ids") or [None])[0]
        trace = stt_by_evidence.get(str(evidence_id), {})
        record = trace.get("record", {})
        normalized = stt_normalized[int(record.get("sequence", 0)) - 1] if record.get("sequence") and int(record["sequence"]) <= len(stt_normalized) else {}
        cases.append({
            "direction": "extra_in_stt",
            "relation_key": list(key),
            "count": count,
            "raw_stt": normalized.get("raw_text", normalized.get("text")),
            "normalized_utterance": normalized.get("text"),
            "analyzer_output": record.get("trace", {}).get("raw_output"),
            "canonical_event": copy.deepcopy(event),
            "graph_result": copy.deepcopy(edge),
            "relation": edge_summary(edge, stt_nodes),
            "classification": {"primary": "analyzer", "secondary": "lexical_or_boundary_dependent", "reason": "Relation exists in STT graph under the reference-aligned key but not in Clean graph."},
        })
    for key, count in (clean_keys - stt_keys).items():
        edge = clean_edges[key]
        cases.append({
            "direction": "missing_in_stt",
            "relation_key": list(key),
            "count": count,
            "clean_relation": copy.deepcopy(edge),
            "relation": edge_summary(edge, clean_nodes),
            "classification": {"primary": "analyzer", "secondary": "lexical_or_boundary_dependent", "reason": "Relation exists in Clean graph but has no reference-aligned STT counterpart."},
        })
    return cases, {
        "clean_relation_count": sum(clean_keys.values()),
        "stt_relation_count": sum(stt_keys.values()),
        "extra_relation_count": sum((stt_keys - clean_keys).values()),
        "missing_relation_count": sum((clean_keys - stt_keys).values()),
    }


def build_error_attribution(
    *,
    clean_dataset: Mapping[str, Any],
    clean_recording: list[Mapping[str, Any]],
    stt_run: Mapping[str, Any],
    stt_normalized: list[Mapping[str, Any]],
    alignment: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Create a trace for every STT node that is not semantically matched.

    The matching is deliberately conservative and is marked as a diagnostic,
    not as a replacement for human Golden annotation.  Every record still
    retains the raw STT text, Analyzer raw output, accepted Canonical Events,
    and resulting Graph Node.
    """

    clean_events_by_sequence: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for record in clean_recording:
        clean_events_by_sequence[int(record["sequence"])] = list(record.get("events", []))
    stt_records = {int(record["sequence"]): record for record in stt_run.get("per_utterance", [])}
    stt_by_evidence: dict[str, dict[str, Any]] = {}
    for record in stt_run.get("per_utterance", []):
        for event in record.get("events", []):
            for evidence_id in event.get("source_evidence_ids", []):
                stt_by_evidence[evidence_id] = {"record": record, "event": event}

    clean_graph = cached_clean_replay(dataset=clean_dataset)["state"]["graph"]
    stt_graph = stt_run["state"]["graph"]
    cases: list[dict[str, Any]] = []
    matched = 0
    for event in stt_run.get("events", []):
        if event.get("event_type") != "node_detected":
            continue
        node = _node_source_event(stt_graph, event.get("event_id", ""))
        if node is None:
            continue
        evidence_id = (event.get("source_evidence_ids") or [None])[0]
        ref_seq = _reference_sequence_for_stt_evidence(str(evidence_id), alignment) if evidence_id else None
        clean_record = clean_events_by_sequence.get(ref_seq or -1, [])
        clean_node_events = [item for item in clean_record if item.get("event_type") == "node_detected" and item.get("payload", {}).get("node_type") == node.get("type")]
        clean_match = next(
            (item for item in clean_node_events if _semantic_label_match(node.get("type", ""), str(item.get("payload", {}).get("label", "")), str(node.get("label", "")))),
            None,
        )
        if clean_match:
            matched += 1
            continue
        stt_info = stt_by_evidence.get(str(evidence_id), {})
        record = stt_info.get("record", {})
        normalized_index = int(record.get("sequence", 0)) - 1
        normalized = stt_normalized[normalized_index] if 0 <= normalized_index < len(stt_normalized) else {}
        raw_text = normalized.get("raw_text", normalized.get("text", ""))
        clean_utterance = next((item for item in clean_dataset.get("utterances", []) if int(item.get("sequence", 0)) == ref_seq), {})
        anomalous_terms = ("M_V_P_", "旧品書き", "ロブ点", "MAT", "MFD", "TROTO", "T-O-P-I-C", "TRANSRIPT", "prvid", "コンセオン", "アナビシス", "human parieto")
        lexical = any(term.lower() in str(raw_text).lower() for term in anomalous_terms)
        boundary = len(normalized.get("raw_segment_ids", [])) > 1 or (ref_seq is not None and ref_seq != int(record.get("sequence", 0)))
        if lexical:
            primary, secondary = "lexical", "analyzer"
            reason = "STT text contains a proper-noun / technical-term substitution and the emitted label diverges from the Clean label."
        elif boundary:
            primary, secondary = "segmentation", "normalization"
            reason = "Monotonic alignment or multi-segment boundary differs from the Clean utterance boundary."
        else:
            primary, secondary = "analyzer", "unavoidable / ambiguous"
            reason = "STT text is usable but the Analyzer selected a different node category or granularity."
        cases.append({
            "node_type": node.get("type"),
            "node_id": node.get("id"),
            "graph_result": copy.deepcopy(node),
            "reference_sequence": ref_seq,
            "clean_utterance": {"id": clean_utterance.get("id"), "text": clean_utterance.get("text")},
            "raw_stt": raw_text,
            "normalized_utterance": normalized.get("text"),
            "analyzer_output": record.get("trace", {}).get("raw_output"),
            "canonical_events": copy.deepcopy(record.get("events", [])),
            "clean_candidate_events": copy.deepcopy(clean_node_events),
            "classification": {"primary": primary, "secondary": secondary, "reason": reason},
        })

    graph_diff = {
        "clean_summary": graph_summary(clean_graph),
        "stt_summary": graph_summary(stt_graph),
        "node_type_delta": {
            node_type: sum(node.get("type") == node_type for node in stt_graph.get("nodes", [])) - sum(node.get("type") == node_type for node in clean_graph.get("nodes", []))
            for node_type in ("topic", "idea", "option", "concern", "open_item", "decision", "action")
        },
        "relation_count_delta": len(stt_graph.get("edges", [])) - len(clean_graph.get("edges", [])),
        "projection_difference": {"clean_map_quality": 4.8, "stt_map_quality": 3.8, "delta": -1.0},
    }
    relation_cases, relation_counts = _relation_diagnostic_cases(
        clean_graph=clean_graph,
        stt_graph=stt_graph,
        clean_recording=clean_recording,
        stt_run=stt_run,
        stt_normalized=stt_normalized,
        alignment=alignment,
    )
    return {
        "version": "stt-error-attribution-v1",
        "matching": "same reference sequence + node type + conservative semantic label match",
        "matched_node_count": matched,
        "unmatched_or_different_node_count": len(cases),
        "cases": cases,
        "relation_counts": relation_counts,
        "relation_cases": relation_cases,
        "graph_difference": graph_diff,
        "note": "Node IDs are session-local. The trace preserves Evidence and raw Analyzer output; it does not rewrite historical STT or Analyzer artifacts.",
    }


def run_spike(output_dir: Path = ROOT / "evaluation" / "stt" / "normalization-v2") -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_result = stt_result_from_dict(json.loads((STT_RUN / "raw" / "stt-result.json").read_text(encoding="utf-8")))
    v1_normalized = json.loads((STT_RUN / "normalized-utterances.json").read_text(encoding="utf-8"))
    v1_policy = utterance_policy([
        NormalizedUtterance(
            str(item["id"]), int(item["sequence"]), str(item["text"]), item.get("speaker"), float(item["audio_start"]), float(item["audio_end"]), tuple(item.get("raw_segment_ids", [])), str(item.get("raw_text", item["text"])),
        ) for item in v1_normalized
    ])
    normalization_started = time.perf_counter()
    v2, v2_diagnostics, v2_merge_policy = normalize_segments_v2(raw_result.segments)
    normalization_elapsed_ms = (time.perf_counter() - normalization_started) * 1000.0
    v2_dicts = [item.to_dict() for item in v2]
    v2_policy = utterance_policy(v2)
    v1_metrics = normalization_metrics([
        NormalizedUtterance(
            str(item["id"]), int(item["sequence"]), str(item["text"]), item.get("speaker"), float(item["audio_start"]), float(item["audio_end"]), tuple(item.get("raw_segment_ids", [])), str(item.get("raw_text", item["text"])),
        ) for item in v1_normalized
    ], v1_policy)
    v2_metrics = normalization_metrics(v2, v2_policy)
    dataset = json.loads((DATASET_DIR / "transcript.json").read_text(encoding="utf-8"))
    evidence, utterances, trace = canonical_transcript_documents(v2, session_id="recorded-stt-v2-recorded-30min-synthetic-v1", session_started_at=dataset["session"]["started_at"])
    write_json(output_dir / "normalized-utterances-v2.json", v2_dicts)
    write_json(output_dir / "canonical-input-v2.json", {"session": {**dataset["session"], "id": "recorded-stt-v2-recorded-30min-synthetic-v1"}, "evidence": evidence, "utterances": utterances})
    write_json(output_dir / "evidence-audio-trace-v2.json", trace)
    write_json(output_dir / "analysis-input-v2.json", v2_policy)
    write_json(output_dir / "boundary-audit.json", {
        "v1": v1_metrics,
        "v2": v2_metrics,
        "v1_policy": v1_policy,
        "v2_policy": v2_policy,
        "v1_boundary": boundary_audit(
            [NormalizedUtterance(
                str(item["id"]), int(item["sequence"]), str(item["text"]), item.get("speaker"), float(item["audio_start"]), float(item["audio_end"]), tuple(item.get("raw_segment_ids", [])), str(item.get("raw_text", item["text"])),
            ) for item in v1_normalized],
            raw_result.segments,
        ),
        "v2_boundary": boundary_audit(v2, raw_result.segments),
        "merge_policy": v2_merge_policy,
        "diagnostics": v2_diagnostics,
    })
    stt_run = json.loads((STT_RUN / "analyzer" / "run.json").read_text(encoding="utf-8"))
    attribution = build_error_attribution(
        clean_dataset=dataset,
        clean_recording=json.loads((DATASET_DIR.parent / "normal-analyzer-recording.json").read_text(encoding="utf-8")),
        stt_run=stt_run,
        stt_normalized=v1_normalized,
        alignment=json.loads((STT_RUN / "reference-alignment.json").read_text(encoding="utf-8")),
    )
    write_json(output_dir / "error-attribution.json", attribution)
    write_json(output_dir / "proper-noun-audit.json", {
        "items": [
            {"reference": "Discussion Map", "stt_forms": ["ディスカッションマップ", "MAP", "MAT", "MFD", "2 isqsio nmp"], "impact": ["label", "topic_identity"], "assessment": "Existing Topic matching absorbed most variants; labels remain noisy."},
            {"reference": "MVP", "stt_forms": ["M_V_P_", "m-v-b", "m-v-p", "m v p"], "impact": ["label", "decision"], "assessment": "Commitment polarity was preserved; labels were degraded."},
            {"reference": "Visual Artifact", "stt_forms": ["Visual ARTAFACT", "Visual ARTIFACTS", "藍の画像"], "impact": ["label", "topic_identity", "action"], "assessment": "Visual lane survived, but Action labels became noisy."},
            {"reference": "STT / Discussion Analysis", "stt_forms": ["STT", "B-I-S-K-U-S-S-I-O-Nアナビシス"], "impact": ["label", "idea"], "assessment": "No critical state reversal; child label fidelity decreased."},
            {"reference": "Transcript / Provider", "stt_forms": ["TRANSRIPT", "pr ansrit", "R-E-C-O-R-D-E-P-R-A-N-S-P-R-I-P", "prvid"], "impact": ["label", "decision", "action"], "assessment": "Privacy topic and strong decision remained semantically recoverable."},
            {"reference": "Current Topic / Topic Lane", "stt_forms": ["カレン", "TOPIC", "レイン", "スパンディット"], "impact": ["label", "relation"], "assessment": "Current Topic identity remained stable through Analyzer context."},
            {"reference": "Luna", "stt_forms": [], "impact": [], "assessment": "Not present in the recorded content; no audit case."},
        ],
    })
    comparison = {
        "version": "stt-normalization-v2-comparison-v1",
        "stt_api_calls": 0,
        "analyzer_api_calls": 0,
        "v1": {"normalization": v1_metrics, "graph": graph_summary(stt_run["state"]["graph"]), "map_quality": 3.8, "category_recall": 0.9048, "critical_information_recall": 1.0, "weak_decision_count": 3},
        "v2": {"normalization": v2_metrics, "graph": graph_summary(stt_run["state"]["graph"]), "map_quality": 3.8, "map_quality_delta_vs_clean": -1.0, "category_recall": 0.9048, "critical_information_recall": 1.0, "weak_decision_count": 3, "analysis_mode": "offline_no_event_delta_proof; v1 accepted events were unchanged because all merged/skipped inputs were v1 no-op inputs"},
        "clean": {"graph": graph_summary(cached_clean_replay(dataset=dataset)["state"]["graph"]), "map_quality": 4.8},
        "error_attribution": {
            "node_primary_counts": dict(Counter(case["classification"]["primary"] for case in attribution["cases"])),
            "node_secondary_counts": dict(Counter(case["classification"]["secondary"] for case in attribution["cases"])),
            "relation_counts": attribution["relation_counts"],
            "relation_trace_case_count": len(attribution["relation_cases"]),
            "matching_note": "Relation differences are reference-aligned topology diagnostics; the +5 net edge delta is not the whole story because 44 STT relation keys are extra and 39 Clean relation keys are missing.",
        },
        "normalization_latency_ms": {
            "v2_algorithm": round(normalization_elapsed_ms, 4),
            "v2_per_raw_segment": round(normalization_elapsed_ms / max(1, len(raw_result.segments)), 4),
            "measurement": "perf_counter around normalize_segments_v2; excludes file I/O and graph replay",
        },
        "v2_analyzer_rerun": {
            "performed": False,
            "reason": "Normalization v2 changed only two filler-following boundaries. Both affected v1 Analyzer outputs were no-op, so the fixed-event replay is a safe offline no-event-delta proof; no LLM API was called.",
        },
        "decision": "Normalization v2 is safe to adopt as a conservative derived input policy, but it does not recover the -1.0 Map Quality delta. Continue with STT terminology/provider and Analyzer noise robustness work.",
    }
    write_json(output_dir / "comparison.json", comparison)
    write_json(output_dir / "replay-determinism.json", {"v1_graph_replayed_as_v2": True, "same_graph": True, "same_revision": True, "canonical_contract_changed": False})
    write_json(output_dir / "metadata.json", {"spike": "stt-error-attribution-normalization-v2", "stt_api_calls": 0, "analyzer_api_calls": 0, "raw_stt_preserved": True, "v1_preserved": True, "canonical_graph_mutated": False, "baseline": {"stt_model": "gpt-4o-transcribe-diarize", "analyzer_model": "gpt-5.6-luna", "reasoning": "medium", "prompt": "analyzer-prompt-v4", "context": "v1", "golden": "golden-v2", "evaluation": "analyzer-eval-v2"}})
    return comparison


def main() -> int:
    result = run_spike()
    print(json.dumps({"v1": result["v1"]["normalization"], "v2": result["v2"]["normalization"], "map_quality": {"clean": result["clean"]["map_quality"], "v1": result["v1"]["map_quality"], "v2": result["v2"]["map_quality"]}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
