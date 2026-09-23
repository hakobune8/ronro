"""JSON Schema validation backed by the repository's canonical schemas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import SchemaValidationError

try:
    from jsonschema import Draft202012Validator, FormatChecker
    from jsonschema.exceptions import SchemaError, ValidationError
except ImportError as exc:  # pragma: no cover - exercised in an uninstalled environment
    raise RuntimeError(
        "Prototype validation requires jsonschema. Install requirements-dev.txt first."
    ) from exc


class SchemaValidator:
    """Validate domain and event documents without duplicating their definitions."""

    def __init__(self, schema_dir: Path | str) -> None:
        self.schema_dir = Path(schema_dir)
        self.domain_schema = self._load_schema("discussion-domain.schema.json")
        self.event_schema = self._load_schema("discussion-event.schema.json")
        self.analyzer_output_schema = self._load_schema("real-analyzer-output.schema.json")
        self.analyzer_output_v2_schema = self._load_schema("analyzer-output-v2.schema.json")
        self.analyzer_output_v3_schema = self._load_schema("analyzer-output-v3.schema.json")
        self._domain = self._build_validator(self.domain_schema)
        self._event = self._build_validator(self.event_schema)
        self._analyzer_output = self._build_validator(self.analyzer_output_schema)
        self._analyzer_output_v2 = self._build_validator(self.analyzer_output_v2_schema)
        self._analyzer_output_v3 = self._build_validator(self.analyzer_output_v3_schema)

    def _load_schema(self, filename: str) -> dict[str, Any]:
        path = self.schema_dir / filename
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SchemaValidationError(
                "schema_invalid",
                f"Unable to load schema {path}: {exc}",
                path=str(path),
            ) from exc

    @staticmethod
    def _build_validator(schema: dict[str, Any]) -> Draft202012Validator:
        try:
            Draft202012Validator.check_schema(schema)
            return Draft202012Validator(schema, format_checker=FormatChecker())
        except SchemaError as exc:
            raise SchemaValidationError(
                "schema_invalid",
                f"Canonical schema is invalid: {exc.message}",
            ) from exc

    @staticmethod
    def _format_path(path: Any) -> str | None:
        parts = [str(part) for part in path]
        return ".".join(parts) if parts else None

    def _validate(
        self,
        validator: Draft202012Validator,
        value: Any,
        kind: str,
    ) -> None:
        error = next(validator.iter_errors(value), None)
        if error is None:
            return
        path = self._format_path(error.absolute_path)
        raise SchemaValidationError(
            "schema_invalid",
            f"{kind} does not satisfy the canonical schema: {error.message}",
            path=path,
            details={
                "validator": error.validator,
                "validator_value": error.validator_value,
            },
        )

    def validate_domain(self, value: dict[str, Any]) -> None:
        self._validate(self._domain, value, "Domain document")

    def validate_event(self, value: dict[str, Any]) -> None:
        self._validate(self._event, value, "Event")

    def validate_analyzer_output(self, value: dict[str, Any], *, version: str = "v1") -> None:
        """Validate provider-facing intent output before canonicalization."""

        validator = self._analyzer_output_v2 if version == "v2" else self._analyzer_output
        if version == "v3":
            validator = self._analyzer_output_v3
        self._validate(validator, value, f"Real Analyzer output {version}")

    def analyzer_output_schema_for(self, version: str) -> dict[str, Any] | None:
        """Return the provider-facing schema for native Structured Outputs."""

        if version == "v2":
            return self.analyzer_output_v2_schema
        if version == "v3":
            return self.analyzer_output_v3_schema
        return None
