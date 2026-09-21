"""Developer-only fixed Event scenarios for visual evaluation of M5."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .fixtures import Fixture


def build_large_map_fixture() -> Fixture:
    """Build a deterministic, non-canonical UI stress scenario.

    This is intentionally not discovered as a Golden Evaluation Fixture. It
    uses the existing Event Schema and Materializer only to exercise the M5
    presentation with several Topic Lanes, cards, decisions, and Parking.
    """

    session_id = "s-ui-large"
    events: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []

    def add_event(
        event_type: str,
        actor: str,
        payload: dict[str, Any],
        *,
        source_evidence: bool = False,
    ) -> str:
        sequence = len(events) + 1
        event_id = f"ui-large-{sequence:03d}"
        event_time = f"2026-09-19T22:{sequence // 60:02d}:{sequence % 60:02d}Z"
        source_evidence_ids: list[str] = []
        if source_evidence:
            evidence_id = f"evd-ui-large-{len(evidence) + 1:03d}"
            evidence.append(
                {
                    "id": evidence_id,
                    "session_id": session_id,
                    "sequence": len(evidence) + 1,
                    "timestamp": event_time,
                    "speaker": "Fixture",
                    "text": payload.get("label", payload.get("topic_id", event_type)),
                }
            )
            source_evidence_ids.append(evidence_id)
        event: dict[str, Any] = {
            "event_id": event_id,
            "session_id": session_id,
            "sequence": sequence,
            "event_type": event_type,
            "occurred_at": event_time,
            "actor": actor,
            "source_evidence_ids": source_evidence_ids,
            "payload": payload,
        }
        if actor == "human":
            event["expected_revision"] = sequence - 1
        events.append(event)
        return event_id

    add_event(
        "session_created",
        "system",
        {"title": "Large Map UI Scenario", "goal": "30分相当のDiscussion Map読みやすさを確認する"},
    )
    add_event("session_started", "system", {})

    topic_ids: dict[str, str] = {}

    def add_topic(label: str, *, focus: bool = True) -> str:
        event_id = add_event("node_detected", "analyzer", {"node_type": "topic", "label": label}, source_evidence=True)
        topic_id = f"node:{session_id}:{event_id}"
        topic_ids[label] = topic_id
        if focus:
            add_event("topic_focus_changed", "analyzer", {"topic_id": topic_id, "confidence": 0.9}, source_evidence=True)
        return topic_id

    def add_topic_cards(topic_id: str, topic_index: int) -> None:
        card_definitions = [
            ("idea", f"主要な観点 {topic_index + 1}"),
            ("option", f"選択肢 {topic_index + 1}-A"),
            ("concern", f"懸念事項 {topic_index + 1}"),
            ("open_item", f"未解決の問い {topic_index + 1}"),
            ("action", f"確認作業 {topic_index + 1}"),
            ("decision", f"方針候補 {topic_index + 1}"),
        ]
        for node_type, label in card_definitions:
            payload: dict[str, Any] = {"node_type": node_type, "label": label}
            if node_type == "action":
                payload["action"] = {"owner": None, "due_date": None}
            decision_event_id = add_event("node_detected", "analyzer", payload, source_evidence=True)
            if node_type == "decision" and topic_index == 0:
                decision_id = f"node:{session_id}:{decision_event_id}"
                add_event(
                    "confirm_decision",
                    "human",
                    {"decision_node_id": decision_id, "expected_status": "candidate"},
                )

    topic_names = ["MVP範囲", "Discussion Map", "Visual生成", "料金モデル", "Parking候補"]
    for index, label in enumerate(topic_names):
        topic_id = add_topic(label)
        add_topic_cards(topic_id, index)

    evaluation_topic_id = add_topic("Evaluation", focus=False)
    add_event(
        "move_to_parking_lot",
        "human",
        {"node_id": topic_ids["Parking候補"]},
    )
    add_event(
        "topic_focus_changed",
        "analyzer",
        {"topic_id": evaluation_topic_id, "confidence": 0.93},
        source_evidence=True,
    )
    add_topic_cards(evaluation_topic_id, len(topic_names))

    return Fixture(
        fixture_id="ui-large",
        name="large-map-ui-scenario",
        path=Path("<generated-m5-ui-scenario>"),
        evidence=evidence,
        events=events,
        expected={
            "session": {
                "id": session_id,
                "title": "Large Map UI Scenario",
                "goal": "30分相当のDiscussion Map読みやすさを確認する",
            },
            "utterances": [],
        },
        invalid_cases=[],
    )


def build_pilot_shared_fixture() -> Fixture:
    """Build the content-first scenario used by the participant Shared View.

    This remains a normal canonical event replay.  The labels are intentionally
    meaningful so that screenshots demonstrate the product experience rather
    than a presentation stress fixture with synthetic counters.
    """

    session_id = "s-pilot-shared"
    events: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []

    def add_event(
        event_type: str,
        actor: str,
        payload: dict[str, Any],
        *,
        source_evidence: bool = False,
    ) -> str:
        sequence = len(events) + 1
        event_id = f"pilot-shared-{sequence:03d}"
        event_time = f"2026-09-21T10:{sequence // 60:02d}:{sequence % 60:02d}Z"
        source_evidence_ids: list[str] = []
        if source_evidence:
            evidence_id = f"evd-pilot-shared-{len(evidence) + 1:03d}"
            evidence.append(
                {
                    "id": evidence_id,
                    "session_id": session_id,
                    "sequence": len(evidence) + 1,
                    "timestamp": event_time,
                    "speaker": "Pilot participant",
                    "text": payload.get("label", payload.get("topic_id", event_type)),
                }
            )
            source_evidence_ids.append(evidence_id)
        event: dict[str, Any] = {
            "event_id": event_id,
            "session_id": session_id,
            "sequence": sequence,
            "event_type": event_type,
            "occurred_at": event_time,
            "actor": actor,
            "source_evidence_ids": source_evidence_ids,
            "payload": payload,
        }
        if actor == "human":
            event["expected_revision"] = sequence - 1
        events.append(event)
        return event_id

    add_event(
        "session_created",
        "system",
        {
            "title": "Live Pilot Shared View",
            "goal": "議論の現在地を共有する",
        },
    )
    add_event("session_started", "system", {})

    topic_ids: dict[str, str] = {}

    def add_topic(label: str, *, focus: bool = True) -> str:
        event_id = add_event(
            "node_detected",
            "analyzer",
            {"node_type": "topic", "label": label},
            source_evidence=True,
        )
        topic_id = f"node:{session_id}:{event_id}"
        topic_ids[label] = topic_id
        if focus:
            add_event(
                "topic_focus_changed",
                "analyzer",
                {"topic_id": topic_id, "confidence": 0.94},
                source_evidence=True,
            )
        return topic_id

    def add_node(node_type: str, label: str) -> str:
        payload: dict[str, Any] = {"node_type": node_type, "label": label}
        if node_type == "action":
            payload["action"] = {"owner": None, "due_date": None}
        event_id = add_event("node_detected", "analyzer", payload, source_evidence=True)
        return f"node:{session_id}:{event_id}"

    mvp_topic = add_topic("MVPで何を実現するか")
    add_node("idea", "議論の現在地を見える化")
    add_node("idea", "音声で論点図を更新")
    add_node("option", "共有画面で確認する")
    add_node("concern", "視線を奪いすぎない")
    add_node("decision", "スマホ画面はPilotでは使わない？")
    add_node("open_item", "どの程度の更新速度が必要？")
    add_node("action", "実会議で試す")

    add_topic("画像生成の扱い")
    add_node("idea", "画像生成は必要な場面だけ使う")
    add_node("option", "手動で生成を始める")
    add_node("concern", "自動生成で議論がそれないか")
    add_node("decision", "画像生成は手動で始める？")
    add_node("open_item", "画像生成を自動にする？")
    add_node("action", "Pilot用画面を確認する")

    add_event(
        "topic_focus_changed",
        "analyzer",
        {"topic_id": mvp_topic, "confidence": 0.95},
        source_evidence=True,
    )
    add_node("idea", "論点図を中心価値にする")
    add_node("option", "共有画面を中心に試す")
    add_node("concern", "更新が議論の邪魔にならない")
    add_node("open_item", "論点図を見る頻度をどう評価する？")
    add_node("action", "Pilot用画面を確認する")

    add_topic("料金と運用")
    add_node("idea", "まずは小さなPilotで試す")
    add_node("option", "2〜3人で10〜15分")
    add_node("concern", "運用時の負荷が大きくならないか")
    add_node("open_item", "継続利用の条件は何か？")
    add_node("action", "Pilotの日程を決める")

    add_topic("オンライン会議との連携", focus=False)
    add_event("move_to_parking_lot", "human", {"node_id": topic_ids["オンライン会議との連携"]})

    add_event(
        "topic_focus_changed",
        "analyzer",
        {"topic_id": mvp_topic, "confidence": 0.95},
        source_evidence=True,
    )
    add_node("idea", "MVPでは共有画面の体験に集中する")

    evaluation_topic = add_topic("パイロットをどう評価するか")
    add_node("idea", "AIの精度だけで評価しない")
    add_node("idea", "論点図が役立つかを見る")
    add_node("option", "10〜15分の実会議で確認")
    add_node("concern", "参加者の注意を奪わない")
    add_node("decision", "Pilotは2〜3人で実施する")
    add_node("open_item", "論点図を見る頻度をどう評価する？")
    add_node("action", "Pilot #1を実施する")

    return Fixture(
        fixture_id="pilot-shared",
        name="pilot-shared-content-scenario",
        path=Path("<generated-pilot-shared-scenario>"),
        evidence=evidence,
        events=events,
        expected={
            "session": {
                "id": session_id,
                "title": "Live Pilot Shared View",
                "goal": "議論の現在地を共有する",
            },
            "utterances": [],
        },
        invalid_cases=[],
    )
