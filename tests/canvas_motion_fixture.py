"""Public-safe, synthetic meeting progression for Semantic Canvas motion QA.

This deliberately exercises presentation transitions, not Analyzer quality.
No speech, provider output, or real evaluation data is used.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone

from prototype.layout import StableLayout, map_projection


def build_scenes() -> list[dict]:
    session_id = "synthetic-canvas-motion"
    origin = datetime(2026, 9, 25, 0, 0, tzinfo=timezone.utc)
    nodes: list[dict] = []
    edges: list[dict] = []
    events: list[dict] = []
    scenes: list[dict] = []
    layout = StableLayout()
    minute = 0

    def stamp() -> str:
        return (origin + timedelta(minutes=minute)).isoformat().replace("+00:00", "Z")

    def event(kind: str, payload: dict, evidence: str | None = None) -> str:
        eid = f"motion-event-{len(events) + 1:03d}"
        events.append({"event_id": eid, "sequence": len(events) + 1,
                       "event_type": kind, "occurred_at": stamp(),
                       "source_evidence_ids": [evidence] if evidence else [],
                       "payload": payload})
        return eid

    def node(node_id: str, kind: str, short: str, full: str, status: str = "active") -> None:
        evidence = f"synthetic-{node_id}"
        eid = event("node_detected", {"node_type": kind, "label": full}, evidence)
        nodes.append({"id": node_id, "type": kind, "status": status, "label": full,
                      "display_label": short, "created_at": stamp(), "updated_at": stamp(),
                      "evidence_ids": [evidence], "source_event_ids": [eid]})

    def link(source: str, target: str, kind: str = "discussion_provenance") -> None:
        # At creation, provenance belongs to the new target while argument
        # Relations belong to the new reason/concern source. This is also what
        # the Canvas placement rule uses to keep those Nodes beside their anchor.
        evidence_owner = target if kind == "discussion_provenance" else source
        eid = event("relation_detected", {"source_node_id": source,
                                            "target_node_id": target, "relation_type": kind},
                    f"synthetic-{evidence_owner}")
        edges.append({"id": f"relation-{eid}", "type": kind, "source_node_id": source,
                      "target_node_id": target, "source_event_ids": [eid]})

    def update(node_id: str, full: str | None = None, status: str | None = None) -> None:
        target = next(item for item in nodes if item["id"] == node_id)
        eid = event("node_updated", {"node_id": node_id}, f"synthetic-{node_id}-update")
        target["source_event_ids"].append(eid)
        target["updated_at"] = stamp()
        if full is not None:
            target["label"] = full
        if status is not None:
            target["status"] = status

    def scene(title: str, note: str, *, ended: bool = False) -> None:
        graph = {"session_id": session_id, "revision": len(events),
                 "nodes": copy.deepcopy(nodes), "edges": copy.deepcopy(edges),
                 "current_topic": {"primary_topic_id": None}}
        state = {"session": {"id": session_id, "title": "防災対応の検討会"}, "graph": graph}
        projected = map_projection(state, copy.deepcopy(events), layout)
        # A deterministic presentation hint for overview labels only. Canonical
        # full text remains in graph/node and in the focused subtitle.
        labels = {item["id"]: item["display_label"] for item in nodes}
        for item in projected["semantic_canvas"]["nodes"]:
            item["label"] = labels[item["id"]]
        projected["shared"] = {}
        scenes.append({"title": title, "note": note, "minute": minute,
                       "snapshot": {"state": state, "map": projected,
                                    "live_state": {"runtime_state": "ended" if ended else "active"}}})

    scene("開始", "議論を待つ空のCanvas")
    minute = 2
    node("water", "concern", "三避難所で初日の飲料水が不足",
         "三つの避難所では、発災初日に必要な飲料水が現在の備蓄だけでは不足する見込みが共有された。")
    scene("最初の論点", "未結線の入口を表示")
    minute = 5
    node("move", "option", "既存倉庫の水を再配置する",
         "初日の飲料水不足に対し、既存倉庫にある水を三避難所へ再配置する案が挙がった。")
    link("water", "move")
    scene("対応案", "議論を受けて案が派生")
    minute = 8
    node("speed", "idea", "再配置なら初日に間に合う",
         "既存倉庫から再配置すれば、新たな調達を待つより早く、初日の必要量に間に合う可能性がある。")
    link("speed", "move", "supports")
    scene("支える根拠", "骨格とは別に支持を表示")
    minute = 11
    node("truck-risk", "concern", "輸送路が一部通行止めの可能性",
         "地震後の輸送路は一部通行止めの可能性があり、倉庫からの再配置が予定通り進まない懸念が出た。")
    link("truck-risk", "move", "opposes")
    scene("懸念が付く", "支持と懸念を線種・色で区別")
    minute = 14
    node("tank", "option", "給水車を追加手配する",
         "同じ飲料水不足への別案として、給水車を追加手配する案も出た。")
    link("water", "tank")
    scene("兄弟の選択肢", "別案同士を無理につながない")
    minute = 18
    node("check", "open_item", "道路の通行可否が未確認",
         "倉庫から各避難所までの道路を給水車と搬送車が通れるかは、まだ確認できていない。")
    link("truck-risk", "check")
    scene("未解決事項", "論点から残った問いが生じる")
    minute = 21
    node("radio", "idea", "住民向け連絡手段を確認",
         "飲料水の配布方法とは別に、停電時に住民へ情報を伝える連絡手段を確認したいという話題に移った。")
    scene("別の話題", "独立したCanvas領域へカメラ移動")
    # A later Human correction explicitly establishes that this was another
    # discussion entry point. The Node has already been placed on the Canvas.
    minute = 22
    link("water", "radio")
    mistaken = next(edge for edge in edges if edge["source_node_id"] == "water" and edge["target_node_id"] == "radio")
    edges.remove(mistaken)
    event("correct_relation", {"old_relation": {"source_node_id": "water",
                                                 "target_node_id": "radio",
                                                 "relation_type": "discussion_provenance"},
                               "declared_independent": True})
    minute = 24
    node("sms", "option", "SMSで配布情報を伝える",
         "通信状況が許す場合は、SMSで配布場所と開始時刻を住民へ伝える案が挙がった。")
    link("radio", "sms")
    scene("別の枝が成長", "独立と確認した入口を含む別の枝")
    minute = 27
    update("move", "飲料水の話に戻り、既存倉庫の水を三避難所へ再配置する案の実行条件を改めて確認した。")
    scene("前の話へ戻る", "既存Nodeへフォーカスとカメラが戻る")
    minute = 30
    link("move", "check")
    scene("後から結線", "既存Nodeの位置を変えず関係だけ追加")
    minute = 33
    wrong = next(edge for edge in edges if edge["source_node_id"] == "move" and edge["target_node_id"] == "check")
    edges.remove(wrong)
    event("correct_relation", {"old_relation": {"source_node_id": "move",
                                                 "target_node_id": "check",
                                                 "relation_type": "discussion_provenance"},
                               "declared_independent": False})
    scene("関係を訂正", "訂正後もNodeの座標は維持")
    minute = 36
    node("decision", "decision", "倉庫の水を再配置する方針",
         "三避難所の初日の飲料水について、既存倉庫の水を再配置する方針を決定候補として挙げた。",
         "candidate")
    link("move", "decision")
    scene("決定候補", "案から候補が生じても確定はしない")
    minute = 39
    update("decision", "参加者が、既存倉庫の水を三避難所へ再配置する方針を明示的に確認した。", "confirmed")
    scene("人が確定", "候補と確定の状態差を表示")
    minute = 42
    node("action", "action", "再配置の準備を進める",
         "合意した再配置方針に基づき、搬送に必要な準備を進める。担当者と期限はこの時点では決まっていない。")
    link("decision", "action")
    scene("次の対応", "Actionの由来は表示、担当・期限は捏造しない")
    minute = 45
    update("action", "再配置に必要な倉庫の在庫確認、各避難所の受入条件、輸送経路の通行可否、搬送車両の調整、関係機関への連絡について順番に確認する。"
           "ただし、道路の被害状況にはまだ未確認の部分があるため、輸送時刻を確定したとは扱わない。担当者や期限もこの会議では明示されていない。"
           "関係機関への確認結果を踏まえて実施可否を判断する。")
    scene("長いCanonical本文", "字幕は最大5行、全文はGraphに保持")
    for target_count, target_minute in ((15, 48), (30, 51), (60, 54), (100, 57)):
        minute = target_minute
        while len(nodes) < target_count:
            index = len(nodes)
            subject = ("避難所の給水", "物資の配分", "道路の復旧", "被害情報の共有",
                       "要配慮者の移動", "河川の点検")[index % 6]
            new_id = f"expansion-{index:03d}"
            node(new_id, "idea", f"{subject}：確認事項{index + 1}",
                 f"{subject}について、担当部署間で確認すべき点が追加された。これは表示負荷を試すための合成論点{index + 1}である。")
            if index % 8 != 0:
                previous = nodes[index - 1]["id"]
                link(previous, new_id)
        scene(f"{target_count} Node", "Canvasは増えてもLive表示は局所のまま")
    minute = 60
    scene("会議終了", "同じCanvasをズームアウトして俯瞰", ended=True)
    return scenes


if __name__ == "__main__":
    print(json.dumps(build_scenes(), ensure_ascii=False))
