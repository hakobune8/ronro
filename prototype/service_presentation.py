"""Validate non-Canonical presentation deltas before durable acceptance."""

from __future__ import annotations

import copy
from typing import Any, Mapping, Sequence

from .display_labels import POLICY_VERSION, VERSION, content_hash, validate_label
from .replay import ReplayResult
from .service_errors import ServiceStoreError


def validate_presentation_delta(
    result: ReplayResult,
    events: Sequence[dict[str, Any]],
    hints: Mapping[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    if hints is None:
        return {}
    if not isinstance(hints, Mapping):
        raise ServiceStoreError("presentation_invalid", "Presentation hints must be a mapping")
    created = {
        f"node:{event['session_id']}:{event['event_id']}": event
        for event in events if event.get("event_type") == "node_detected"
    }
    nodes = {node["id"]: node for node in result.state["graph"]["nodes"]}
    accepted: dict[str, dict[str, Any]] = {}
    for node_id, record in hints.items():
        event = created.get(node_id)
        node = nodes.get(node_id)
        if event is None or node is None or not isinstance(record, dict):
            raise ServiceStoreError("presentation_invalid", "Hint must belong to a newly accepted Node")
        if (record.get("version") != VERSION or record.get("policy") != POLICY_VERSION
                or record.get("event_id") != event["event_id"]
                or record.get("sequence") != event["sequence"]
                or record.get("content_hash") != content_hash(node)):
            raise ServiceStoreError("presentation_invalid", "Hint identity does not match Canonical Node")
        label = record.get("display_label")
        if label is not None:
            validated, _ = validate_label(label, node)
            if validated != label:
                raise ServiceStoreError("presentation_invalid", "Hint failed display-label validation")
        reason = record.get("reason")
        if not isinstance(reason, str) or len(reason) > 80:
            raise ServiceStoreError("presentation_invalid", "Hint reason is invalid")
        if set(record) != {"version", "policy", "event_id", "sequence", "content_hash", "display_label", "reason"}:
            raise ServiceStoreError("presentation_invalid", "Hint has unsupported fields")
        accepted[node_id] = copy.deepcopy(record)
    return accepted
