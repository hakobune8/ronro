"""Participant-facing selection only; canonical state is never modified."""
from __future__ import annotations

import copy
from pathlib import Path

from .materializer import initial_state
from .replay import ReplayResult, ReplayRunner
from .schema import SchemaValidator

ORDINARY = {"idea", "option", "concern"}
GROUPS = ("candidate", "confirmed", "open_item", "action")
INACTIVE = {"archived", "resolved", "completed", "revoked", "parked"}


def select_shared(graph, events, previous=()):
    sequences = {e["event_id"]: e["sequence"] for e in events}
    nodes = [n for n in graph["nodes"] if n["status"] not in INACTIVE]
    ordinary = [n for n in nodes if n["type"] in ORDINARY]
    def rank(n):
        return (max((sequences.get(e, 0) for e in n["source_event_ids"]), default=0), n["id"])
    selected = [n["id"] for n in sorted(ordinary, key=rank, reverse=True)[:6]]
    slots = list(previous) + [None] * (6-len(previous))
    slots = [i if i in selected else None for i in slots]
    for node_id in selected:
        if node_id not in slots:
            slots[slots.index(None)] = node_id
    rail = {}
    for group in GROUPS:
        def eligible(n):
            return (n["type"] == "decision" and n["status"] == group) if group in {"candidate", "confirmed"} else n["type"] == group
        items = sorted(filter(eligible, nodes), key=lambda n: (n["created_at"], n["id"]))
        rail[group] = {"node_ids": [n["id"] for n in items[:1]], "overflow": max(0, len(items)-1)}
    return {"version": "shared-recency-v1", "slots": slots, "eligible": len(ordinary),
            "overflow": len(ordinary)-len(selected), "rail": rail}


class SharedProjection:
    """Replay skipped revisions, caching only private derived state.

    Fresh clients and incremental clients get identical slots. Branch/undo
    histories reset the cache. A normal append only replays new Events.
    """
    def __init__(self):
        self.reset()

    def reset(self):
        self._result = None
        self._slots = []
        self._runner = None

    def project(self, state, events):
        ordered = sorted(events, key=lambda e: e["sequence"])
        session_id = state["graph"]["session_id"]
        prior = list(self._result.events) if self._result else []
        if self._result is None or self._result.state["graph"]["session_id"] != session_id or ordered[:len(prior)] != prior:
            self.reset()
            self._result = ReplayResult(initial_state(session_id, state.get("evidence", []), state.get("utterances", [])), ())
            prior = []
        if len(ordered) > len(prior):
            if self._runner is None:
                self._runner = ReplayRunner(SchemaValidator(Path(__file__).resolve().parents[1] / "schemas"))
            self._result.state["evidence"] = copy.deepcopy(state.get("evidence", []))
            self._result.state["utterances"] = copy.deepcopy(state.get("utterances", []))
            for event in ordered[len(prior):]:
                self._result = self._runner.apply_event(self._result, event)
                self._slots = select_shared(self._result.state["graph"], self._result.events, self._slots)["slots"]
        return select_shared(state["graph"], ordered, self._slots)
