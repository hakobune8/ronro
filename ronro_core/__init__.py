"""Provider-independent RONRO Core API for the Spot Content adapter.

Canonical meaning is defined by accepted Events and the bundled schemas.
The ``_impl`` namespace is intentionally private and may change between
package versions. Do not mix its classes with ``prototype`` classes in one
runtime; the package is the distribution boundary, not a second source.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path


_EXPORTS = {
    "AudioChunk": "live_audio", "AudioFrameError": "live_audio",
    "AudioRange": "source_stt", "LiveSTTProvider": "source_stt",
    "LiveSTTSession": "source_stt", "SourceSTTLedger": "source_stt",
    "STTBoundary": "source_stt", "STTCommitted": "source_stt", "STTDrain": "source_stt",
    "STTFailure": "source_stt", "STTFinal": "source_stt",
    "STTIntegrityError": "source_stt", "STTPartial": "source_stt", "STTSource": "source_stt",
    "EventStore": "store", "GraphMaterializer": "materializer",
    "HumanCommandHandler": "commands", "ReplayResult": "replay",
    "ReplayRunner": "replay", "SchemaValidator": "schema",
    "StableLayout": "layout", "canonical_json": "replay",
    "display_projection": "display_labels", "initial_state": "materializer",
    "interpret_relation_correction": "relation_correction", "map_projection": "layout",
    "decode_audio_frame": "live_audio", "encode_audio_frame": "live_audio",
    "float32_to_pcm16le": "live_audio", "resample_mono": "live_audio",
    "prepare_final_record": "service_final_record",
    "project_semantic_canvas": "semantic_canvas",
    "render_final_pdf": "service_final_record",
}


def __getattr__(name: str):
    """Load selected implementation only when its public symbol is used."""

    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(name)
    return getattr(import_module(f"._impl.{module}", __name__), name)


def bundled_schema_dir() -> Path:
    """Return the canonical JSON Schemas installed with this wheel."""

    return Path(__file__).resolve().parent / "schemas"


__all__ = [
    "AudioChunk", "AudioFrameError", "AudioRange", "EventStore", "GraphMaterializer", "HumanCommandHandler",
    "LiveSTTProvider", "LiveSTTSession", "ReplayResult", "SourceSTTLedger",
    "STTBoundary", "STTCommitted", "STTDrain", "STTFailure", "STTFinal",
    "STTIntegrityError", "STTPartial", "STTSource",
    "ReplayRunner", "SchemaValidator", "StableLayout", "bundled_schema_dir",
    "canonical_json", "decode_audio_frame", "display_projection", "encode_audio_frame",
    "float32_to_pcm16le", "initial_state",
    "interpret_relation_correction", "map_projection", "prepare_final_record",
    "project_semantic_canvas", "render_final_pdf", "resample_mono",
]
