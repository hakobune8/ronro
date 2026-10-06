"""Deterministic, content-only post-meeting PDF from the accepted Canvas.

This is an offline rendering boundary. Authentication, private object storage,
download authorization, and seven-day deletion are separate service gates.
No transcript or raw audio is placed in the PDF.
"""

from __future__ import annotations

import html
import io
import math
from typing import Any, Mapping, Sequence

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Flowable, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer

from .display_labels import display_projection
from .errors import PrototypeError
from .replay import ReplayResult, ReplayRunner, canonical_json
from .schema import SchemaValidator
from .semantic_canvas import project_semantic_canvas
from .semantic_projection import final_discussion_map
from .service_errors import ServiceStoreError


ROLE = {
    "idea": "視点", "option": "案", "concern": "懸念",
    "decision": "決定", "open_item": "未解決事項", "action": "次の対応",
}
RELATION = {
    "discussion_provenance": "話を受けて",
    "supports": "支持", "opposes": "懸念",
}
STATE = {
    "candidate": "候補", "confirmed": "確定", "active": "継続中",
    "resolved": "解決済み", "completed": "完了", "revoked": "撤回",
    "archived": "記録", "parked": "保留",
}
ROLE_COLOR = {
    "idea": ("#eef8fa", "#20768a"),
    "option": ("#eef8f0", "#23824e"),
    "concern": ("#fff1ec", "#ad5039"),
    "decision": ("#fff6e7", "#a16d16"),
    "open_item": ("#f6effb", "#7c5797"),
    "action": ("#eef2ff", "#4967a7"),
}


def _role_label(node: Mapping[str, Any]) -> str:
    if node["type"] == "decision":
        return "確定事項" if node["status"] == "confirmed" else "決定候補"
    return ROLE.get(node["type"], "論点")


def _pdf_overview_ids(canvas: Mapping[str, Any], *, limit: int = 8) -> list[str]:
    """Semantic zoom: outcomes plus their local discussion backbone."""

    nodes = {node["id"]: node for node in canvas["nodes"]}
    edges = canvas["edges"]
    outcomes = sorted(
        (node for node in nodes.values() if node["type"] in {"decision", "open_item", "action"}),
        key=lambda node: (node["created_sequence"], node["id"]),
    )
    selected = [node["id"] for node in outcomes[:limit]]
    for kind in ("discussion_provenance", "supports", "opposes"):
        for edge in edges:
            if len(selected) >= limit:
                break
            source, target = edge["source_node_id"], edge["target_node_id"]
            if edge["type"] == kind and target in selected and source in nodes and source not in selected:
                selected.append(source)
    if not selected:
        selected = [node["id"] for node in sorted(
            nodes.values(), key=lambda node: (node["created_sequence"], node["id"])
        )[:limit]]
    return selected


class _CanvasMiniMap(Flowable):
    """Paper camera onto accepted Canvas positions, with no new Graph edges."""

    def __init__(self, canvas: Mapping[str, Any], node_ids: Sequence[str], font: str) -> None:
        super().__init__()
        self.width = 500
        self.height = 230
        self.font = font
        selected = set(node_ids)
        self.nodes = [node for node in canvas["nodes"] if node["id"] in selected]
        self.edges = [edge for edge in canvas["edges"] if edge["type"] in RELATION
                      and edge["source_node_id"] in selected
                      and edge["target_node_id"] in selected]

    def _lines(self, value: str, max_width: float) -> list[str]:
        lines = []
        current = ""
        for char in value:
            if pdfmetrics.stringWidth(current + char, self.font, 8) > max_width and current:
                lines.append(current)
                current = char
            else:
                current += char
        if current:
            lines.append(current)
        if len(lines) > 2:
            lines = [lines[0], lines[1][:-1] + "…"]
        return lines

    def draw(self) -> None:
        if not self.nodes:
            return
        painter = self.canv
        card_w, card_h, margin = 116, 50, 8
        xs = [node["x"] for node in self.nodes]
        ys = [node["y"] for node in self.nodes]
        span_x, span_y = max(xs) - min(xs), max(ys) - min(ys)
        scale_x = (self.width - card_w - margin * 2) / max(span_x, 1)
        scale_y = (self.height - card_h - margin * 2) / max(span_y, 1)
        positions = {}
        for node in self.nodes:
            px = (self.width / 2 if not span_x else
                  card_w / 2 + margin + (node["x"] - min(xs)) * scale_x)
            py = (self.height / 2 if not span_y else
                  self.height - card_h / 2 - margin - (node["y"] - min(ys)) * scale_y)
            positions[node["id"]] = (px, py)
        for edge in self.edges:
            sx, sy = positions[edge["source_node_id"]]
            tx, ty = positions[edge["target_node_id"]]
            dx, dy = tx - sx, ty - sy
            length = math.hypot(dx, dy) or 1
            vx, vy = dx / length, dy / length
            line_color = {"discussion_provenance": "#548cac", "supports": "#339061",
                          "opposes": "#b56250"}[edge["type"]]
            painter.setStrokeColor(colors.HexColor(line_color))
            painter.setLineWidth(1.5)
            painter.setDash(3, 2) if edge["type"] != "discussion_provenance" else painter.setDash()
            start_x, start_y = sx + vx * 29, sy + vy * 25
            end_x, end_y = tx - vx * 29, ty - vy * 25
            painter.line(start_x, start_y, end_x, end_y)
            painter.setDash()
        for node in self.nodes:
            x, y = positions[node["id"]]
            fill, border = ROLE_COLOR.get(node["type"], ("#f5f8fa", "#6f8491"))
            painter.setFillColor(colors.HexColor(fill))
            painter.setStrokeColor(colors.HexColor(border))
            painter.setLineWidth(1.1)
            painter.roundRect(x - card_w / 2, y - card_h / 2,
                              card_w, card_h, 5, fill=1, stroke=1)
            painter.setFillColor(colors.HexColor(border))
            painter.setFont(self.font, 7)
            painter.drawString(x - card_w / 2 + 5, y + 12,
                               _role_label(node))
            painter.setFillColor(colors.HexColor("#1f3343"))
            painter.setFont(self.font, 8)
            for index, line in enumerate(self._lines(node["label"], card_w - 10)):
                painter.drawString(x - card_w / 2 + 5, y - 2 - index * 11, line)


def prepare_final_record(
    replay: ReplayResult, *, final_revision: int, schema_validator: SchemaValidator,
    capture_intervals: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Reject an unfrozen/corrupt Graph before creating a shareable artifact."""

    graph = replay.state["graph"]
    try:
        schema_validator.validate_domain(replay.state)
    except PrototypeError as exc:
        raise ServiceStoreError("final_graph_invalid", "Final Graph failed validation") from exc
    if type(final_revision) is not int or final_revision < 1:
        raise ServiceStoreError("final_revision_invalid", "Final revision is required")
    if graph.get("revision") != final_revision:
        raise ServiceStoreError("final_revision_mismatch", "Graph is not the frozen final revision")
    events = tuple(sorted(replay.events, key=lambda row: row["sequence"]))
    if (not events or events[-1].get("event_type") != "session_ended"
            or events[-1].get("sequence") != final_revision):
        raise ServiceStoreError("session_not_ended", "Accepted Session end is required")
    if any(event.get("sequence") != index for index, event in enumerate(events, 1)):
        raise ServiceStoreError("event_sequence_invalid", "Event sequence has a gap")
    try:
        rebuilt = ReplayRunner(schema_validator).replay_events(
            session_id=graph["session_id"], evidence=replay.state["evidence"],
            utterances=replay.state["utterances"], events=events,
        )
    except PrototypeError as exc:
        raise ServiceStoreError("final_replay_invalid", "Final Events failed replay") from exc
    if canonical_json(rebuilt.state) != canonical_json(replay.state):
        raise ServiceStoreError("final_replay_mismatch", "Final Graph differs from accepted Events")
    end_payload = events[-1].get("payload") or {}
    if end_payload.get("final_graph_revision") != final_revision - 1:
        raise ServiceStoreError("final_revision_mismatch", "Session end does not match Graph")
    created = next((event for event in events if event.get("event_type") == "session_created"), None)
    if created is None:
        raise ServiceStoreError("session_not_created", "Session creation is missing")
    display = display_projection(graph, replay.presentation)
    labels = {node_id: value["text"] for node_id, value in display.items()}
    canvas = project_semantic_canvas(graph, events, labels)
    final_map = final_discussion_map(graph, events, labels)
    nodes = [node for node in graph["nodes"] if node["type"] != "topic"]
    by_id = {node["id"]: node for node in nodes}
    gaps = []
    for interval in capture_intervals:
        if interval.get("kind") != "capture_unavailable":
            continue  # Deliberate pause is not an Evidence gap.
        gaps.append({"start": interval.get("opened_at"),
                     "end": interval.get("closed_at")})
    return {
        "version": "service-final-record-v1",
        "session_id": graph["session_id"],
        "revision": final_revision,
        "title": created.get("payload", {}).get("title") or "会議",
        "incomplete": end_payload.get("drain_status") != "complete",
        "has_gap_warning": bool(gaps) or end_payload.get("drain_status") != "complete",
        "canvas": canvas,
        "pdf_overview_ids": _pdf_overview_ids(canvas),
        "final_map": final_map,
        "display": display,
        "nodes": by_id,
        "gaps": gaps,
    }


def render_final_pdf(record: Mapping[str, Any]) -> bytes:
    """Render one immutable record; callers must store/serve it privately."""

    if record.get("version") != "service-final-record-v1":
        raise ServiceStoreError("record_version_invalid", "Unsupported final record")
    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
    font = "HeiseiKakuGo-W5"
    normal = ParagraphStyle("normal-ja", fontName=font, fontSize=10.5,
                            leading=16, textColor=colors.HexColor("#1f3343"),
                            spaceAfter=6, alignment=TA_LEFT, wordWrap="CJK")
    small = ParagraphStyle("small-ja", parent=normal, fontSize=9, leading=13)
    heading = ParagraphStyle("heading-ja", parent=normal, fontSize=16, leading=23,
                             spaceBefore=13, spaceAfter=9)
    title = ParagraphStyle("title-ja", parent=normal, fontSize=22, leading=32,
                           spaceAfter=12)
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=45, rightMargin=45,
        topMargin=44, bottomMargin=48, title="RONRO 会議後の論点図",
        author="RONRO", invariant=1,
    )
    story: list[Any] = []

    def add(text: Any, style: ParagraphStyle = normal) -> None:
        story.append(Paragraph(html.escape(str(text)).replace("\n", "<br/>"), style))

    def section(text: str) -> None:
        add(text, heading)

    add(record["title"], title)
    add("会議後の論点図", small)
    if record["has_gap_warning"]:
        add("一部の音声・解析が完了していない可能性があります。以下の欠落可能性を確認してください。")
    else:
        add("受理済みの議論構造を表示しています。音声の完全性を保証する表示ではありません。")
    gaps = record["gaps"]
    if gaps:
        section("記録に欠落可能性がある区間")
        for gap in gaps:
            start = gap["start"] or "時刻不明"
            end = gap["end"] or "終了時刻不明"
            add(f"{start} ～ {end}", small)
    elif record["incomplete"]:
        section("記録に欠落可能性がある区間")
        add("範囲を特定できていません。")

    final_map = record["final_map"]
    section("議論の全体像")
    story.append(_CanvasMiniMap(record["canvas"], record["pdf_overview_ids"], font))
    add("線は現在の論点図にあるつながりです。原因・結果を断定するものではありません。詳しい内容は後半に掲載しています。", small)
    if not record["canvas"]["nodes"]:
        add("表示できる論点はありません。")
    outside = len(record["nodes"]) - len(record["pdf_overview_ids"])
    if outside:
        add(f"図外の論点{outside}件も、後半の詳細に掲載しています。", small)

    selected_edges = [edge for edge in record["canvas"]["edges"]
                      if edge["source_node_id"] in record["pdf_overview_ids"]
                      and edge["target_node_id"] in record["pdf_overview_ids"]]
    if selected_edges:
        legend = []
        if any(edge["type"] == "discussion_provenance" for edge in selected_edges):
            legend.append("青線: この話を受けて")
        if any(edge["type"] == "supports" for edge in selected_edges):
            legend.append("緑破線: 支持する理由")
        if any(edge["type"] == "opposes" for edge in selected_edges):
            legend.append("赤破線: 懸念・反対")
        add(" / ".join(legend), small)

    nodes = record["nodes"]
    decision = [node for node in nodes.values() if node["type"] == "decision"
                and node["status"] in {"candidate", "confirmed"}]
    open_items = [node for node in nodes.values() if node["type"] == "open_item"
                  and node["status"] == "active"]
    actions = [node for node in nodes.values() if node["type"] == "action"
               and node["status"] not in {"archived", "revoked"}]
    for label, group in (("決まったこと・決まりつつあること", decision),
                         ("残っていること", open_items),
                         ("次にすること", actions)):
        section(label)
        if not group:
            add("該当なし", small)
        for node in group:
            state = ("確定" if node["type"] == "decision" and node["status"] == "confirmed"
                     else "決定候補" if node["type"] == "decision" else "")
            block = [Paragraph(html.escape(f"{state} {node['label']}".strip()), normal)]
            if node["type"] == "action":
                action = node.get("action") or {}
                details = [f"担当: {action['owner']}" for _ in [0] if action.get("owner")]
                if action.get("due_date"):
                    details.append(f"期限: {action['due_date']}")
                if details:
                    block.append(Paragraph(html.escape(" / ".join(details)), small))
            story.append(KeepTogether(block))

    story.append(PageBreak())
    section("論点の詳細")
    # Full Canonical text remains available even when overview uses a label.
    for node in sorted(nodes.values(), key=lambda item: (item["created_at"], item["id"])):
        role = ROLE.get(node["type"], node["type"])
        state = " · " + STATE.get(node["status"], "状態未確認") if node["type"] in {"decision", "open_item", "action"} else ""
        block = [Paragraph(html.escape(f"{role}{state}"), small),
                 Paragraph(html.escape(node["label"]).replace("\n", "<br/>"), normal),
                 Spacer(1, 8)]
        if node["type"] == "action":
            action = node.get("action") or {}
            attributes = []
            if action.get("owner"):
                attributes.append(f"担当: {action['owner']}")
            if action.get("due_date"):
                attributes.append(f"期限: {action['due_date']}")
            if attributes:
                block.insert(2, Paragraph(html.escape(" / ".join(attributes)), small))
        story.append(KeepTogether(block))

    def footer(page_canvas: Any, doc: Any) -> None:
        page_canvas.saveState()
        page_canvas.setFont(font, 8)
        page_canvas.setFillColor(colors.HexColor("#657685"))
        page_canvas.drawString(45, 24, "RONRO · 会議後の論点図")
        page_canvas.drawRightString(A4[0] - 45, 24, str(doc.page))
        page_canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
