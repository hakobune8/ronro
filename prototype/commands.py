"""Human Command -> Canonical Event boundary for Prototype 1 M4."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import PrototypeError
from .fixtures import Fixture
from .replay import ReplayResult, ReplayRunner


@dataclass(frozen=True)
class CommandResult:
    event: dict[str, Any]
    result: ReplayResult


class HumanCommandHandler:
    """Validate UI commands and turn them into Human Events.

    The handler never mutates a Graph. It creates one Event and delegates
    application to the existing ReplayRunner / Event Store / Materializer
    path.
    """

    COMMAND_TYPES = {
        "confirm_decision",
        "revoke_decision",
        "resolve_open_item",
        "reopen_open_item",
        "rename_node",
        "merge_nodes",
        "move_to_parking_lot",
        "restore_from_parking_lot",
        "update_action",
        "set_current_topic",
        "undo_last_correction",
        "archive_node",
        "correct_relation",
    }

    def __init__(self, replay_runner: ReplayRunner) -> None:
        self.replay_runner = replay_runner

    def handle(self, result: ReplayResult, command: dict[str, Any]) -> CommandResult:
        if not isinstance(command, dict):
            raise PrototypeError("command_invalid", "Command must be an object")
        command_type = command.get("command_type")
        if command_type not in self.COMMAND_TYPES:
            raise PrototypeError("command_invalid", f"Unsupported Human Command: {command_type}")

        state = result.state
        current_revision = state["graph"]["revision"]
        expected_revision = command.get("expected_revision")
        if expected_revision != current_revision:
            raise PrototypeError(
                "revision_mismatch",
                f"Command expected revision {current_revision}, got {expected_revision}",
            )

        occurred_at = command.get("occurred_at")
        if not isinstance(occurred_at, str) or not occurred_at:
            raise PrototypeError("command_invalid", "Human Command requires occurred_at")

        event = self._build_event(result, command, command_type, occurred_at)
        next_result = self.replay_runner.apply_event(result, event)
        return CommandResult(event=event, result=next_result)

    @staticmethod
    def _node(state: dict[str, Any], node_id: str) -> dict[str, Any] | None:
        return next((node for node in state["graph"]["nodes"] if node["id"] == node_id), None)

    def _require_node(self, state: dict[str, Any], node_id: Any) -> dict[str, Any]:
        if not isinstance(node_id, str):
            raise PrototypeError("command_invalid", "node_id must be a string")
        node = self._node(state, node_id)
        if node is None:
            raise PrototypeError("missing_reference", f"Node {node_id} does not exist")
        return node

    @staticmethod
    def _command_error(message: str) -> PrototypeError:
        return PrototypeError("invalid_transition", message)

    def _build_event(
        self,
        result: ReplayResult,
        command: dict[str, Any],
        command_type: str,
        occurred_at: str,
    ) -> dict[str, Any]:
        state = result.state
        payload: dict[str, Any]

        if command_type in {"confirm_decision", "revoke_decision"}:
            node = self._require_node(state, command.get("decision_node_id"))
            expected_status = "candidate" if command_type == "confirm_decision" else "confirmed"
            if node["type"] != "decision" or node["status"] != expected_status:
                raise self._command_error(
                    f"{command_type} requires a Decision with status {expected_status}"
                )
            payload = {
                "decision_node_id": node["id"],
                "expected_status": expected_status,
            }
        elif command_type in {"resolve_open_item", "reopen_open_item"}:
            node = self._require_node(state, command.get("open_item_node_id"))
            expected_status = "active" if command_type == "resolve_open_item" else "resolved"
            if node["type"] != "open_item" or node["status"] != expected_status:
                raise self._command_error(
                    f"{command_type} requires an Open Item with status {expected_status}"
                )
            payload = {
                "open_item_node_id": node["id"],
                "expected_status": expected_status,
            }
        elif command_type == "rename_node":
            node = self._require_node(state, command.get("node_id"))
            label = command.get("label")
            if node["status"] == "archived":
                raise self._command_error("Archived Nodes cannot be renamed")
            if not isinstance(label, str) or not label.strip():
                raise PrototypeError("command_invalid", "rename_node requires a non-empty label")
            payload = {"node_id": node["id"], "label": label}
        elif command_type == "merge_nodes":
            source = self._require_node(state, command.get("source_node_id"))
            target = self._require_node(state, command.get("target_node_id"))
            if source["id"] == target["id"]:
                raise self._command_error("A Node cannot be merged into itself")
            if source["status"] == "archived" or target["status"] == "archived":
                raise self._command_error("Archived Nodes cannot be merged")
            payload = {
                "source_node_id": source["id"],
                "target_node_id": target["id"],
            }
        elif command_type == "move_to_parking_lot":
            node = self._require_node(state, command.get("node_id"))
            if node["type"] == "decision":
                raise self._command_error("Decision lifecycle cannot be replaced by Parking status")
            if node["status"] in {"archived", "parked"}:
                raise self._command_error("Only an active Node can be parked")
            payload = {"node_id": node["id"]}
        elif command_type == "restore_from_parking_lot":
            node = self._require_node(state, command.get("node_id"))
            if node["status"] != "parked":
                raise self._command_error("Only a parked Node can be restored")
            payload = {"node_id": node["id"]}
        elif command_type == "update_action":
            node = self._require_node(state, command.get("action_node_id"))
            if node["type"] != "action" or node["status"] == "archived":
                raise self._command_error("update_action requires a non-archived Action Node")
            allowed = ("description", "owner", "due_date", "status")
            changes = {key: command[key] for key in allowed if key in command}
            if not changes:
                raise PrototypeError("command_invalid", "update_action requires at least one field")
            payload = {"action_node_id": node["id"], **changes}
        elif command_type == "set_current_topic":
            node = self._require_node(state, command.get("topic_id"))
            if node["type"] != "topic" or node["status"] != "active":
                raise self._command_error("set_current_topic requires an active Topic")
            payload = {"topic_id": node["id"]}
        elif command_type == "archive_node":
            node = self._require_node(state, command.get("node_id"))
            if node["status"] == "archived":
                raise self._command_error("Node is already archived")
            payload = {"node_id": node["id"]}
        elif command_type == "correct_relation":
            old = command.get("old_relation")
            new = command.get("new_relation")
            if old is None and new is None:
                raise PrototypeError("command_invalid", "A relation correction needs an old or new relation")
            for relation in (old, new):
                if relation is None:
                    continue
                if not isinstance(relation, dict) or set(relation) != {"source_node_id", "target_node_id", "relation_type"}:
                    raise PrototypeError("command_invalid", "Relation correction needs exact endpoints and type")
                if relation["relation_type"] not in {"discussion_provenance", "supports", "opposes"}:
                    raise PrototypeError("command_invalid", "Only semantic Relations can be corrected here")
                self._require_node(state, relation["source_node_id"])
                self._require_node(state, relation["target_node_id"])
            payload = {
                "old_relation": old,
                "new_relation": new,
                "evidence_sequence_at_correction": max(
                    (item["sequence"] for item in state["evidence"]), default=0
                ),
                "declared_independent": command.get("declared_independent") is True,
            }
        else:
            payload = self._undo_payload(result, command)

        sequence = state["graph"]["last_event_sequence"] + 1
        event = {
            "event_id": f"human:{state['graph']['session_id']}:{sequence:06d}:{command_type}",
            "session_id": state["graph"]["session_id"],
            "sequence": sequence,
            "event_type": command_type,
            "occurred_at": occurred_at,
            "actor": "human",
            "source_evidence_ids": list(command.get("source_evidence_ids", [])),
            "expected_revision": state["graph"]["revision"],
            "payload": payload,
        }
        return event

    @staticmethod
    def _undo_payload(result: ReplayResult, command: dict[str, Any]) -> dict[str, Any]:
        if not result.events:
            raise PrototypeError("unsupported_correction", "There is no Human Correction to undo")
        latest = result.events[-1]
        if latest["actor"] != "human" or latest["event_type"] != "rename_node":
            raise PrototypeError(
                "unsupported_correction",
                "Prototype Undo only supports the latest rename_node",
            )
        target_event_id = command.get("target_event_id", latest["event_id"])
        if target_event_id != latest["event_id"]:
            raise PrototypeError(
                "unsupported_correction",
                "Undo must target the latest rename_node",
            )
        return {"target_event_id": target_event_id}


class CommandSession:
    """Mutable application session whose only state transition is Event-driven."""

    def __init__(self, result: ReplayResult, handler: HumanCommandHandler) -> None:
        self.result = result
        self.handler = handler

    @classmethod
    def from_fixture(
        cls,
        fixture: Fixture,
        replay_runner: ReplayRunner,
        *,
        through_sequence: int | None = None,
    ) -> "CommandSession":
        events = fixture.events
        if through_sequence is not None:
            events = [event for event in events if event["sequence"] <= through_sequence]
        result = replay_runner.replay_events(
            session_id=fixture.expected["session"]["id"],
            evidence=fixture.evidence,
            utterances=fixture.expected["utterances"],
            events=events,
        )
        return cls(result, HumanCommandHandler(replay_runner))

    def execute(self, command: dict[str, Any]) -> CommandResult:
        command_result = self.handler.handle(self.result, command)
        self.result = command_result.result
        return command_result

    def can_undo(self) -> bool:
        return bool(self.result.events) and self.result.events[-1]["event_type"] == "rename_node" and self.result.events[-1]["actor"] == "human"
