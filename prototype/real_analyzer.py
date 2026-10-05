"""Recorded Real Analyzer boundary for the pre-STT spike.

The provider-facing format in this module is deliberately smaller than the
canonical Event envelope.  A provider may suggest an intent, a node type, a
label, and references to existing or same-response nodes.  The application
owns event IDs, sequences, session IDs, timestamps, and all safety checks
before a CandidateEvent is returned to the existing replay pipeline.

No provider SDK is required.  ``OpenAICompatibleProvider`` uses the standard
library and is only activated when an endpoint, API key, and model are
configured.  ``StaticJsonProvider`` is a test double for parser and contract
tests; it is not a claim of real-model quality.
"""

from __future__ import annotations

import copy
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Protocol

from .analyzer import CandidateEvent
from .errors import PrototypeError
from .materializer import GraphMaterializer, RELATION_MATRIX
from .schema import SchemaValidator
from .display_labels import INSTRUCTION as DISPLAY_INSTRUCTION, POLICY_VERSION


PROMPT_VERSION = "analyzer-prompt-v1"
PROMPT_VERSION_V2 = "analyzer-prompt-v2"
PROMPT_VERSION_V3 = "analyzer-prompt-v3"
PROMPT_VERSION_V4 = "analyzer-prompt-v4"
PROMPT_VERSION_V5 = "analyzer-prompt-v5"
PROMPT_VERSION_V6 = "analyzer-prompt-v6-semantic-graph-hypothesis"
PROMPT_VERSION_V7 = "analyzer-prompt-v7-correctable-working-graph"
PROMPT_VERSION_V8 = "analyzer-prompt-v8-explicit-candidate-decision"
PROMPT_VERSION_V9 = "analyzer-prompt-v9-semantic-edge-balance"
PROMPT_VERSION_V10 = "analyzer-prompt-v10-action-time-horizon"
HUMAN_EVENT_TYPES = {
    "confirm_decision",
    "revoke_decision",
    "resolve_open_item",
    "reopen_open_item",
    "rename_node",
    "archive_node",
    "merge_nodes",
    "move_to_parking_lot",
    "restore_from_parking_lot",
    "update_action",
    "set_current_topic",
    "undo_last_correction",
    "correct_relation",
}
NODE_TYPES = {"topic", "idea", "option", "concern", "open_item", "decision", "action"}
EXPLICIT_ACTION_MARKERS = (
    "作ります",
    "作成します",
    "実装します",
    "対応します",
    "確認します",
    "確認してください",
    "調べます",
    "整理します",
    "お願いします",
    "進めます",
)
ACTION_SUGGESTION_MARKERS = (
    "かもしれません",
    "方がいい",
    "た方がよい",
    "できるといい",
    "検討したい",
    "したいです",
    "どうですか",
)
AGREEMENT_MARKERS = ("それでいきましょう", "その方向でいきましょう", "了解です", "わかりました", "そうですね")


class Provider(Protocol):
    """Minimal provider capability required by RealAnalyzer."""

    provider_name: str
    model: str

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: Mapping[str, Any],
        response_schema: Mapping[str, Any] | None = None,
    ) -> "ProviderResponse":
        ...


@dataclass(frozen=True)
class ProviderResponse:
    output: Any
    raw_text: str
    provider_name: str
    model: str
    latency_ms: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None

    def usage_dict(self) -> dict[str, int | None]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "total_tokens": self.total_tokens,
        }


class ProviderFailure(RuntimeError):
    """A provider call failed before a Candidate Event could be produced."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


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


class StaticJsonProvider:
    """Deterministic provider double used for contract tests and dry runs."""

    provider_name = "static-json"

    def __init__(self, responses: Iterable[Mapping[str, Any]], model: str = "static") -> None:
        self._responses = [copy.deepcopy(dict(response)) for response in responses]
        self._index = 0
        self.model = model

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: Mapping[str, Any],
        response_schema: Mapping[str, Any] | None = None,
    ) -> ProviderResponse:
        del system_prompt, user_payload, response_schema
        if self._index >= len(self._responses):
            raise ProviderFailure("provider_exhausted", "Static provider has no response for this utterance")
        output = copy.deepcopy(self._responses[self._index])
        self._index += 1
        raw_text = json.dumps(output, ensure_ascii=False, sort_keys=True)
        return ProviderResponse(
            output=output,
            raw_text=raw_text,
            provider_name=self.provider_name,
            model=self.model,
            latency_ms=0.0,
        )


class AnalysisContextBuilder:
    """Build a bounded, canonical-only context for one Final Utterance."""

    def __init__(self, *, recent_event_limit: int = 8, node_limit: int = 32) -> None:
        self.recent_event_limit = recent_event_limit
        self.node_limit = node_limit

    def build(
        self,
        *,
        utterance: Mapping[str, Any],
        current_graph: Mapping[str, Any],
        recent_events: Iterable[Mapping[str, Any]],
        meeting_goal: str | None,
    ) -> dict[str, Any]:
        graph_nodes = list(current_graph.get("nodes", []))
        graph_edges = list(current_graph.get("edges", []))
        current = current_graph.get("current_topic", {})
        current_id = current.get("primary_topic_id")

        active_topics = [
            self._node_summary(node)
            for node in graph_nodes
            if node.get("type") == "topic" and node.get("status") == "active"
        ]
        active_topics.sort(key=lambda node: node["id"])

        relevant_ids = {node["id"] for node in active_topics}
        if current_id:
            relevant_ids.add(current_id)
            for edge in graph_edges:
                if edge.get("source_node_id") == current_id:
                    relevant_ids.add(edge.get("target_node_id"))
                if edge.get("target_node_id") == current_id:
                    relevant_ids.add(edge.get("source_node_id"))
        relevant_nodes = [
            self._node_summary(node)
            for node in graph_nodes
            if node.get("id") in relevant_ids and node.get("status") not in {"archived", "parked"}
        ]
        relevant_nodes.sort(key=lambda node: (node["type"] != "topic", node["id"]))
        relevant_nodes = relevant_nodes[: self.node_limit]

        events = []
        for event in list(recent_events)[-self.recent_event_limit :]:
            events.append(
                {
                    "sequence": event.get("sequence"),
                    "event_type": event.get("event_type"),
                    "actor": event.get("actor"),
                    "source_evidence_ids": list(event.get("source_evidence_ids", [])),
                    "payload": copy.deepcopy(event.get("payload", {})),
                }
            )

        return {
            "meeting_goal": meeting_goal,
            "current_utterance": {
                "id": utterance.get("id"),
                "sequence": utterance.get("sequence"),
                "text": utterance.get("text"),
                "evidence_ids": list(utterance.get("evidence_ids", [])),
            },
            "current_topic": {
                "primary_topic_id": current_id,
                "mode": current.get("mode", "derived"),
            },
            "relevant_nodes": relevant_nodes,
            "recent_events": events,
            "output_contract": {
                "events": "array of node, relation, or topic_focus intents; return [] when no meaningful change is present",
                "ids": "return existing_node_id only for IDs shown in relevant_nodes; never invent canonical IDs",
                "safety": "never return human commands, confirmed decisions, inferred owners, or inferred due dates",
            },
        }

    def augment_for_semantic_relations(
        self, context: dict[str, Any], graph: Mapping[str, Any], utterance: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Bounded cross-Topic retrieval for opt-in late relations.

        Lexical overlap only retrieves candidates; it never asserts an edge.
        Recent/current-context Nodes remain available when wording differs.
        """
        text = re.sub(r"[\s　。、・:：「」『』（）()\-—]+", "", str(utterance.get("text", ""))).lower()
        grams = {text[i:i + 2] for i in range(max(0, len(text) - 1))}
        existing = {n["id"] for n in context["relevant_nodes"]}
        nodes = [n for n in graph.get("nodes", []) if n.get("status") not in {"archived", "parked"}]
        def lexical(node: Mapping[str, Any]) -> int:
            label = re.sub(r"[\s　。、・:：「」『』（）()\-—]+", "", str(node.get("label", ""))).lower()
            return len(grams & {label[i:i + 2] for i in range(max(0, len(label) - 1))})
        # Prefer strongly mentioned old Nodes, then keep existing current-Topic
        # context and latest Nodes. Stable IDs break all remaining ties.
        matched = sorted((n for n in nodes if lexical(n) >= 2),
                         key=lambda n: (-lexical(n), n["id"]))
        current = sorted((n for n in nodes if n["id"] in existing), key=lambda n: n["id"])
        recent = sorted(nodes, key=lambda n: (str(n.get("updated_at") or ""), n["id"]), reverse=True)
        ordered = matched + current + recent
        selected: list[dict[str, Any]] = []
        seen: set[str] = set()
        for node in ordered:
            if node["id"] not in seen:
                selected.append(self._node_summary(node))
                seen.add(node["id"])
                if len(selected) >= self.node_limit:
                    break
        context["relevant_nodes"] = selected
        return context

    @staticmethod
    def _node_summary(node: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "id": node.get("id"),
            "type": node.get("type"),
            "label": node.get("label"),
            "status": node.get("status"),
        }

    @staticmethod
    def measure(context: Mapping[str, Any]) -> dict[str, int]:
        serialized = json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return {
            "context_chars": len(serialized),
            "estimated_tokens": max(1, (len(serialized) + 3) // 4),
        }


def build_analyzer_prompt(
    context: Mapping[str, Any],
    *,
    prompt_version: str = PROMPT_VERSION,
) -> tuple[str, dict[str, Any]]:
    """Return a versioned system instruction and JSON user payload."""

    if prompt_version == PROMPT_VERSION_V4:
        return build_analyzer_prompt_v4(context)
    if prompt_version == PROMPT_VERSION_V5:
        return build_analyzer_prompt_v5(context)
    if prompt_version == PROMPT_VERSION_V6:
        return build_analyzer_prompt_v6(context)
    if prompt_version == PROMPT_VERSION_V7:
        return build_analyzer_prompt_v7(context)
    if prompt_version == PROMPT_VERSION_V8:
        return build_analyzer_prompt_v8(context)
    if prompt_version == PROMPT_VERSION_V9:
        return build_analyzer_prompt_v9(context)
    if prompt_version == PROMPT_VERSION_V10:
        return build_analyzer_prompt_v10(context)
    if prompt_version == PROMPT_VERSION_V3:
        return build_analyzer_prompt_v3(context)
    if prompt_version == PROMPT_VERSION_V2:
        return build_analyzer_prompt_v2(context)

    system_prompt = f"""You are Discussion Map Analyzer {PROMPT_VERSION}.
Return JSON only with this shape: {{\"events\": [intent, ...]}}.
An intent is exactly one of:
1. node: node_type, label, source_evidence_ids, and action={{owner,due_date}} for action nodes;
2. relation: source, target, relation_type, source_evidence_ids;
3. topic_focus: topic, optional confidence, source_evidence_ids.
Use existing_node_id only when it is present in the supplied relevant_nodes. For a node created in this response, use new_node_index in references; the application assigns the canonical ID.
Return [] for acknowledgements, filler, or statements that do not change the Discussion Model.
Decisions are always candidate nodes. Never emit confirm_decision or revoke_decision. Never emit any human correction command.
Only explicit execution intent is an action. A suggestion, wish, or question is not an action.
Set owner or due_date only when the current utterance states it explicitly; otherwise use null.
Do not infer facts that are absent from the current utterance or supplied context. Keep labels short and meaningful in Japanese, usually 10-30 characters.
"""
    return system_prompt, copy.deepcopy(dict(context))


def build_analyzer_prompt_v2(context: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Return the constrained v2 prompt without changing semantic policy."""

    system_prompt = f"""You are Discussion Map Analyzer {PROMPT_VERSION_V2}.
Return exactly one JSON object and nothing else. Do not emit Markdown, prose, comments, or reasoning.
The root object has exactly one key: events. It is an array. If there is no meaningful model change, return {{"events":[]}}.

Every event in events must be one of these flat intent shapes:
1) node: kind="node", node_type, label, existing_node_id, source_evidence_ids.
   node_type is exactly one of: topic, idea, option, concern, open_item, decision, action.
   For action, also include action={{owner,due_date}}. For every other node, do not include action.
2) relation: kind="relation", source, target, relation_type, source_evidence_ids.
3) topic focus: kind="topic_focus", topic, confidence, source_evidence_ids.

All fields in these shapes are required by the output schema. Use null for an unavailable nullable value.
For a node, existing_node_id is an existing ID from relevant_nodes or null for a new node.
For a reference object, include both existing_node_id and new_node_index; set one to null and use the other.
new_node_index counts only node intents, starting at 0. Never invent a canonical node ID.
The application owns event_id, session_id, sequence, occurred_at, expected_revision, and all new IDs.

Allowed relation_type values are exactly: contains, has_option, supports, opposes, related_to.
Relation constraints: contains is Topic -> Idea/Option/Concern/Open Item/Decision/Action; has_option is Topic -> Option;
supports is Idea/Option -> Idea/Option/Decision; opposes is Idea/Option/Concern -> Idea/Option/Decision;
related_to connects two non-archived nodes. Do not invent other relations.

A decision is always a candidate node. Never emit confirmed, agreed, accepted, approved, final, rejected,
confirm_decision, revoke_decision, or any human correction command.
Only explicit execution intent is an action. Suggestions, wishes, questions, and agreement are not actions.
Set owner or due_date only when the current utterance states them explicitly. Use null for unknown values;
relative phrases such as “次回まで” are not ISO dates and must use due_date=null.
Question and Unresolved Item use node_type=open_item. Parking Lot is not a node type.
Do not create a new Topic when an existing relevant Topic is the subject of a return.

Small shape examples:
Input: 「Visual生成は自動にするんですか？」
Output: {{"events":[{{"kind":"node","node_type":"open_item","label":"Visual生成の自動化","existing_node_id":null,"source_evidence_ids":["e1"]}}]}}

Input: 「スマホUIはMVPから外しましょう」
Output: {{"events":[{{"kind":"node","node_type":"decision","label":"スマホUIはMVP対象外","existing_node_id":null,"source_evidence_ids":["e1"]}}]}}

Input: 「それでいきましょう」
Output: {{"events":[]}}

Input: 「次回までにVisual Prototypeを作ります」
Output: {{"events":[{{"kind":"node","node_type":"action","label":"Visual Prototypeを作る","existing_node_id":null,"source_evidence_ids":["e1"],"action":{{"owner":null,"due_date":null}}}}]}}

Input: 「Visual Prototypeも作った方がいいかもしれません」
Output: {{"events":[]}}

Input: 「なるほど」
Output: {{"events":[]}}

Context has topic-123 labeled Discussion Map. Input: 「さっきのDiscussion Mapの話に戻ると」
Output: {{"events":[{{"kind":"topic_focus","topic":{{"existing_node_id":"topic-123","new_node_index":null}},"confidence":null,"source_evidence_ids":["e1"]}}]}}
"""
    return system_prompt, copy.deepcopy(dict(context))


def build_analyzer_prompt_v3(context: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Return the v2 contract with a semantic-only classification policy.

    v3 deliberately keeps the provider-facing shape unchanged.  Its additions
    explain when a durable Topic is warranted, how to prefer existing Topics,
    and how to separate preferences, candidate decisions, and actions.
    """

    system_prompt = f"""You are Discussion Map Analyzer {PROMPT_VERSION_V3}.
Return exactly one JSON object and nothing else. Do not emit Markdown, prose, comments, or reasoning.
The root object has exactly one key: events. It is an array. If there is no meaningful model change, return {{"events":[]}}.

OUTPUT CONTRACT (unchanged from analyzer-prompt-v2)
Every event in events must be one of these flat intent shapes:
1) node: kind="node", node_type, label, existing_node_id, source_evidence_ids.
   node_type is exactly one of: topic, idea, option, concern, open_item, decision, action.
   For action, also include action={{owner,due_date}}. For every other node, do not include action.
2) relation: kind="relation", source, target, relation_type, source_evidence_ids.
3) topic focus: kind="topic_focus", topic, confidence, source_evidence_ids.

All fields in these shapes are required by the output schema. Use null for an unavailable nullable value.
For a node, existing_node_id is an existing ID from relevant_nodes or null for a new node.
For a reference object, include both existing_node_id and new_node_index; set one to null and use the other.
new_node_index counts only node intents, starting at 0. Never invent a canonical node ID.
The application owns event_id, session_id, sequence, occurred_at, expected_revision, and all new IDs.

Allowed relation_type values are exactly: contains, has_option, supports, opposes, related_to.
Relation constraints: contains is Topic -> Idea/Option/Concern/Open Item/Decision/Action; has_option is Topic -> Option;
supports is Idea/Option -> Idea/Option/Decision; opposes is Idea/Option/Concern -> Idea/Option/Decision;
related_to connects two non-archived nodes. Do not invent other relations.

A decision is always a candidate node. Never emit confirmed, agreed, accepted, approved, final, rejected,
confirm_decision, revoke_decision, or any human correction command.
Only explicit execution intent is an action. Suggestions, wishes, questions, preferences, and agreement are not actions.
Set owner or due_date only when the current utterance states them explicitly. Use null for unknown values;
relative phrases such as “次回まで” are not ISO dates and must use due_date=null.
Question and Unresolved Item use node_type=open_item. Parking Lot is not a node type.
Do not create a new Topic when an existing relevant Topic is the subject of a return.

SEMANTIC POLICY
The Discussion Map represents meaning, not a transcript. One utterance may produce zero, one, or several useful
events, but never create a node mechanically for every sentence. When uncertain, prefer fewer high-value nodes over
many speculative nodes.

A Topic is a relatively persistent discussion axis that can group multiple Ideas, Options, Concerns, Decisions, or
Actions. A single opinion, concrete proposal, person, feature, or artifact is normally a child node, not a Topic.
For example, “スマホUIも必要だと思います” is normally an idea or option under “MVP範囲”, not a new Topic named
“スマホUI”. Likewise, “Visual Prototype” is normally an Action or Idea under the current Topic.

Choose a Topic in this order:
1) If the utterance belongs naturally to the current Topic, use that Topic and do not create another one.
2) If it refers back to a previously discussed axis, use that existing Topic ID and emit topic_focus only when focus changes.
3) If it is a related but independent discussion axis, use an existing related Topic if one is shown.
4) Only then create a new Topic. Create it when a new durable axis clearly begins, cannot naturally fit an existing Topic,
   is likely to receive multiple nodes, or is meaningful as an independent step in Discussion Flow.

When there is no current Topic and the utterance starts a durable axis, create one concise Topic and attach meaningful
child nodes with contains/has_option when appropriate. Use the Meeting Goal and Session context to name the broader
axis, but do not invent unrelated content. Prefer at most one new Topic per utterance; do not create Topics for every
noun in a compound sentence.

Distinguish a Topic Return from a Related Topic. “さっきのMVP範囲の話に戻ると” is a return and must reference the
existing MVP Topic. Moving from MVP範囲 to a separately discussable 価格モデル is a related but distinct Topic and
may create/focus that Topic. Different wording with the same durable meaning still refers to the same Topic.

Decision candidates are narrow. Emit node_type=decision only when a participant explicitly proposes a direction,
scope choice, or option to proceed with, such as “スマホUIはMVPから外しましょう” or “この方式を採用する方向で
進めます”. A preference such as “Aの方がいいと思います”, “良さそう”, or “なくてもいいかもしれません” is an
idea/option, not a decision. “そうですね”, “賛成です”, “それでいいと思います”, and “それでいきましょう” do
not confirm a decision and normally produce events: []. Never emit a human confirmation event.

Actions require explicit execution intent for a concrete next step: “次回までにPrototypeを作ります” or
“山田さん、金曜までにPrototypeお願いします”. “作った方がいい”, “検討したい”, “できるといい”, and
“必要かもしれない” are not actions. If a sentence says “Prototypeを作ることにしましょう”, prefer Decision when
it primarily selects a policy, and prefer Action when an executor and concrete execution are clearly specified; do not
emit both unless the utterance clearly contains both independent intents. Never infer owner or due_date.

Use open_item for an unresolved question or issue, and concern for a risk or problem. Do not create a Topic merely for
a concern, question, or option that naturally belongs under an existing Topic.

SEMANTIC EXAMPLES (shape remains flat)
Input: 「MVPはDiscussion Mapを中心にしたいです」 with no current Topic and goal about deciding MVP value
Output: a durable MVP-scope Topic plus a Discussion Map Idea and a contains relation, or a single high-value Topic if
the utterance does not provide enough evidence for both. Do not create unrelated Topics for each noun.

Input: 「料金は月額の方がいいですかね」 followed by 「従量課金もありそうです」
Output: one Topic such as 料金体系/価格モデル, then Options under it; do not create a Topic for each pricing option.

Input: 「Aの方がいいと思います」
Output: an idea or option, never a decision.

Input: 「Aで進めましょう」
Output: a candidate decision only; never a confirmed decision or human command.

Input: 「次回までにVisual Prototypeを作ります」
Output: an action with owner=null and due_date=null when the utterance does not explicitly state them.

Input: 「Visual Prototypeも作った方がいいかもしれません」
Output: events: [] or an idea/open_item when meaningful; never an action.

Input: Existing Topic topic-123 labeled Discussion Map; 「さっきの議論可視化の話に戻ると」
Output: topic_focus referencing existing_node_id=topic-123; do not create a new Topic.

Input: 「なるほど」 or 「それでいきましょう」
Output: {{"events":[]}} unless a separate substantive intent is explicitly present.
"""
    return system_prompt, copy.deepcopy(dict(context))


def build_analyzer_prompt_v4(context: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Return v3 semantic guidance with conservative decisions and node economy."""

    system_prompt = f"""You are Discussion Map Analyzer {PROMPT_VERSION_V4}.
Return exactly one JSON object and nothing else. Do not emit Markdown, prose, comments, or reasoning.
The root object has exactly one key: events. It is an array. If there is no meaningful model change, return {{"events":[]}}.

OUTPUT CONTRACT (keep this provider-facing contract exactly)
Every event in events must be one of these flat intent shapes:
1) node: kind="node", node_type, label, existing_node_id, source_evidence_ids.
   node_type is exactly one of: topic, idea, option, concern, open_item, decision, action.
   For action, also include action={{owner,due_date}}. For every other node, do not include action.
2) relation: kind="relation", source, target, relation_type, source_evidence_ids.
3) topic focus: kind="topic_focus", topic, confidence, source_evidence_ids.

All fields required by the output schema must be present. Use null for nullable values.
For a node, existing_node_id is an existing ID shown in relevant_nodes or null for a new node.
For a reference object, include both existing_node_id and new_node_index; set one to null and use the other.
new_node_index counts only node intents in this response, starting at 0. Never invent a canonical Node ID.
The application owns event_id, session_id, sequence, occurred_at, expected_revision, and all new IDs.

Allowed relation_type values are exactly: contains, has_option, supports, opposes, related_to.
Relation constraints: contains is Topic -> Idea/Option/Concern/Open Item/Decision/Action; has_option is Topic -> Option;
supports is Idea/Option -> Idea/Option/Decision; opposes is Idea/Option/Concern -> Idea/Option/Decision;
related_to connects two non-archived nodes. Do not invent other relations.

Never emit confirmed, agreed, accepted, approved, final, rejected, confirm_decision, revoke_decision,
or any human correction command. A decision node is always candidate.
Only explicit execution intent is an action. Suggestions, wishes, questions, preferences, and agreement are not actions.
Set owner or due_date only when the current utterance states them explicitly; otherwise use null.
Relative phrases such as “次回まで” are not ISO dates and must use due_date=null.
Question and Unresolved Item use node_type=open_item. Parking Lot is not a node type.

TOPIC POLICY
A Topic is a relatively persistent discussion axis that can group multiple Ideas, Options, Concerns, Decisions, or
Actions. A single opinion, feature, proposal, artifact, or concrete option is normally a child node, not a Topic.
The Discussion Map is a compact meaning structure, not a transcript.

Before creating a new Topic, check in this order:
1) Current Topic: use it if the utterance naturally belongs there.
2) Existing Topic: use an existing Topic ID if the utterance returns to the same durable meaning.
3) Related Topic: use an existing related axis when it is already represented.
4) New Topic: create one only for a new durable axis that cannot fit the existing Topics and can plausibly hold
   multiple useful nodes or represents an independent Discussion Flow step.
Prefer semantic identity over surface wording. “さっきの議論可視化の話に戻ると” must reference an existing
Discussion Map Topic rather than create a synonym.

Keep the Run #3 implicit Topic detection rule: an explicit “let us discuss” phrase is not required when a durable
axis clearly starts. When there is no current Topic and the utterance starts such an axis, create a concise Topic
using the utterance and Meeting Goal/Session context, but do not create a Topic for every noun.
If a newly created Topic is the focus of the current utterance, emit topic_focus for that new Topic in the same
response using its new_node_index. Mentioning a future or secondary topic does not change focus; focus the topic
that is actually being advanced in the current utterance.

NODE ECONOMY
Create 0-2 new node intents per utterance as the strong default. If more than two concepts are mentioned, keep only
the highest-value concepts and omit speculative or repetitive ones. Do not split synonyms or one semantic contribution
into multiple nodes. Do not create a Topic and an almost-equivalent Idea such as Topic “料金体系” plus Idea
“料金体系について検討する”. A Topic plus one distinct child may be enough.

RELATION ECONOMY
Create 0-2 new relation intents per utterance as the default. Emit only relations that materially improve Map
understanding. Prefer one contains relation for a child under a newly created Topic and has_option for options.
Use supports, opposes, or related_to only when the relation is explicit and important. Do not use related_to as a
fallback, and do not connect nodes merely because they share a Topic. When contains is sufficient, do not add
cross-relations.

CONSERVATIVE DECISION POLICY
Run these internal checks without outputting reasoning:
A) What exactly is the selectable option, scope, or policy being decided?
B) Does the current utterance contain commitment language such as “〜で進めましょう”, “〜にする”,
   “〜から外しましょう”, or “〜を採用します”?
C) Is it stronger than a preference, comparison, proposal, possibility, question, or impression?
Only emit node_type=decision when all A/B/C are satisfied. If uncertain, do not create a Decision.
An opening framing statement, an architectural principle, or a general meeting direction is usually an Idea unless
it clearly selects a concrete alternative or scope after a choice is being considered. For example, “共有画面を
中心にしましょう” at the opening is normally an Idea/Topic framing; “スマホUIはMVPから外しましょう” is a
Candidate Decision because it selects a concrete scope. “Graphを決定的にしてLLMを外す方針で進めましょう”
is an Idea unless the utterance clearly resolves an explicit competing option.

Decision and non-decision examples:
“Aの方がいいと思います” -> Idea or Preference, not Decision.
“Aでもいいかもしれません” -> Idea, not Decision.
“Aが良さそうですね” -> Idea, not Decision.
“Aという選択肢もあります” -> Option, not Decision.
“Aにするんですか？” -> Open Item, not Decision.
“Aで進めましょう” -> Candidate Decision only when A is a concrete choice being selected.
“Aは今回は外しましょう” -> Candidate Decision when A is a concrete scope choice.

AGREEMENT SAFETY
“そうですね”, “賛成です”, “それでいいと思います”, “了解です”, and “それでいきましょう” alone are
not Candidate Decisions and never produce a Human Confirmation Event. If the current utterance does not itself name
the Decision proposal, return events: [].

ACTION AND OTHER TYPES
Keep the existing Action policy unchanged: explicit execution intent only. Do not infer Owner or Due.
Use open_item for an unresolved question or issue, and concern for a risk or problem. Prefer a child node under the
current Topic rather than a new Topic for a Concern, Question, Option, or Action.

FEW-SHOT SEMANTIC EXAMPLES
Input: “Aの方がいいと思います” -> one Idea/Option at most; no Decision.
Input: “Aで進めましょう” after alternatives A/B were discussed -> one candidate Decision; no confirmation.
Input: no current Topic, “次に料金について考えましょう” -> a 料金モデル Topic plus topic_focus for that new Topic;
do not add an equivalent Idea or multiple cross-relations.
Input: “料金も後で考える必要があります” while advancing MVP範囲 -> no focus change for 料金.
Input: Topic + two Options -> at most the necessary has_option relations; do not add supports/opposes/related_to
unless explicitly stated.
Input: “それでいきましょう” with no named proposal -> {{"events":[]}}.
"""
    return system_prompt, copy.deepcopy(dict(context))


def build_analyzer_prompt_v5(context: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Return the STT-robust semantic policy while preserving v4's contract.

    v5 is intentionally an additive prompt experiment.  It does not alter the
    provider schema, context builder, CandidateEvent conversion, or
    Materializer.  The v4 contract and economy rules remain the first part of
    the instruction; this suffix makes the evidence-quality policy explicit
    for imperfect recorded transcripts.
    """

    base_prompt, payload = build_analyzer_prompt_v4(context)
    system_prompt = base_prompt.replace(
        f"You are Discussion Map Analyzer {PROMPT_VERSION_V4}.",
        f"You are Discussion Map Analyzer {PROMPT_VERSION_V5}.",
        1,
    )
    system_prompt += f"""

STT EVIDENCE POLICY ({PROMPT_VERSION_V5})
Treat the transcript as imperfect speech-recognition evidence. Do not infer a
stronger intent than the words explicitly support. A grammatical error,
technical-term substitution, missing particle, or incomplete fragment is not
permission to repair the transcript from what you think the speaker meant.
Use only the meaning explicitly supported by the current utterance and the
canonical context. If the intended meaning is not sufficiently clear, return
{{"events":[]}} rather than inventing a stronger event.

Never perform these intent escalations:
- preference -> decision
- suggestion -> action
- question -> decision
- incomplete fragment -> open_item
- agreement -> decision or confirmation
The Analyzer may detect a candidate decision, but it must never emit a Human
Confirmation event or make a decision confirmed.

DECISION EVIDENCE THRESHOLD
Create a candidate decision only when the current utterance itself provides:
A) a clear selectable option, scope, policy, adoption, or rejection target;
B) clear commitment evidence such as 〜にする, 〜で進める, 〜を採用する,
   〜を外す, 〜は対象外とする, 〜で決める, or 〜に決定する; and
C) wording stronger than a preference, comparison, possibility, question,
   proposal, or impression.
All three must be satisfied. If a commitment phrase is damaged or ambiguous
in the transcript, do not create a decision. Do not use a previous proposal,
agreement-like phrase, or likely intended wording to upgrade the current
utterance to a decision. “〜が良さそう”, “〜でもいい”, “〜かもしれない”,
“〜の方がいいと思う”, “〜という方向もある”, and “〜を検討したい” are
not candidate decisions. “それでいきましょう” without a named target in
the current utterance is events:[]; it is not confirmation.

ACTION EVIDENCE AND RECOVERY
Keep Action precision safety, but recover short Actions when the current
utterance has explicit execution or request intent. Examples that may be an
Action when their target is clear are “確認します”, “整理します”, “私がやります”,
“次回までに作ります”, “〜を作ります”, “〜を確認してください”, and
“〜お願いします”. Shortness alone is not a reason to return no events.
“〜した方がいい”, “〜できるといい”, “〜を検討したい”, “〜かもしれない”,
and “〜する必要がありそう” remain non-Actions. Do not infer an owner or
due date: set each to null unless the current transcript explicitly states it.
Do not turn a malformed fragment into an Action by guessing a missing verb.

OPEN ITEM AND FRAGMENT SAFETY
Create an open_item only for a substantive unresolved question or issue that
is understandable from the current utterance. An incomplete sentence,
filler, isolated agreement, or STT-looking fragment with an unknown target is
not automatically an open_item; prefer events:[]. Preserve the evidence in
the surrounding application, but do not put unsupported meaning on the Map.

EXISTING TOPIC ROBUSTNESS
If a technical term has a light lexical variation but the current utterance
clearly refers to an existing Topic shown in relevant_nodes, use that existing
Node ID. Do not invent a synonym Topic. If the term could refer to more than
one existing node, do not guess; return no focus or no new Topic. This is
semantic identity matching, not free-form transcript correction.

KEEP V4 ECONOMY RULES
Keep the v4 defaults of 0-2 new Nodes and 0-2 new Relations per utterance,
avoid redundant Ideas, prefer contains/has_option, and do not use related_to
as a fallback. Do not create a node merely because the STT transcript is
long, awkward, or contains a technical noun.

V5 CHECK EXAMPLES
Input: “スマホ類はMVPから外す案でどうでしょう” -> option or open_item,
not a candidate decision, because it is a proposal/question rather than an
explicit commitment.
Input: “オンライン会議連携はMVPから外しましょう” -> one candidate
decision for that explicit scope choice.
Input: “それでいきましょう” -> events:[] unless the current utterance
itself names a substantive target; never a Human Confirmation event.
Input: “確認します” with a clear current-topic target -> one Action; do not
skip it because it is short.
Input: “確認した方がいいかもしれません” -> not an Action.
Input: “ただ、同遺跡から文字が読めないのは心配です” -> create a
Concern only if the risk is clear; do not invent the malformed noun's meaning.
Input: an unfinished or targetless fragment such as “なので…” -> events:[].
"""
    return system_prompt, payload


def build_analyzer_prompt_v6(context: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Opt-in working hypothesis: sparse, Evidence-backed Node provenance."""

    system_prompt, payload = build_analyzer_prompt_v5(context)
    system_prompt = system_prompt.replace(PROMPT_VERSION_V5, PROMPT_VERSION_V6)
    system_prompt = system_prompt.replace(
        "Allowed relation_type values are exactly: contains, has_option, supports, opposes, related_to.",
        "For this hypothesis, emit relation_type only from: contains, has_option, supports, opposes, discussion_provenance.",
    )
    system_prompt = system_prompt.replace(
        "related_to connects two non-archived nodes. Do not invent other relations.",
        "Legacy related_to remains readable for replay but must not be newly emitted. Do not invent other relations.",
    )
    system_prompt = system_prompt.replace(
        "Use supports, opposes, or related_to only when the relation is explicit and important.",
        "Use supports, opposes, or discussion_provenance only when the relation is explicit and important.",
    )
    system_prompt += """

DISCUSSION PROVENANCE — WORKING HYPOTHESIS
Use discussion_provenance only between non-Topic Nodes when the current utterance
clearly establishes that target B arose from discussion of source A. It records
discussion origin, NOT physical causation, proof, support, opposition, resolution,
or mere order/similarity. Prefer no edge to a speculative edge. A shared Topic,
adjacent utterances, a Topic Return, or sibling Options do not establish an edge.
Do not emit redundant transitive shortcuts (Issue→Decision when Issue→Option→Decision
already explains the path) unless current Evidence separately establishes the direct link.
Multiple parents are allowed only when each is explicitly supported. Never add a
provenance cycle. Use source_evidence_ids from the CURRENT utterance that actually
establishes the connection, including for late links between existing Nodes.
The relation never creates/confirms a Decision, resolves an Open Item, creates an
Action, or supplies Owner/Due. supports/opposes remain distinct argument relations.
Do not use related_to as a substitute for uncertain provenance.
"""
    return system_prompt, payload


def build_analyzer_prompt_v7(context: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """One versioned, general-purpose correction of the v6 acceptance defects."""
    system_prompt, payload = build_analyzer_prompt_v6(context)
    system_prompt = system_prompt.replace(PROMPT_VERSION_V6, PROMPT_VERSION_V7)
    system_prompt += """

CORRECTABLE WORKING GRAPH — V7
The Graph is a working interpretation that participants can correct. Prefer
useful, Evidence-defensible discussion provenance when a point is introduced
as a response, specific development, open question, chosen option, or concrete
follow-up to an existing point. The edge means discussion origin only, not
physical causality or resolution. Never connect mere temporal neighbors,
sibling alternatives, or unrelated points to fill the map. Rejected Human
relations in the supplied Event history must not be recreated from old Evidence;
new utterances may provide genuinely new support.

Decision procedure is NOT an Action. A chair saying a proposal is a Decision
candidate or that they will confirm it if nobody objects does not assign
operational work. Represent an explicit candidate Decision as a candidate
Decision Node; only a Human confirmation event can confirm it. Do not invent
Action, Owner, Due, consensus, negation reversal, or stronger certainty.
"""
    return system_prompt, payload


def build_analyzer_prompt_v8(context: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Make an explicitly named decision candidate distinct from commitment."""
    system_prompt, payload = build_analyzer_prompt_v7(context)
    system_prompt = system_prompt.replace(PROMPT_VERSION_V7, PROMPT_VERSION_V8)
    system_prompt += """

EXPLICIT DECISION CANDIDATE — V8
The earlier commitment threshold applies to inferring a choice from ordinary
discussion. A participant can instead explicitly name a *candidate decision*
without committing to or confirming it. If the CURRENT utterance explicitly
says that a concrete named option/policy is being put forward as a decision
candidate (e.g. 「この方針を決定候補として出します」 with the policy named in the
same utterance), emit one decision Node with candidate status. It is not
confirmed; conditional future checking or lack of objection is not consent.
Do not convert procedural 「確認します」 or 「異論がなければ確認します」 into an
Action. Do not create a candidate from a mere option, question, preference,
or anaphoric 「それで」 without an explicit named target in the current speech.
Where a matching Option already exists, use discussion_provenance from the
Option to the candidate Decision only if this speech identifies that Option
as the candidate's origin. No automatic Human confirmation event.
"""
    return system_prompt, payload


def build_analyzer_prompt_v9(context: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Remove legacy Topic-edge precedence without lowering semantic safety."""
    system_prompt, payload = build_analyzer_prompt_v8(context)
    system_prompt = system_prompt.replace(PROMPT_VERSION_V8, PROMPT_VERSION_V9)
    system_prompt = system_prompt.replace(
        "Prefer one contains relation for a child under a newly created Topic and has_option for options.",
        "Use contains/has_option for Topic membership, but these do not replace a distinct Evidence-backed Node-to-Node relation.",
    ).replace(
        "When contains is sufficient, do not add cross-relations.",
        "Do not add a semantic Node-to-Node edge merely to duplicate Topic membership.",
    ).replace(
        "avoid redundant Ideas, prefer contains/has_option, and do not use related_to",
        "avoid redundant Ideas, preserve Topic membership and independent semantic edges, and do not use related_to",
    )
    system_prompt += """

SEMANTIC EDGE BALANCE — V9
After choosing a substantive new Node, check its explicit relationship to
existing discussion Nodes in the supplied context. If the current utterance
introduces an Option in response to a stated Issue, gives a reason for an
Option, states a Concern against an Option, names an Option as a candidate
Decision, or assigns concrete follow-up arising from an unresolved issue,
include the precise Evidence-backed Node-to-Node relation in this SAME output.
Topic contains/has_option may coexist; it is not the answer to this check.
Do not add an edge when the origin/argument is only guessed from adjacency,
shared Topic, similar vocabulary, or an inferred real-world causal link.
Independent roots and uncertainty remain unconnected. No transitive shortcuts.
"""
    return system_prompt, payload


def build_analyzer_prompt_v10(context: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Distinguish meeting-time agenda from work that follows the meeting."""
    system_prompt, payload = build_analyzer_prompt_v9(context)
    system_prompt = system_prompt.replace(PROMPT_VERSION_V9, PROMPT_VERSION_V10)
    system_prompt += """

ACTION TIME HORIZON — V10
An Action is work to execute after this meeting, not an agenda item or activity
to be done during the present meeting. Distinguish 「本日の会議では点検結果を確認します」
or 「まずここで説明します」 (current meeting process, NOT Action) from
「次回までに点検結果を確認します」 or 「会議後に担当者が調査します」
(post-meeting work, Action). A bare 「確認します」 may be an Action only when
context clearly identifies a post-meeting follow-up; otherwise do not create
one. Do not infer Owner or Due. Do not suppress a separately explicit
post-meeting Action merely because the utterance also describes today's agenda.
"""
    return system_prompt, payload


class RealAnalyzer:
    """Provider-backed Analyzer with the M6 CandidateEvent boundary."""

    def __init__(
        self,
        *,
        provider: Provider,
        schema_validator: SchemaValidator,
        meeting_goal: str | None = None,
        context_builder: AnalysisContextBuilder | None = None,
        prompt_version: str = PROMPT_VERSION,
        output_schema_version: str = "v1",
    ) -> None:
        self.provider = provider
        self.schema_validator = schema_validator
        self.meeting_goal = meeting_goal
        self.context_builder = context_builder or AnalysisContextBuilder()
        self.prompt_version = prompt_version
        self.output_schema_version = output_schema_version
        if output_schema_version not in {"v1", "v2", "v3"}:
            raise ValueError("Unsupported Analyzer output schema version")
        self.run_history: list[dict[str, Any]] = []
        self.last_trace: dict[str, Any] | None = None

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

    @property
    def provider_name(self) -> str:
        return self.provider.provider_name

    @property
    def model(self) -> str:
        return self.provider.model

    def analyze(
        self,
        utterance: Mapping[str, Any],
        current_graph: Mapping[str, Any],
        recent_events: Iterable[dict[str, Any]],
    ) -> list[CandidateEvent]:
        started = time.perf_counter()
        context = self.context_builder.build(
            utterance=utterance,
            current_graph=current_graph,
            recent_events=recent_events,
            meeting_goal=self.meeting_goal,
        )
        if self.prompt_version in {PROMPT_VERSION_V6, PROMPT_VERSION_V7, PROMPT_VERSION_V8, PROMPT_VERSION_V9, PROMPT_VERSION_V10}:
            context = self.context_builder.augment_for_semantic_relations(context, current_graph, utterance)
        context_measure = self.context_builder.measure(context)
        system_prompt, user_payload = build_analyzer_prompt(context, prompt_version=self.prompt_version)
        if self.output_schema_version == "v3":
            system_prompt += DISPLAY_INSTRUCTION
        base = {
            "utterance_id": utterance.get("id"),
            "session_id": utterance.get("session_id"),
            "provider": self.provider_name,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "output_schema_version": self.output_schema_version,
            "presentation_policy": POLICY_VERSION if self.output_schema_version == "v3" else None,
            **context_measure,
            "raw_output": None,
            "validation_error": None,
            "critical_errors": [],
            "events_emitted": 0,
            "status": "failed",
            "latency_ms": None,
            "usage": {
                "prompt_tokens": None,
                "completion_tokens": None,
                "reasoning_tokens": None,
                "total_tokens": None,
            },
            "cost_usd": None,
        }
        try:
            response = self.provider.complete_json(
                system_prompt=system_prompt,
                user_payload=user_payload,
                response_schema=self.schema_validator.analyzer_output_schema_for(self.output_schema_version),
            )
        except ProviderFailure as exc:
            base["validation_error"] = {"code": exc.code, "message": exc.message}
            base["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
            self._finish_trace(base)
            return []
        except Exception as exc:  # Provider failures must not corrupt the Graph.
            base["validation_error"] = {"code": "provider_failure", "message": str(exc)}
            base["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
            self._finish_trace(base)
            return []

        base["raw_output"] = response.raw_text
        base["latency_ms"] = round(response.latency_ms, 3)
        base["usage"] = response.usage_dict()
        base["cost_usd"] = response.cost_usd
        # Conversion-time safety diagnostics are attached to this run record.
        # They are not part of the canonical Event or Graph state.
        self.last_trace = base
        try:
            output = copy.deepcopy(response.output)
            # Presentation errors never reject otherwise valid Canonical intents.
            # Strict provider v3 requires nullable keys; old/malformed hints from
            # compatible providers are normalized locally for graceful fallback.
            raw_hints = []
            if self.output_schema_version == "v3" and isinstance(output, dict):
                for intent in output.get("events", []):
                    if isinstance(intent, dict) and intent.get("kind") == "node":
                        raw_hints.append(intent.get("display_label"))
                        intent["display_label"] = None
            self.schema_validator.validate_analyzer_output(output, version=self.output_schema_version)
            if self.output_schema_version == "v3":
                for intent, hint in zip([i for i in output["events"] if i.get("kind") == "node"], raw_hints):
                    intent["display_label"] = hint
            visible_ids = ({node["id"] for node in context["relevant_nodes"]}
                           if self.prompt_version in {PROMPT_VERSION_V6, PROMPT_VERSION_V7, PROMPT_VERSION_V8, PROMPT_VERSION_V9, PROMPT_VERSION_V10} else None)
            candidates = self._to_candidates(output, utterance, current_graph,
                                             visible_node_ids=visible_ids,
                                             recent_events=recent_events)
            for candidate in candidates:
                # Sequence is a temporary validation placeholder.  The replay
                # boundary replaces it with the canonical global sequence.
                self.schema_validator.validate_event(candidate.to_event(1))
        except PrototypeError as exc:
            base["validation_error"] = exc.as_dict()
            self._finish_trace(base)
            return []
        except (TypeError, ValueError, KeyError) as exc:
            base["validation_error"] = {"code": "output_conversion_failed", "message": str(exc)}
            self._finish_trace(base)
            return []

        base["events_emitted"] = len(candidates)
        base["status"] = "success" if candidates else "noop"
        self._finish_trace(base)
        return candidates

    def _finish_trace(self, trace: dict[str, Any]) -> None:
        trace["critical_errors"] = list(trace.get("critical_errors", []))
        trace["total_elapsed_ms"] = trace.get("latency_ms")
        self.last_trace = copy.deepcopy(trace)
        self.run_history.append(copy.deepcopy(trace))

    def _to_candidates(
        self,
        output: Mapping[str, Any],
        utterance: Mapping[str, Any],
        graph: Mapping[str, Any],
        *, visible_node_ids: set[str] | None = None,
        recent_events: Iterable[dict[str, Any]] = (),
    ) -> list[CandidateEvent]:
        intents = list(output.get("events", []))
        evidence_ids = set(utterance.get("evidence_ids", []))
        text = str(utterance.get("text", ""))
        trace = self.last_trace if self.last_trace is not None else None

        # The live Utterance and its Evidence use related but distinct IDs.
        # Some otherwise valid provider outputs prepend the Evidence prefix to
        # the *Utterance* ID. Resolve only that exact, unambiguous live alias;
        # every other unknown reference remains a hard validation error.
        live_alias = f"live-evidence:{utterance.get('id', '')}"
        canonical_live_id = f"live-evidence:{utterance.get('session_id', '')}:{utterance.get('sequence', '')}"
        if (utterance.get('id') == f"live-utterance:{utterance.get('session_id', '')}:{utterance.get('sequence', '')}"
                and evidence_ids == {canonical_live_id}):
            for intent in intents:
                source_ids = intent.get("source_evidence_ids", [])
                if live_alias in source_ids:
                    intent["source_evidence_ids"] = [canonical_live_id if value == live_alias else value
                                                     for value in source_ids]
                    if trace is not None:
                        trace["live_evidence_alias_resolved"] = trace.get("live_evidence_alias_resolved", 0) + 1

        # Validate every evidence reference before any candidate is returned.
        for intent in intents:
            missing = set(intent.get("source_evidence_ids", [])) - evidence_ids
            if missing:
                raise PrototypeError(
                    "evidence_reference_invalid",
                    f"Analyzer output references Evidence outside the current Utterance: {sorted(missing)}",
                )

        node_intents = [intent for intent in intents if intent.get("kind") == "node"]
        node_refs: dict[int, str | None] = {}
        candidates: list[CandidateEvent] = []
        next_candidate_index = 1
        session_id = str(utterance["session_id"])
        utterance_id = str(utterance["id"])
        occurred_at = str(utterance["ended_at"])

        def candidate(event_type: str, payload: dict[str, Any], source_ids: Iterable[str], presentation: dict[str, Any] | None = None) -> CandidateEvent:
            nonlocal next_candidate_index
            event_id = f"real:{session_id}:{utterance_id}:{next_candidate_index:02d}"
            next_candidate_index += 1
            result = CandidateEvent(
                event_id=event_id,
                session_id=session_id,
                event_type=event_type,
                occurred_at=occurred_at,
                source_evidence_ids=tuple(source_ids),
                payload=payload,
                presentation=presentation,
            )
            candidates.append(result)
            return result

        # Allocate references in a first pass so relations can refer to nodes
        # that appear later in the same provider response.
        for index, intent in enumerate(node_intents):
            node_type = intent["node_type"]
            label = intent["label"]
            existing_id = intent.get("existing_node_id")
            if existing_id:
                node = self._node(graph, existing_id)
                if node is None or node.get("type") != node_type or node.get("status") == "archived":
                    node_refs[index] = None
                    self._critical("invalid_existing_node_reference", trace)
                    continue
                node_refs[index] = existing_id
                continue

            duplicate_topic = self._find_duplicate_topic(graph, label)
            if node_type == "topic" and duplicate_topic is not None:
                node_refs[index] = duplicate_topic["id"]
                self._critical("duplicate_topic_prevented", trace)
                continue

            source_ids = intent["source_evidence_ids"]
            if node_type == "action":
                if not self._explicit_action(text):
                    node_refs[index] = None
                    self._critical("false_action_rejected", trace)
                    continue
                action = intent["action"]
                if not self._explicit_value(action.get("owner"), text) or not self._explicit_value(action.get("due_date"), text):
                    node_refs[index] = None
                    self._critical("inferred_action_metadata_rejected", trace)
                    continue
                payload = {
                    "node_type": node_type,
                    "label": label,
                    "action": {
                        "owner": action.get("owner"),
                        "due_date": action.get("due_date"),
                    },
                }
            else:
                payload = {"node_type": node_type, "label": label}
            event = candidate("node_detected", payload, source_ids,
                              {"display_label": intent.get("display_label")} if self.output_schema_version == "v3" else None)
            node_refs[index] = f"node:{session_id}:{event.event_id}"

        # Human commands are not part of the provider schema, but keep this
        # guard in case a compatible provider ignores the requested format.
        for intent in intents:
            event_type = intent.get("event_type")
            if event_type in HUMAN_EVENT_TYPES:
                self._critical(f"human_event_rejected:{event_type}", trace)

        for intent in intents:
            kind = intent.get("kind")
            if kind == "relation":
                if visible_node_ids is not None and any(
                    ref.get("existing_node_id") not in visible_node_ids
                    for ref in (intent["source"], intent["target"])
                    if ref.get("existing_node_id")
                ):
                    self._critical("relation_reference_not_in_context", trace)
                    continue
                source_id = self._resolve_ref(intent["source"], node_refs, graph, node_intents)
                target_id = self._resolve_ref(intent["target"], node_refs, graph, node_intents)
                if source_id is None or target_id is None:
                    self._critical("relation_reference_unresolved", trace)
                    continue
                source = self._node(graph, source_id) or self._node_from_candidates(candidates, source_id)
                target = self._node(graph, target_id) or self._node_from_candidates(candidates, target_id)
                if source is None or target is None:
                    self._critical("relation_reference_missing", trace)
                    continue
                relation_type = intent["relation_type"]
                relation_key = (source_id, target_id, relation_type)
                removal = next((event for event in reversed(list(recent_events))
                                if event.get("event_type") == "correct_relation"
                                and event["payload"].get("old_relation") is not None
                                and (event["payload"]["old_relation"]["source_node_id"],
                                     event["payload"]["old_relation"]["target_node_id"],
                                     event["payload"]["old_relation"]["relation_type"]) == relation_key), None)
                if removal is not None and utterance.get("sequence", 0) <= removal["payload"]["evidence_sequence_at_correction"]:
                    self._critical("human_relation_correction_respected", trace, critical=False)
                    continue
                if self.prompt_version not in {PROMPT_VERSION_V6, PROMPT_VERSION_V7, PROMPT_VERSION_V8, PROMPT_VERSION_V9, PROMPT_VERSION_V10} and relation_type == "discussion_provenance":
                    self._critical("hypothesis_relation_not_enabled", trace)
                    continue
                if self.prompt_version in {PROMPT_VERSION_V6, PROMPT_VERSION_V7, PROMPT_VERSION_V8, PROMPT_VERSION_V9, PROMPT_VERSION_V10} and relation_type == "related_to":
                    self._critical("legacy_related_to_rejected", trace)
                    continue
                if (self.prompt_version in {PROMPT_VERSION_V9, PROMPT_VERSION_V10} and relation_type == "opposes"
                        and not self._explicit_opposition(text)):
                    self._critical("weak_opposition_rejected", trace, critical=False)
                    continue
                allowed_source, allowed_target = RELATION_MATRIX[relation_type]
                if source["type"] not in allowed_source or target["type"] not in allowed_target:
                    self._critical("invalid_relation_rejected", trace)
                    continue
                if relation_type == "discussion_provenance":
                    if not intent["source_evidence_ids"] or source_id == target_id:
                        self._critical("unsupported_provenance_rejected", trace)
                        continue
                    accepted_edges = list(graph.get("edges", [])) + [
                        {"type": c.payload["relation_type"],
                         "source_node_id": c.payload["source_node_id"],
                         "target_node_id": c.payload["target_node_id"]}
                        for c in candidates if c.event_type == "relation_detected"
                    ]
                    if GraphMaterializer._provenance_reaches(accepted_edges, target_id, source_id):
                        self._critical("provenance_cycle_rejected", trace)
                        continue
                candidate(
                    "relation_detected",
                    {
                        "source_node_id": source_id,
                        "target_node_id": target_id,
                        "relation_type": relation_type,
                    },
                    intent["source_evidence_ids"],
                )
            elif kind == "topic_focus":
                if graph.get("current_topic", {}).get("mode") == "human_corrected":
                    self._critical("human_topic_override_respected", trace, critical=False)
                    continue
                topic_id = self._resolve_ref(intent["topic"], node_refs, graph, node_intents)
                topic = self._node(graph, topic_id) if topic_id else None
                if topic is None and topic_id:
                    topic = self._node_from_candidates(candidates, topic_id)
                if topic is None or topic.get("type") != "topic" or topic.get("status") != "active":
                    self._critical("invalid_topic_focus_rejected", trace)
                    continue
                if topic_id == graph.get("current_topic", {}).get("primary_topic_id"):
                    continue
                payload: dict[str, Any] = {
                    "topic_id": topic_id,
                    "previous_topic_id": graph.get("current_topic", {}).get("primary_topic_id"),
                }
                if intent.get("confidence") is not None:
                    payload["confidence"] = intent["confidence"]
                candidate("topic_focus_changed", payload, intent["source_evidence_ids"])

        return candidates

    @staticmethod
    def _node(graph: Mapping[str, Any], node_id: str | None) -> dict[str, Any] | None:
        if not node_id:
            return None
        return next((node for node in graph.get("nodes", []) if node.get("id") == node_id), None)

    @staticmethod
    def _node_from_candidates(candidates: Iterable[CandidateEvent], node_id: str) -> dict[str, Any] | None:
        for event in candidates:
            if event.event_type != "node_detected":
                continue
            expected = f"node:{event.session_id}:{event.event_id}"
            if expected == node_id:
                payload = event.payload
                return {"id": node_id, "type": payload["node_type"], "status": "candidate" if payload["node_type"] == "decision" else "active"}
        return None

    @staticmethod
    def _explicit_opposition(text: str) -> bool:
        """A drawback alone is not an argument that opposes an option."""
        return bool(re.search(
            r"反対|賛成できない|支持できない|採用できない|この案では.{0,24}(?:できない|満たせない|成立しない)|"
            r"(?:案|方法|方針).{0,16}(?:却下|除外|対象外|不適切)", text,
        ))

    @staticmethod
    def _resolve_ref(
        ref: Mapping[str, Any],
        node_refs: Mapping[int, str | None],
        graph: Mapping[str, Any],
        node_intents: list[Mapping[str, Any]],
    ) -> str | None:
        existing_id = ref.get("existing_node_id")
        if existing_id:
            return existing_id if RealAnalyzer._node(graph, existing_id) else None
        index = ref.get("new_node_index")
        if not isinstance(index, int) or index < 0 or index >= len(node_intents):
            return None
        return node_refs.get(index)

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[\s　。、・:：「」『』（）()\-—]+", "", value).lower()

    def _find_duplicate_topic(self, graph: Mapping[str, Any], label: str) -> dict[str, Any] | None:
        normalized = self._normalize(label)
        return next(
            (
                node
                for node in graph.get("nodes", [])
                if node.get("type") == "topic"
                and node.get("status") == "active"
                and self._normalize(str(node.get("label", ""))) == normalized
            ),
            None,
        )

    @staticmethod
    def _explicit_action(text: str) -> bool:
        if "決定候補" in text or ("異論がなければ" in text and "確認します" in text):
            return False
        return bool(any(marker in text for marker in EXPLICIT_ACTION_MARKERS) and not any(marker in text for marker in ACTION_SUGGESTION_MARKERS))

    @staticmethod
    def _explicit_value(value: Any, text: str) -> bool:
        if value is None:
            return True
        if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            year, month, day = (int(part) for part in value.split("-"))
            if re.search(rf"{year}年0?{month}月0?{day}日", text):
                return True
        return str(value) in text

    @staticmethod
    def _critical(code: str, trace: dict[str, Any] | None, *, critical: bool = True) -> None:
        if trace is not None and critical:
            trace.setdefault("critical_errors", []).append(code)


def provider_configuration_summary(provider: Provider) -> dict[str, Any]:
    """Return safe provider metadata without exposing credentials."""

    configured = getattr(provider, "configured", None)
    return {
        "provider": provider.provider_name,
        "model": provider.model,
        "reasoning_effort": getattr(provider, "reasoning_effort", None),
        "configured": configured if isinstance(configured, bool) else None,
    }
