"""Backward-compatible prototype entrypoint for the pure Analyzer engine.

The Core wheel includes only :mod:`analysis_engine`; this module wires the
legacy environment-configured Cloud adapter for pre-Spot prototypes.
"""

from __future__ import annotations

from .analysis_engine import *  # noqa: F403 - retain the established prototype API
from .analysis_engine import RealAnalyzer as _CoreRealAnalyzer
from .openai_analyzer_provider import OpenAICompatibleProvider


class RealAnalyzer(_CoreRealAnalyzer):
    @classmethod
    def from_environment(
        cls,
        *,
        schema_validator: SchemaValidator,
        meeting_goal: str | None = None,
        prompt_version: str = PROMPT_VERSION,
        output_schema_version: str = "v1",
    ) -> "RealAnalyzer":
        return cls(
            provider=OpenAICompatibleProvider.from_environment(),
            schema_validator=schema_validator,
            meeting_goal=meeting_goal,
            prompt_version=prompt_version,
            output_schema_version=output_schema_version,
        )
