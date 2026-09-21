"""Pure-ish deterministic Graph Materializer for Prototype 1."""

from __future__ import annotations

import copy
from typing import Any, Iterable

from .errors import MaterializerError
from .schema import SchemaValidator


RELATION_MATRIX: dict[str, tuple[set[str], set[str]]] = {
    "contains": (
        {"topic"},
        {"idea", "option", "concern", "open_item", "decision", "action"},
    ),
    "has_option": ({"topic"}, {"option"}),
    "supports": ({"idea", "option"}, {"idea", "option", "decision"}),
    "opposes": (
        {"idea", "option", "concern"},
        {"idea", "option", "decision"},
    ),
    "related_to": (
        {"topic", "idea", "option", "concern", "open_item", "decision", "action"},
        {"topic", "idea", "option", "concern", "open_item", "decision", "action"},
    ),
}


def initial_state(
    session_id: str,
    evidence: Iterable[dict[str, Any]],
    utterances: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Create revision 0 without using a clock or generated identifier."""

    return {
        "session": {
            "id": session_id,
            "title": None,
            "goal": None,
            "status": "created",
            "created_at": None,
            "started_at": None,
            "ended_at": None,
            "graph_revision": 0,
        },
        "evidence": copy.deepcopy(list(evidence)),
        "utterances": copy.deepcopy(list(utterances)),
        "graph": {
            "session_id": session_id,
            "revision": 0,
            "last_event_sequence": 0,
            "nodes": [],
            "edges": [],
            "current_topic": {
                "primary_topic_id": None,
                "mode": "derived",
                "source_event_ids": [],
            },
        },
    }


class GraphMaterializer:
    """Apply ordered Events without LLM, time, randomness, or UI dependencies."""

    def __init__(self, schema_validator: SchemaValidator) -> None:
        self.schema_validator = schema_validator

    def apply(
        self,
        state: dict[str, Any],
        event: dict[str, Any],
        history: Iterable[dict[str, Any]] = (),
    ) -> dict[str, Any]:
        """Return a new state or raise, leaving the input state untouched."""

        self.schema_validator.validate_event(event)
        prior_events = list(history)
        self._validate_envelope(state, event, prior_events)
        next_state = copy.deepcopy(state)

        self._dispatch(next_state, event, prior_events)

        next_revision = state["graph"]["revision"] + 1
        next_state["graph"]["revision"] = next_revision
        next_state["graph"]["last_event_sequence"] = event["sequence"]
        next_state["session"]["graph_revision"] = next_revision
        return next_state

    def _validate_envelope(
        self,
        state: dict[str, Any],
        event: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> None:
        event_id = event["event_id"]
        sequence = event["sequence"]
        graph = state["graph"]
        if event["session_id"] != graph["session_id"]:
            raise MaterializerError(
                "session_mismatch",
                f"Expected session {graph['session_id']}, got {event['session_id']}",
                event_id=event_id,
                sequence=sequence,
            )
        if any(previous["event_id"] == event_id for previous in history):
            raise MaterializerError(
                "duplicate_event_id",
                f"Event ID {event_id} already exists in history",
                event_id=event_id,
                sequence=sequence,
            )
        expected_sequence = graph["last_event_sequence"] + 1
        if sequence < expected_sequence:
            raise MaterializerError(
                "duplicate_sequence",
                f"Expected sequence {expected_sequence}, got {sequence}",
                event_id=event_id,
                sequence=sequence,
            )
        if sequence > expected_sequence:
            raise MaterializerError(
                "sequence_gap",
                f"Expected sequence {expected_sequence}, got {sequence}",
                event_id=event_id,
                sequence=sequence,
            )
        if event["actor"] == "human" and event["expected_revision"] != graph["revision"]:
            raise MaterializerError(
                "revision_mismatch",
                f"Expected Graph revision {graph['revision']}, got {event['expected_revision']}",
                event_id=event_id,
                sequence=sequence,
            )
        evidence_ids = {item["id"] for item in state["evidence"]}
        missing = set(event["source_evidence_ids"]) - evidence_ids
        if missing:
            raise MaterializerError(
                "missing_reference",
                f"Event references missing Evidence: {sorted(missing)}",
                event_id=event_id,
                sequence=sequence,
            )

    def _dispatch(
        self,
        state: dict[str, Any],
        event: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> None:
        handlers = {
            "session_created": self._session_created,
            "session_started": self._session_started,
            "session_finalizing": self._session_finalizing,
            "session_ended": self._session_ended,
            "node_detected": self._node_detected,
            "relation_detected": self._relation_detected,
            "topic_focus_changed": self._topic_focus_changed,
            "confirm_decision": self._confirm_decision,
            "revoke_decision": self._revoke_decision,
            "resolve_open_item": self._resolve_open_item,
            "reopen_open_item": self._reopen_open_item,
            "rename_node": self._rename_node,
            "archive_node": self._archive_node,
            "merge_nodes": self._merge_nodes,
            "move_to_parking_lot": self._move_to_parking_lot,
            "restore_from_parking_lot": self._restore_from_parking_lot,
            "update_action": self._update_action,
            "set_current_topic": self._set_current_topic,
            "undo_last_correction": self._undo_last_correction,
        }
        handler = handlers.get(event["event_type"])
        if handler is None:  # Schema enum should make this unreachable.
            raise MaterializerError(
                "schema_invalid",
                f"Unsupported event type {event['event_type']}",
                event_id=event["event_id"],
                sequence=event["sequence"],
            )
        handler(state, event, history)

    @staticmethod
    def _event_context(event: dict[str, Any]) -> dict[str, Any]:
        return {
            "event_id": event["event_id"],
            "sequence": event["sequence"],
        }

    def _error(self, code: str, message: str, event: dict[str, Any]) -> MaterializerError:
        return MaterializerError(code, message, **self._event_context(event))

    @staticmethod
    def _graph_node(state: dict[str, Any], node_id: str) -> dict[str, Any] | None:
        return next((node for node in state["graph"]["nodes"] if node["id"] == node_id), None)

    def _require_node(self, state: dict[str, Any], node_id: str, event: dict[str, Any]) -> dict[str, Any]:
        node = self._graph_node(state, node_id)
        if node is None:
            raise self._error("missing_reference", f"Node {node_id} does not exist", event)
        return node

    @staticmethod
    def _append_unique(items: list[str], value: str) -> None:
        if value not in items:
            items.append(value)

    def _touch_node(self, node: dict[str, Any], event: dict[str, Any]) -> None:
        self._append_unique(node["source_event_ids"], event["event_id"])
        for evidence_id in event["source_evidence_ids"]:
            self._append_unique(node["evidence_ids"], evidence_id)
        node["updated_at"] = event["occurred_at"]

    @staticmethod
    def _clear_current_topic(state: dict[str, Any], event_id: str) -> None:
        state["graph"]["current_topic"] = {
            "primary_topic_id": None,
            "mode": "derived",
            "source_event_ids": [event_id],
        }

    def _session_created(self, state: dict[str, Any], event: dict[str, Any], _: list[dict[str, Any]]) -> None:
        session = state["session"]
        if session["created_at"] is not None or session["status"] != "created":
            raise self._error("invalid_transition", "Session is already created", event)
        session["title"] = event["payload"]["title"]
        session["goal"] = event["payload"]["goal"]
        session["created_at"] = event["occurred_at"]

    def _session_started(self, state: dict[str, Any], event: dict[str, Any], _: list[dict[str, Any]]) -> None:
        session = state["session"]
        if session["status"] != "created":
            raise self._error("invalid_transition", "Session must be created before it starts", event)
        session["status"] = "active"
        session["started_at"] = event["occurred_at"]

    def _session_finalizing(self, state: dict[str, Any], event: dict[str, Any], _: list[dict[str, Any]]) -> None:
        session = state["session"]
        if session["status"] != "active":
            raise self._error("invalid_transition", "Only an active Session can finalize", event)
        session["status"] = "finalizing"

    def _session_ended(self, state: dict[str, Any], event: dict[str, Any], _: list[dict[str, Any]]) -> None:
        session = state["session"]
        if session["status"] != "finalizing":
            raise self._error("invalid_transition", "Session must be finalizing before it ends", event)
        if event["payload"]["final_graph_revision"] != state["graph"]["revision"]:
            raise self._error("revision_mismatch", "Final graph revision does not match current revision", event)
        session["status"] = "ended"
        session["ended_at"] = event["occurred_at"]

    def _node_detected(self, state: dict[str, Any], event: dict[str, Any], _: list[dict[str, Any]]) -> None:
        payload = event["payload"]
        node_id = f"node:{event['session_id']}:{event['event_id']}"
        if self._graph_node(state, node_id) is not None:
            raise self._error("duplicate_event_id", f"Node {node_id} already exists", event)
        node: dict[str, Any] = {
            "id": node_id,
            "session_id": event["session_id"],
            "type": payload["node_type"],
            "label": payload["label"],
            "status": "candidate" if payload["node_type"] == "decision" else "active",
            "created_at": event["occurred_at"],
            "updated_at": event["occurred_at"],
            "source_event_ids": [event["event_id"]],
            "evidence_ids": list(event["source_evidence_ids"]),
        }
        if payload["node_type"] == "action":
            details = payload["action"]
            node["action"] = {
                "description": payload["label"],
                "owner": details["owner"],
                "due_date": details["due_date"],
                "status": "open",
            }
        state["graph"]["nodes"].append(node)

    def _relation_detected(self, state: dict[str, Any], event: dict[str, Any], _: list[dict[str, Any]]) -> None:
        payload = event["payload"]
        source = self._require_node(state, payload["source_node_id"], event)
        target = self._require_node(state, payload["target_node_id"], event)
        relation_type = payload["relation_type"]
        if source["id"] == target["id"]:
            raise self._error("unsupported_relation", "A relation cannot target itself", event)
        allowed_source, allowed_target = RELATION_MATRIX[relation_type]
        if source["type"] not in allowed_source or target["type"] not in allowed_target:
            raise self._error(
                "unsupported_relation",
                f"Relation {relation_type} does not allow {source['type']} -> {target['type']}",
                event,
            )
        if source["status"] == "archived" or target["status"] == "archived":
            raise self._error("unsupported_relation", "Archived Nodes cannot receive new Relations", event)
        edge_id = f"edge:{event['session_id']}:{relation_type}:{source['id']}:{target['id']}"
        existing = next((edge for edge in state["graph"]["edges"] if edge["id"] == edge_id), None)
        if existing is not None:
            self._append_unique(existing["source_event_ids"], event["event_id"])
            return
        state["graph"]["edges"].append(
            {
                "id": edge_id,
                "source_node_id": source["id"],
                "target_node_id": target["id"],
                "type": relation_type,
                "source_event_ids": [event["event_id"]],
            }
        )

    def _topic_focus_changed(self, state: dict[str, Any], event: dict[str, Any], _: list[dict[str, Any]]) -> None:
        topic = self._require_node(state, event["payload"]["topic_id"], event)
        if topic["type"] != "topic" or topic["status"] != "active":
            raise self._error("invalid_transition", "Focus requires an active Topic", event)
        current = {
            "primary_topic_id": topic["id"],
            "mode": "derived",
            "source_event_ids": [event["event_id"]],
        }
        if "confidence" in event["payload"]:
            current["confidence"] = event["payload"]["confidence"]
        state["graph"]["current_topic"] = current

    def _confirm_decision(self, state: dict[str, Any], event: dict[str, Any], _: list[dict[str, Any]]) -> None:
        node = self._require_node(state, event["payload"]["decision_node_id"], event)
        if node["type"] != "decision" or node["status"] != "candidate":
            raise self._error("invalid_transition", "Only a candidate Decision can be confirmed", event)
        if event["payload"]["expected_status"] != node["status"]:
            raise self._error("invalid_transition", "Decision expected_status does not match", event)
        node["status"] = "confirmed"
        self._touch_node(node, event)

    def _revoke_decision(self, state: dict[str, Any], event: dict[str, Any], _: list[dict[str, Any]]) -> None:
        node = self._require_node(state, event["payload"]["decision_node_id"], event)
        if node["type"] != "decision" or node["status"] != "confirmed":
            raise self._error("invalid_transition", "Only a confirmed Decision can be revoked", event)
        if event["payload"]["expected_status"] != node["status"]:
            raise self._error("invalid_transition", "Decision expected_status does not match", event)
        node["status"] = "revoked"
        self._touch_node(node, event)

    def _resolve_open_item(self, state: dict[str, Any], event: dict[str, Any], _: list[dict[str, Any]]) -> None:
        node = self._require_node(state, event["payload"]["open_item_node_id"], event)
        if node["type"] != "open_item" or node["status"] != "active":
            raise self._error("invalid_transition", "Only an active Open Item can be resolved", event)
        if event["payload"]["expected_status"] != node["status"]:
            raise self._error("invalid_transition", "Open Item resolve expected_status does not match", event)
        node["status"] = "resolved"
        self._touch_node(node, event)

    def _reopen_open_item(self, state: dict[str, Any], event: dict[str, Any], _: list[dict[str, Any]]) -> None:
        node = self._require_node(state, event["payload"]["open_item_node_id"], event)
        if node["type"] != "open_item" or node["status"] != "resolved":
            raise self._error("invalid_transition", "Only a resolved Open Item can be reopened", event)
        if event["payload"]["expected_status"] != node["status"]:
            raise self._error("invalid_transition", "Open Item reopen expected_status does not match", event)
        node["status"] = "active"
        self._touch_node(node, event)

    def _rename_node(self, state: dict[str, Any], event: dict[str, Any], _: list[dict[str, Any]]) -> None:
        node = self._require_node(state, event["payload"]["node_id"], event)
        if node["status"] == "archived":
            raise self._error("invalid_transition", "Archived Nodes cannot be renamed", event)
        node["label"] = event["payload"]["label"]
        if node["type"] == "action":
            node["action"]["description"] = node["label"]
        self._touch_node(node, event)

    def _archive_node(self, state: dict[str, Any], event: dict[str, Any], _: list[dict[str, Any]]) -> None:
        node = self._require_node(state, event["payload"]["node_id"], event)
        if node["status"] == "archived":
            raise self._error("invalid_transition", "Node is already archived", event)
        node["status"] = "archived"
        self._touch_node(node, event)
        if state["graph"]["current_topic"]["primary_topic_id"] == node["id"]:
            self._clear_current_topic(state, event["event_id"])

    def _merge_nodes(self, state: dict[str, Any], event: dict[str, Any], _: list[dict[str, Any]]) -> None:
        payload = event["payload"]
        source = self._require_node(state, payload["source_node_id"], event)
        target = self._require_node(state, payload["target_node_id"], event)
        if source["id"] == target["id"]:
            raise self._error("unsupported_correction", "A Node cannot be merged into itself", event)
        if source["status"] == "archived" or target["status"] == "archived":
            raise self._error("invalid_transition", "Archived Nodes cannot be merged", event)
        source["status"] = "archived"
        self._touch_node(source, event)
        self._touch_node(target, event)
        self._rewire_edges(state, source["id"], target["id"], event)
        if state["graph"]["current_topic"]["primary_topic_id"] == source["id"]:
            current = state["graph"]["current_topic"]
            current["primary_topic_id"] = target["id"]
            current["mode"] = "derived"
            current.pop("confidence", None)
            current["source_event_ids"] = [event["event_id"]]

    def _rewire_edges(
        self,
        state: dict[str, Any],
        source_node_id: str,
        target_node_id: str,
        event: dict[str, Any],
    ) -> None:
        """Rebuild deterministic Edge IDs after a Human Merge."""

        reindexed: dict[str, dict[str, Any]] = {}
        for original in state["graph"]["edges"]:
            edge = copy.deepcopy(original)
            rewired = False
            if edge["source_node_id"] == source_node_id:
                edge["source_node_id"] = target_node_id
                rewired = True
            if edge["target_node_id"] == source_node_id:
                edge["target_node_id"] = target_node_id
                rewired = True
            if edge["source_node_id"] == edge["target_node_id"]:
                continue
            edge["id"] = (
                f"edge:{state['graph']['session_id']}:{edge['type']}:{edge['source_node_id']}:{edge['target_node_id']}"
            )
            if rewired:
                self._append_unique(edge["source_event_ids"], event["event_id"])
            existing = reindexed.get(edge["id"])
            if existing is None:
                reindexed[edge["id"]] = edge
            else:
                for source_event_id in edge["source_event_ids"]:
                    self._append_unique(existing["source_event_ids"], source_event_id)
        state["graph"]["edges"] = list(reindexed.values())

    def _move_to_parking_lot(self, state: dict[str, Any], event: dict[str, Any], _: list[dict[str, Any]]) -> None:
        node = self._require_node(state, event["payload"]["node_id"], event)
        if node["type"] == "decision":
            raise self._error("invalid_transition", "Decision lifecycle cannot be replaced by Parking status", event)
        if node["status"] == "archived" or node["status"] == "parked":
            raise self._error("invalid_transition", "Only a non-archived active Node can be parked", event)
        node["status"] = "parked"
        self._touch_node(node, event)
        if state["graph"]["current_topic"]["primary_topic_id"] == node["id"]:
            self._clear_current_topic(state, event["event_id"])

    def _restore_from_parking_lot(self, state: dict[str, Any], event: dict[str, Any], _: list[dict[str, Any]]) -> None:
        node = self._require_node(state, event["payload"]["node_id"], event)
        if node["status"] != "parked":
            raise self._error("invalid_transition", "Only a parked Node can be restored", event)
        node["status"] = "active"
        self._touch_node(node, event)

    def _update_action(self, state: dict[str, Any], event: dict[str, Any], _: list[dict[str, Any]]) -> None:
        node = self._require_node(state, event["payload"]["action_node_id"], event)
        if node["type"] != "action":
            raise self._error("invalid_transition", "update_action requires an Action Node", event)
        payload = event["payload"]
        if "description" in payload:
            node["label"] = payload["description"]
            node["action"]["description"] = payload["description"]
        for field in ("owner", "due_date", "status"):
            if field in payload:
                node["action"][field] = payload[field]
        self._touch_node(node, event)

    def _set_current_topic(self, state: dict[str, Any], event: dict[str, Any], _: list[dict[str, Any]]) -> None:
        topic = self._require_node(state, event["payload"]["topic_id"], event)
        if topic["type"] != "topic" or topic["status"] != "active":
            raise self._error("invalid_transition", "Human Current Topic requires an active Topic", event)
        self._touch_node(topic, event)
        state["graph"]["current_topic"] = {
            "primary_topic_id": topic["id"],
            "mode": "human_corrected",
            "source_event_ids": [event["event_id"]],
        }

    def _undo_last_correction(
        self,
        state: dict[str, Any],
        event: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> None:
        target_event_id = event["payload"]["target_event_id"]
        if not history or history[-1]["event_id"] != target_event_id:
            raise self._error("unsupported_correction", "Undo must target the latest applied correction", event)
        target_event = history[-1]
        if target_event["event_type"] != "rename_node" or target_event["actor"] != "human":
            raise self._error("unsupported_correction", "Prototype Undo only supports the latest rename_node", event)
        node_id = target_event["payload"]["node_id"]
        node = self._require_node(state, node_id, event)
        previous_label: str | None = None
        for prior in reversed(history[:-1]):
            if prior["event_type"] == "rename_node" and prior["payload"]["node_id"] == node_id:
                previous_label = prior["payload"]["label"]
                break
            if prior["event_type"] == "node_detected":
                generated_id = f"node:{prior['session_id']}:{prior['event_id']}"
                if generated_id == node_id:
                    previous_label = prior["payload"]["label"]
                    break
        if previous_label is None:
            raise self._error("unsupported_correction", "Cannot reconstruct the previous Node label", event)
        node["label"] = previous_label
        if node["type"] == "action":
            node["action"]["description"] = previous_label
        self._touch_node(node, event)
