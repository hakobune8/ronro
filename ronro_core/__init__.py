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
    "EventStore": "store", "GraphMaterializer": "materializer",
    "HumanCommandHandler": "commands", "ReplayResult": "replay",
    "ReplayRunner": "replay", "SchemaValidator": "schema",
    "StableLayout": "layout", "canonical_json": "replay",
    "display_projection": "display_labels", "initial_state": "materializer",
    "interpret_relation_correction": "relation_correction", "map_projection": "layout",
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
    "EventStore", "GraphMaterializer", "HumanCommandHandler", "ReplayResult",
    "ReplayRunner", "SchemaValidator", "StableLayout", "bundled_schema_dir",
    "canonical_json", "display_projection", "initial_state",
    "interpret_relation_correction", "map_projection", "prepare_final_record",
    "project_semantic_canvas", "render_final_pdf",
]
