"""Legacy OpenAI-compatible Chat Completions adapter for RONRO prototypes.

Do not bundle this vendor transport in ronro-core; Spot Content selects its
own Cloud or Local Analyzer Provider and owns credentials/network policy.
"""

from __future__ import annotations

import copy
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Mapping

from .analysis_engine import ProviderFailure, ProviderResponse


class OpenAICompatibleProvider:
    """Small JSON-only adapter for an OpenAI-compatible Chat Completions API.

    The adapter intentionally does not expose provider-specific objects to the
    Analyzer.  Configuration is read only when the Recorded Spike is started:

    - ``REAL_ANALYZER_ENDPOINT`` or ``OPENAI_BASE_URL``
    - ``REAL_ANALYZER_API_KEY`` or ``OPENAI_API_KEY``
    - ``REAL_ANALYZER_MODEL`` or ``OPENAI_MODEL``

    The endpoint is configurable so the spike can use a compatible hosted or
    local provider without changing the Analyzer boundary.
    """

    provider_name = "openai-compatible"

    def __init__(
        self,
        *,
        endpoint: str | None,
        api_key: str | None,
        model: str | None,
        timeout_seconds: float = 45.0,
        reasoning_effort: str | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.model = model or ""
        self.timeout_seconds = timeout_seconds
        self.reasoning_effort = reasoning_effort

    @classmethod
    def from_environment(cls) -> "OpenAICompatibleProvider":
        endpoint = os.getenv("REAL_ANALYZER_ENDPOINT") or os.getenv("OPENAI_BASE_URL")
        if endpoint is None and os.getenv("OPENAI_API_KEY"):
            endpoint = "https://api.openai.com/v1/chat/completions"
        api_key = os.getenv("REAL_ANALYZER_API_KEY") or os.getenv("OPENAI_API_KEY")
        model = os.getenv("REAL_ANALYZER_MODEL") or os.getenv("OPENAI_MODEL")
        timeout_raw = os.getenv("REAL_ANALYZER_TIMEOUT_SECONDS", "45")
        reasoning_effort = (
            os.getenv("REAL_ANALYZER_REASONING_EFFORT")
            or os.getenv("OPENAI_REASONING_EFFORT")
            or "medium"
        )
        try:
            timeout = float(timeout_raw)
        except ValueError:
            timeout = 45.0
        return cls(
            endpoint=endpoint,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout,
            reasoning_effort=reasoning_effort,
        )

    @property
    def configured(self) -> bool:
        return bool(self.endpoint and self.api_key and self.model)

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: Mapping[str, Any],
        response_schema: Mapping[str, Any] | None = None,
    ) -> ProviderResponse:
        if not self.endpoint:
            raise ProviderFailure("provider_not_configured", "REAL_ANALYZER_ENDPOINT or OPENAI_BASE_URL is not configured")
        if not self.api_key:
            raise ProviderFailure("provider_not_configured", "REAL_ANALYZER_API_KEY or OPENAI_API_KEY is not configured")
        if not self.model:
            raise ProviderFailure("provider_not_configured", "REAL_ANALYZER_MODEL or OPENAI_MODEL is not configured")

        endpoint = self.endpoint.rstrip("/")
        if endpoint.endswith("/v1"):
            endpoint = f"{endpoint}/chat/completions"
        request_body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        }
        if response_schema is not None:
            request_body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "discussion_analyzer_output_v3" if response_schema.get("$id") == "urn:discussion-map:analyzer-output-v3" else "discussion_analyzer_output_v2",
                    "strict": True,
                    "schema": copy.deepcopy(dict(response_schema)),
                },
            }
        else:
            request_body["response_format"] = {"type": "json_object"}
        if self.reasoning_effort:
            request_body["reasoning_effort"] = self.reasoning_effort
        else:
            request_body["temperature"] = 0
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        started = time.perf_counter()
        try:
            # The endpoint is operator-supplied configuration, not user input.
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:  # nosec B310
                raw_response = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ProviderFailure("provider_http_error", f"Provider returned HTTP {exc.code}: {body[:400]}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProviderFailure("provider_network_error", str(exc)) from exc

        elapsed_ms = (time.perf_counter() - started) * 1000
        try:
            response_body = json.loads(raw_response)
            raw_text = self._extract_text(response_body)
            output = json.loads(raw_text)
        except (ValueError, TypeError, KeyError) as exc:
            raise ProviderFailure("provider_output_invalid", f"Provider did not return a JSON object: {exc}") from exc
        if not isinstance(output, dict):
            raise ProviderFailure("provider_output_invalid", "Provider output must be a JSON object")

        usage = response_body.get("usage", {}) if isinstance(response_body, dict) else {}
        completion_details = usage.get("completion_tokens_details", {}) if isinstance(usage, Mapping) else {}
        reasoning_tokens = self._int_or_none(completion_details.get("reasoning_tokens")) if isinstance(completion_details, Mapping) else None
        prompt_tokens = self._int_or_none(usage.get("prompt_tokens"))
        completion_tokens = self._int_or_none(usage.get("completion_tokens"))
        total_tokens = self._int_or_none(usage.get("total_tokens"))
        return ProviderResponse(
            output=output,
            raw_text=raw_text,
            provider_name=self.provider_name,
            model=self.model,
            latency_ms=elapsed_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            reasoning_tokens=reasoning_tokens,
            cost_usd=self._estimate_cost(prompt_tokens, completion_tokens),
        )

    @staticmethod
    def _extract_text(response_body: Mapping[str, Any]) -> str:
        # Chat Completions-compatible shape.
        choices = response_body.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message", {})
            content = message.get("content") if isinstance(message, Mapping) else None
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = [part.get("text", "") for part in content if isinstance(part, Mapping)]
                return "".join(parts)
        # A small compatibility path for providers exposing output_text.
        output_text = response_body.get("output_text")
        if isinstance(output_text, str):
            return output_text
        raise KeyError("choices[0].message.content")

    @staticmethod
    def _int_or_none(value: Any) -> int | None:
        return value if isinstance(value, int) else None

    def _estimate_cost(self, prompt_tokens: int | None, completion_tokens: int | None) -> float | None:
        """Estimate text-token cost for the fixed Run #1 model when possible."""

        if prompt_tokens is None or completion_tokens is None:
            return None
        if self.model != "gpt-5.6-luna":
            return None
        return round((prompt_tokens * 0.20 + completion_tokens * 1.20) / 1_000_000, 8)
