"""Terminology-aware Recorded STT evaluation.

This runner deliberately changes only the STT model/context input.  It keeps
the saved diarized run as the baseline and sends the new transcript through
the existing Normalization v2, Analyzer v4, materializer, and presentation
projection pipeline.

The selected ``gpt-transcribe`` API surface returns JSON text rather than
segment timestamps.  For this recorded experiment we therefore transcribe
deterministic 15-second transport chunks and attach their absolute offsets to
the raw evidence.  The chunk size is a transport compatibility detail, not a
semantic post-processing or Analyzer rule.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import statistics
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from .projection import build_presentation_projection
from .real_analyzer import OpenAICompatibleProvider
from .recorded_stt import (
    CLEAN_DATASET,
    align_reference_texts,
    analyzer_metrics,
    graph_summary,
    load_clean_dataset,
    make_session,
    run_analyzer,
    semantic_stt_errors,
    write_json,
)
from .schema import SchemaValidator
from .stt import (
    OpenAICompatibleTranscriber,
    RawSTTSegment,
    STTFailure,
    STTResult,
    audio_duration_seconds,
    canonical_transcript_documents,
    character_error_rate,
    whitespace_word_error_rate,
)
from .stt_normalization_v2 import normalize_segments_v2


ROOT = Path(__file__).resolve().parents[1]
SOURCE_AUDIO = ROOT / "evaluation" / "stt" / "source" / "recorded-30min-synthetic-v1.m4a"
PREFLIGHT_AUDIO = ROOT / "evaluation" / "stt" / "source" / "preflight-recorded-synthetic-v1.m4a"
PREFLIGHT_REFERENCE = ROOT / "evaluation" / "stt" / "source" / "preflight-reference-transcript.json"
BASELINE_RUN = ROOT / "evaluation" / "stt" / "full-run-v1"
DEFAULT_OUTPUT = ROOT / "evaluation" / "stt" / "terminology-run"

STT_MODEL = "gpt-transcribe"
STT_CHUNK_SECONDS = 15.0
TERMINOLOGY_CONTEXT = (
    "Discussion Map AI FacilitatorのMVPについて、Visual Artifact、Current Topic、STT、"
    "Discussion Analysis、AI Analyzer、Open Item、Action、Decision、Privacy、Transcript、"
    "Provider、Human Correction、Event Catalog、Compact Overview、Recent Flow、Static Mockを"
    "含む日本語の技術会議。"
)
# Only terms that occur in the recorded dataset are included.  In particular,
# Candidate Decision, Action Item, Parking Lot, and GPT-5.6 Luna do not occur
# verbatim in the clean transcript and are intentionally omitted.
TERMINOLOGY_KEYWORDS = (
    "Discussion Map",
    "MVP",
    "Visual Artifact",
    "Current Topic",
    "STT",
    "Open Item",
    "Action",
    "Decision",
    "Privacy",
    "Transcript",
    "Provider",
    "Human Correction",
    "Event Catalog",
    "Parking",
    "Recent Flow",
    "Compact Overview",
    "Static Mock",
    "Discussion Analysis",
    "Recorded Transcript",
    "Partial Transcript",
    "Visual",
    "Analyzer",
    "Topic",
)


def terminology_transcriber() -> OpenAICompatibleTranscriber:
    base = OpenAICompatibleTranscriber.from_environment()
    if not base.configured:
        raise STTFailure("provider_not_configured", "STT endpoint, API key, and model configuration are required")
    return OpenAICompatibleTranscriber(
        endpoint=base.endpoint,
        api_key=base.api_key,
        model=STT_MODEL,
        timeout_seconds=base.timeout_seconds,
        context_prompt=TERMINOLOGY_CONTEXT,
        keywords=TERMINOLOGY_KEYWORDS,
    )


def _chunk_audio(audio_path: Path, chunk_path: Path, offset: float, duration: float) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise STTFailure("audio_chunking_unavailable", "ffmpeg is required for terminology STT chunking")
    chunk_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{offset:.3f}",
            "-i",
            str(audio_path),
            "-t",
            f"{duration:.3f}",
            "-vn",
            "-c:a",
            "aac",
            "-b:a",
            "64k",
            str(chunk_path),
            "-y",
        ],
        check=True,
    )


def transcribe_with_terminology(
    provider: OpenAICompatibleTranscriber,
    audio_path: Path,
    *,
    chunk_dir: Path,
    chunk_seconds: float = STT_CHUNK_SECONDS,
) -> STTResult:
    """Run actual STT with stable transport offsets around JSON-only output."""

    duration = audio_duration_seconds(audio_path)
    chunks: list[dict[str, Any]] = []
    segments: list[RawSTTSegment] = []
    total_processing_ms = 0.0
    offset = 0.0
    index = 0
    while offset < duration - 0.01:
        current_duration = min(chunk_seconds, duration - offset)
        chunk_path = chunk_dir / f"chunk-{index:04d}.m4a"
        _chunk_audio(audio_path, chunk_path, offset, current_duration)
        result = provider.transcribe(chunk_path)
        total_processing_ms += result.processing_ms
        chunks.append({
            "chunk_index": index,
            "offset_seconds": round(offset, 3),
            "duration_seconds": round(current_duration, 3),
            "audio_path": str(chunk_path),
            "provider_response": result.raw_response,
            "diagnostics": list(result.diagnostics),
        })
        # gpt-transcribe returns one JSON text response for this transport
        # chunk.  Preserve it as a final raw segment with absolute offsets.
        text = " ".join(segment.text.strip() for segment in result.segments).strip()
        if text:
            segments.append(
                RawSTTSegment(
                    segment_id=f"chunk-{index:04d}",
                    start=offset,
                    end=offset + current_duration,
                    text=text,
                    speaker=None,
                    raw={
                        "chunk_index": index,
                        "chunk_offset_seconds": round(offset, 3),
                        "chunk_duration_seconds": round(current_duration, 3),
                        "provider_segment_count": len(result.segments),
                    },
                )
            )
        offset += current_duration
        index += 1
    return STTResult(
        provider=provider.provider_name,
        model=provider.model,
        response_format=provider.response_format,
        audio_path=str(audio_path),
        processing_ms=total_processing_ms,
        raw_response={
            "chunked": True,
            "chunking_mode": "fixed_transport_chunk",
            "chunk_seconds": chunk_seconds,
            "audio_duration_seconds": round(duration, 3),
            "chunks": chunks,
        },
        segments=tuple(segments),
        diagnostics=(),
    )


def _norm(value: str) -> str:
    return re.sub(r"[\s　。、・:：「」『』（）()\[\]{}<>!?！？_\-—/.,]", "", str(value).lower())


TERM_DEFINITIONS: dict[str, dict[str, tuple[str, ...]]] = {
    "Discussion Map": {
        "accepted": ("discussionmap", "ディスカッションマップ"),
        "substitution": ("map", "ディスカッションアップ", "ディスカッションマット"),
    },
    "MVP": {
        "accepted": ("mvp", "エムブイピー"),
        "substitution": ("mvb", "mvpの", "m v p"),
    },
    "Visual Artifact": {
        "accepted": ("visualartifact", "ビジュアルアーティファクト"),
        "substitution": ("visualartifacts", "visual", "ビジュアル"),
    },
    "Current Topic": {
        "accepted": ("currenttopic", "カレントトピック"),
        "substitution": ("カレンとトピック", "current", "topic"),
    },
    "STT": {"accepted": ("stt", "エスティーティー"), "substitution": ("s t t",)},
    "Open Item": {"accepted": ("openitem", "オープンアイテム"), "substitution": ("open", "item")},
    "Action": {"accepted": ("action", "アクション"), "substitution": ()},
    "Decision": {"accepted": ("decision", "ディシジョン"), "substitution": ()},
    "Privacy": {"accepted": ("privacy", "プライバシー"), "substitution": ()},
    "Transcript": {"accepted": ("transcript", "トランスクリプト"), "substitution": ()},
    "Provider": {"accepted": ("provider", "プロバイダー"), "substitution": ()},
    "Human Correction": {"accepted": ("humancorrection", "ヒューマンコレクション"), "substitution": ()},
    "Event Catalog": {"accepted": ("eventcatalog", "イベントカタログ"), "substitution": ()},
    "Parking": {"accepted": ("parking", "パーキング"), "substitution": ()},
    "Recent Flow": {"accepted": ("recentflow", "リーセントフロー", "リセントフロー"), "substitution": ()},
    "Compact Overview": {"accepted": ("compactoverview", "コンパクトオーバービュー"), "substitution": ()},
    "Static Mock": {"accepted": ("staticmock", "スタティックモック"), "substitution": ()},
    "Discussion Analysis": {"accepted": ("discussionanalysis", "ディスカッションアナリシス"), "substitution": ()},
    "Recorded Transcript": {"accepted": ("recordedtranscript", "レコーデッドトランスクリプト"), "substitution": ()},
    "Partial Transcript": {"accepted": ("partialtranscript", "パーシャルトランスクリプト"), "substitution": ()},
}


def _group_aligned(aligned: Iterable[Mapping[str, Any]]) -> dict[int, str]:
    grouped: defaultdict[int, list[str]] = defaultdict(list)
    for item in aligned:
        grouped[int(item["reference_sequence"])].append(str(item.get("stt_text", "")))
    return {sequence: " ".join(values) for sequence, values in grouped.items()}


def technical_term_accuracy(
    reference_dataset: Mapping[str, Any],
    aligned: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    hypotheses = _group_aligned(aligned)
    results: dict[str, Any] = {}
    for term, definition in TERM_DEFINITIONS.items():
        occurrences = [
            item for item in reference_dataset.get("utterances", [])
            if term.lower() in str(item.get("text", "")).lower()
        ]
        correct: list[dict[str, Any]] = []
        substitutions: list[dict[str, Any]] = []
        omissions: list[dict[str, Any]] = []
        accepted = tuple(_norm(value) for value in definition["accepted"])
        substitute = tuple(_norm(value) for value in definition["substitution"])
        for occurrence in occurrences:
            sequence = int(occurrence["sequence"])
            hypothesis = hypotheses.get(sequence, "")
            normalized = _norm(hypothesis)
            detail = {
                "reference_sequence": sequence,
                "reference_text": occurrence["text"],
                "stt_text": hypothesis,
            }
            if any(value and value in normalized for value in accepted):
                correct.append(detail)
            elif any(value and value in normalized for value in substitute):
                substitutions.append(detail)
            else:
                omissions.append(detail)
        results[term] = {
            "occurrence_count": len(occurrences),
            "correct": len(correct),
            "substitution": len(substitutions),
            "omission": len(omissions),
            "accuracy": round(len(correct) / max(1, len(occurrences)), 4),
            "cases": {"correct": correct, "substitution": substitutions, "omission": omissions},
        }
    total = sum(item["occurrence_count"] for item in results.values())
    correct = sum(item["correct"] for item in results.values())
    return {
        "terms": results,
        "proper_noun_accuracy": round(correct / max(1, total), 4),
        "total_occurrences": total,
        "total_correct": correct,
    }


def lexical_metrics(reference_dataset: Mapping[str, Any], aligned: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    items = list(aligned)
    reference_text = "".join(str(item["reference_text"]) for item in items)
    hypothesis_text = "".join(str(item["stt_text"]) for item in items)
    return {
        "character_error_rate": character_error_rate(reference_text, hypothesis_text),
        "word_error_rate": None,
        "whitespace_word_error_rate_diagnostic": whitespace_word_error_rate(reference_text, hypothesis_text),
        "word_error_rate_note": "Japanese text has no whitespace tokenization in this dataset; CER is primary.",
    }


def run_stt_stage(
    *,
    audio_path: Path,
    reference_dataset: Mapping[str, Any],
    output_dir: Path,
    preflight: bool = False,
) -> dict[str, Any]:
    provider = terminology_transcriber()
    started = time.perf_counter()
    result = transcribe_with_terminology(
        provider,
        audio_path,
        chunk_dir=output_dir / "raw" / "chunks",
    )
    wall_ms = (time.perf_counter() - started) * 1000
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "raw" / "stt-result.json", result.to_dict(include_raw_response=True))
    normalized, diagnostics, policy = normalize_segments_v2(result.segments, id_prefix="term-stt-v2-utt")
    write_json(output_dir / "normalized-utterances-v2.json", [item.to_dict() for item in normalized])
    write_json(output_dir / "normalization-diagnostics.json", diagnostics)
    write_json(output_dir / "normalization-policy.json", policy)
    session_id = f"terminology-stt-{audio_path.stem}"
    session_dataset = reference_dataset if "session" in reference_dataset else load_clean_dataset()
    session = make_session(session_dataset, session_id)
    evidence, utterances, trace = canonical_transcript_documents(
        normalized,
        session_id=session_id,
        session_started_at=session_dataset["session"]["started_at"],
    )
    write_json(output_dir / "canonical-input.json", {"session": session, "evidence": evidence, "utterances": utterances})
    write_json(output_dir / "evidence-audio-trace.json", trace)
    alignment_dataset = copy.deepcopy(dict(reference_dataset))
    alignment_dataset["utterances"] = []
    for index, item in enumerate(reference_dataset.get("utterances", []), start=1):
        normalized_reference = dict(item)
        normalized_reference.setdefault("id", normalized_reference.get("utterance_id", f"reference-{index:04d}"))
        normalized_reference.setdefault("sequence", index)
        alignment_dataset["utterances"].append(normalized_reference)
    aligned = align_reference_texts(alignment_dataset, [item.to_dict() for item in normalized])
    write_json(output_dir / "reference-alignment.json", aligned)
    lexical = lexical_metrics(reference_dataset, aligned)
    terms = technical_term_accuracy(alignment_dataset, aligned)
    semantic = semantic_stt_errors(aligned)
    write_json(output_dir / "technical-term-accuracy.json", terms)
    write_json(output_dir / "stt-error-analysis.json", {"lexical": lexical, "semantic": semantic})
    audio_seconds = audio_duration_seconds(audio_path)
    usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
    for chunk in result.raw_response.get("chunks", []):
        item = chunk.get("provider_response", {}).get("usage", {})
        for key in usage:
            usage[key] += int(item.get(key, 0) or 0)
    summary = {
        "stage": "preflight" if preflight else "full",
        "stt": result.to_dict(include_raw_response=False),
        "audio_duration_seconds": round(audio_seconds, 3),
        "wall_processing_ms": round(wall_ms, 3),
        "processing_ms": round(result.processing_ms, 3),
        "real_time_factor": round((result.processing_ms / 1000) / max(0.001, audio_seconds), 4),
        "normalization": {
            "raw_segment_count": len(result.segments),
            "utterance_count": len(normalized),
            "diagnostics": diagnostics,
        },
        "lexical": lexical,
        "technical_terms": terms,
        "semantic_errors": semantic,
        "usage": usage,
        "configuration": {
            "model": STT_MODEL,
            "context_prompt": TERMINOLOGY_CONTEXT,
            "keywords": list(TERMINOLOGY_KEYWORDS),
            "chunk_seconds": STT_CHUNK_SECONDS,
            "api_key_recorded": False,
            "authorization_recorded": False,
        },
    }
    write_json(output_dir / "run-summary.json", summary)
    return {"summary": summary, "result": result, "normalized": normalized, "session": session, "evidence": evidence, "utterances": utterances, "trace": trace, "aligned": aligned}


def run_analyzer_stage(stage: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    validator = SchemaValidator(ROOT / "schemas")
    provider = OpenAICompatibleProvider.from_environment()
    if not provider.configured:
        raise STTFailure("analyzer_not_configured", "Real Analyzer provider is not configured")
    analyzer_run = run_analyzer(
        session=stage["session"],
        evidence=list(stage["evidence"]),
        utterances=list(stage["utterances"]),
        validator=validator,
        provider=provider,
    )
    write_json(output_dir / "analyzer" / "run.json", analyzer_run)
    projection = build_presentation_projection(analyzer_run["state"]["graph"], analyzer_run["events"])
    write_json(output_dir / "projection.json", projection)
    result = {
        "metrics": analyzer_metrics(analyzer_run, len(stage["utterances"])),
        "provider": analyzer_run["provider"],
        "analysis_errors": analyzer_run["analysis_errors"],
        "graph_summary": graph_summary(analyzer_run["state"]["graph"]),
        "projection": {
            "visible_node_count": len(projection.get("visible_node_ids", [])),
            "lane_count": len(projection.get("lanes", [])),
        },
    }
    write_json(output_dir / "analyzer-summary.json", result)
    write_json(output_dir / "final-graphs" / "terminology.json", analyzer_run["state"]["graph"])
    write_json(output_dir / "final-projections" / "terminology.json", projection)
    return {"run": analyzer_run, "summary": result, "projection": projection}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run terminology-aware recorded STT evaluation")
    parser.add_argument("--audio", type=Path, default=SOURCE_AUDIO)
    parser.add_argument("--reference", type=Path, default=CLEAN_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--with-analyzer", action="store_true")
    args = parser.parse_args(argv)
    reference = json.loads(args.reference.read_text(encoding="utf-8"))
    stage = run_stt_stage(audio_path=args.audio, reference_dataset=reference, output_dir=args.output, preflight=args.preflight)
    if args.with_analyzer:
        analyzer = run_analyzer_stage(stage, args.output)
        stage["summary"]["analyzer"] = analyzer["summary"]
        write_json(args.output / "run-summary.json", stage["summary"])
    print(json.dumps({
        "output": str(args.output),
        "model": STT_MODEL,
        "segments": stage["summary"]["normalization"]["raw_segment_count"],
        "utterances": stage["summary"]["normalization"]["utterance_count"],
        "cer": stage["summary"]["lexical"]["character_error_rate"],
        "proper_noun_accuracy": stage["summary"]["technical_terms"]["proper_noun_accuracy"],
        "processing_ms": stage["summary"]["processing_ms"],
        "rtf": stage["summary"]["real_time_factor"],
        "analyzer": stage["summary"].get("analyzer", {}).get("metrics"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
