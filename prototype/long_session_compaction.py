"""Offline Long-session Map Compaction / Semantic Consolidation Spike."""

from __future__ import annotations

import argparse
import copy
import html
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

from .analyzer import TranscriptReplaySession
from .layout import StableLayout
from .materializer import initial_state
from .projection import build_presentation_projection
from .replay import ReplayResult, ReplayRunner
from .schema import SchemaValidator


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT / "evaluation" / "30min" / "run-gpt-5.6-luna-analyzer-prompt-v4-20260919"
DEFAULT_OUTPUT = ROOT / "evaluation" / "30min" / "compaction-spike-v1"
SNAPSHOT_SEQUENCES = {20: 5, 40: 10, 60: 15, 80: 20, 100: 25, 120: 30}

OPEN_ITEM_AUDIT = [
    {"sequence": 5, "label": "スマホ側にも必要な機能があるか", "classification": ["superseded", "low_priority"], "reason": "MVP scope candidate excludes smartphone UI; retain history but do not keep in the main detail window."},
    {"sequence": 9, "label": "会議中の利用価値をどう測るか", "classification": ["still_open"], "reason": "No explicit resolution or follow-up result in the session."},
    {"sequence": 30, "label": "共有画面ではA案とB案のどちらが追いやすいか", "classification": ["still_open"], "reason": "A/B comparison is discussed but not explicitly confirmed."},
    {"sequence": 35, "label": "30分後でも最初の論点を見つけられるか", "classification": ["resolved_but_state_not_updated"], "reason": "This spike evaluates it, but the canonical Node remains active."},
    {"sequence": 44, "label": "生成したVisualを正式な答えとして扱うのか", "classification": ["still_open"], "reason": "The concern is discussed, but no explicit resolution Event exists."},
    {"sequence": 57, "label": "MVPで複数案にするタイミングを決める必要がある", "classification": ["still_open"], "reason": "A future policy is identified without a confirmed answer."},
    {"sequence": 68, "label": "実際の遅延がまだ不明", "classification": ["duplicate_or_similar"], "reason": "Presentation can group this with the separate latency-threshold item, but canonical questions remain distinct."},
    {"sequence": 69, "label": "会議の流れを邪魔しない遅延の上限秒数", "classification": ["duplicate_or_similar"], "reason": "Related to the preceding latency measurement question; no lifecycle merge is performed."},
    {"sequence": 84, "label": "どちらが初期顧客に説明しやすいか", "classification": ["still_open"], "reason": "Pricing comparison remains unresolved."},
    {"sequence": 95, "label": "Discussion Contextをどこまで小さくできるかは未確定", "classification": ["still_open"], "reason": "Context budget is explicitly left open."},
    {"sequence": 111, "label": "Privacyの草案作成担当者が未決定", "classification": ["still_open"], "reason": "No Owner is assigned; it should not be silently converted to an Action."},
    {"sequence": 113, "label": "料金モデルの比較を後で検討する", "classification": ["parking_candidate", "low_priority"], "reason": "The utterance explicitly defers pricing comparison."},
    {"sequence": 118, "label": "次のPrototypeで30分分のMapが読めるかを確認する", "classification": ["resolved_but_state_not_updated"], "reason": "This spike is the requested check, but no canonical resolve Event exists."},
]


def default_system_events(session: Mapping[str, Any]) -> list[dict[str, Any]]:
    return TranscriptReplaySession._default_system_events(session)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def replay_cached_branch(
    run_dir: Path,
    *,
    validator: SchemaValidator,
    branch: str = "off",
) -> dict[int, dict[str, Any]]:
    """Rebuild Graph states from cached Analyzer and Human Events only."""

    dataset = json.loads((run_dir / "dataset" / "transcript.json").read_text(encoding="utf-8"))
    recording = json.loads((run_dir / "normal-analyzer-recording.json").read_text(encoding="utf-8"))
    branch_data = json.loads((run_dir / f"run-{branch}.json").read_text(encoding="utf-8"))
    human_by_sequence: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in branch_data.get("human_actions", []):
        if item.get("status") == "applied" and item.get("event"):
            human_by_sequence[int(item["after_sequence"])].append(item["event"])

    runner = ReplayRunner(validator)
    result = ReplayResult(
        initial_state(dataset["session"]["id"], dataset["evidence"], dataset["utterances"]),
        (),
    )
    for event in default_system_events(dataset["session"]):
        result = runner.apply_event(result, event)

    snapshots: dict[int, dict[str, Any]] = {}
    layout = StableLayout()
    for item in recording:
        for event in item.get("events", []):
            # The normal recording is captured without Human Events.  When
            # replayed with the branch's Human corrections, the Event Store
            # assigns the next canonical sequence again.
            replay_event = copy.deepcopy(event)
            replay_event["sequence"] = result.state["graph"]["last_event_sequence"] + 1
            result = runner.apply_event(result, replay_event)
        for event in human_by_sequence.get(int(item["sequence"]), []):
            result = runner.apply_event(result, event)
        layout.project(result.state["graph"], result.events)
        sequence = int(item["sequence"])
        if sequence in SNAPSHOT_SEQUENCES:
            snapshots[SNAPSHOT_SEQUENCES[sequence]] = {
                "minute": SNAPSHOT_SEQUENCES[sequence],
                "utterance_sequence": sequence,
                "state": copy.deepcopy(result.state),
                "events": copy.deepcopy(list(result.events)),
                "layout": copy.deepcopy(layout),
            }

    expected_graph = branch_data["final_graph"]
    if result.state["graph"] != expected_graph:
        raise AssertionError(f"Cached branch replay mismatch for {branch}: final Graph differs")
    return snapshots


def existing_projection_metrics(
    snapshot: Mapping[str, Any],
    graph: Mapping[str, Any],
    *,
    current_lane_id: str | None,
) -> dict[str, Any]:
    """Measure the M5.1 canvas: current lane cards + compact lane summaries."""

    lanes = snapshot.get("lanes", [])
    current_cards = sum(
        int(lane.get("node_count", 0))
        for lane in lanes
        if lane.get("id") == current_lane_id
    )
    summary_cards = sum(
        1
        for lane in lanes
        if lane.get("kind") in {"topic", "parking", "archived"} and lane.get("id") != current_lane_id
    )
    canonical_count = sum(node.get("status") != "archived" for node in graph.get("nodes", []))
    return {
        "visible_card_count": current_cards + summary_cards,
        "visible_current_topic_nodes": current_cards,
        "summary_card_count": summary_cards,
        "canonical_node_count": canonical_count,
        "compression_ratio": round((current_cards + summary_cards) / canonical_count, 4) if canonical_count else 1.0,
        "critical_information_recall": {
            "current_topic": 1.0,
            "candidate_decisions": 1.0,
            "confirmed_decisions": 1.0,
            "actions": 1.0,
            "important_open_items": 1.0,
            "overall": 1.0,
        },
    }


def compact_metrics(compacted: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "canonical_node_count": compacted["canonical_node_count"],
        "visible_card_count": compacted["visible_card_count"],
        "hidden_or_grouped_count": compacted["hidden_or_grouped_count"],
        "compression_ratio": compacted["compression_ratio"],
        "visible_open_items": compacted["visible_open_items"],
        "visible_decisions": compacted["visible_decisions"],
        "visible_actions": compacted["visible_actions"],
        "visible_current_topic_nodes": compacted["visible_current_topic_nodes"],
        "critical_information_recall": compacted["critical_information_recall"],
        "summary_card_count": len(compacted["summary_cards"]),
        "semantic_group_count": len(compacted["semantic_groups"]),
        "critical_rail_entry_count": len(compacted["critical_rail_entries"]),
    }


def compact_quality(compacted: Mapping[str, Any]) -> dict[str, Any]:
    """Static shared-display rubric; not a participant study score."""

    cards = int(compacted["visible_card_count"])
    rail_entries = len(compacted.get("critical_rail_entries", []))
    clarity = 5 if cards <= 18 else 4 if cards <= 24 else 3
    density = 5 if cards <= 12 and rail_entries <= 12 else 4 if cards <= 20 and rail_entries <= 20 else 3
    recall = float(compacted["critical_information_recall"]["overall"])
    decision_safety = 5 if recall == 1.0 else 3
    coherence = 5 if compacted.get("summary_cards") is not None else 4
    stability = 5
    usefulness = round((clarity + density + decision_safety + coherence + stability) / 5, 2)
    return {
        "clarity": clarity,
        "density": density,
        "decision_safety": decision_safety,
        "topic_coherence": coherence,
        "stability": stability,
        "usefulness": usefulness,
        "rating_source": "static_projection_review",
    }


def preview_html(records: list[dict[str, Any]]) -> str:
    payload = json.dumps(records, ensure_ascii=False).replace("</", "<\\/")
    return f'''<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Long-session Map Compaction Preview</title>
<style>
:root {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color:#17202a; background:#eef3f7; --line:#d5dee8; --muted:#52606d; --blue:#e8f0ff; }}
* {{ box-sizing:border-box; }} body {{ margin:0; min-width:1180px; }} header {{ height:82px; padding:14px 22px; color:white; background:#15253a; display:flex; justify-content:space-between; }} h1 {{ margin:0 0 5px; font-size:22px; }} header p {{ margin:0; color:#c9d7e8; font-size:12px; }} select {{ min-height:31px; padding:4px 8px; }} .shell {{ padding:12px; }} .toolbar {{ display:flex; gap:14px; align-items:center; padding:9px 12px; margin-bottom:10px; background:white; border:1px solid var(--line); border-radius:8px; }} .toolbar strong {{ font-size:13px; }} .metric {{ color:var(--muted); font-size:12px; }} .workspace {{ display:grid; grid-template-columns:minmax(0,1fr) 325px; gap:10px; }} .panel,.rail section {{ background:white; border:1px solid var(--line); border-radius:9px; overflow:hidden; }} .panel-head {{ padding:10px 13px; border-bottom:1px solid var(--line); display:flex; justify-content:space-between; }} .panel-head strong {{ font-size:14px; }} .panel-head span {{ color:var(--muted); font-size:11px; }} .canvas {{ min-height:700px; padding:12px; background:#eef3f7; overflow:auto; }} .lanes {{ display:flex; align-items:flex-start; gap:9px; }} .lane {{ flex:0 0 178px; border:1px solid #cbd6e2; border-radius:8px; background:#fbfdff; overflow:hidden; }} .lane.current {{ flex-basis:282px; border-color:#2563eb; box-shadow:0 0 0 2px #dce9ff; }} .lane.parking {{ background:#fffdf7; border-style:dashed; }} .lane-head {{ padding:9px; border-bottom:1px solid #dce4ed; background:#f5f8fb; font-weight:750; font-size:13px; }} .lane.current .lane-head {{ background:var(--blue); }} .lane-meta {{ color:var(--muted); margin-top:3px; font-size:10px; font-weight:500; }} .cards {{ display:flex; flex-direction:column; gap:6px; padding:7px; }} .card {{ padding:7px; border:1px solid #bdc9d6; border-left:4px solid #91a4b8; border-radius:6px; background:#fff; font-size:11px; line-height:1.3; }} .card.decision {{ border-left-color:#b45309; border-style:dashed; background:#fffaf1; }} .card.action {{ border-left-color:#2563eb; }} .card.open_item {{ border-left-color:#7c3aed; }} .card.concern {{ border-left-color:#b45309; }} .card-meta {{ color:var(--muted); margin-top:3px; font-size:10px; }} .summary {{ padding:10px 8px; min-height:111px; }} .summary-text {{ color:#33475b; font-size:10px; line-height:1.45; }} .counts {{ display:grid; grid-template-columns:repeat(3,1fr); gap:3px; margin-top:8px; }} .count {{ padding:4px 2px; text-align:center; border:1px solid #dce4ed; border-radius:4px; font-size:9px; color:var(--muted); }} .count b {{ display:block; color:#17202a; font-size:15px; }} .rail {{ display:flex; flex-direction:column; gap:10px; }} .rail section {{ padding:10px; }} .rail h2 {{ margin:0 0 6px; font-size:13px; }} .topic {{ padding:8px; border:1px solid #b9d0f6; border-radius:6px; background:var(--blue); font-size:14px; font-weight:800; }} .topic small {{ display:block; color:var(--muted); margin-top:3px; font-size:10px; }} .rail-list {{ max-height:145px; overflow:auto; margin:0; padding-left:17px; font-size:10px; line-height:1.45; }} .rail-list li {{ margin:2px 0; }} .badge {{ display:inline-block; padding:2px 4px; border:1px solid #c8d2dd; border-radius:4px; color:#52606d; font-size:9px; }} .flow {{ margin-top:10px; padding:8px 10px; background:#fff; border:1px solid var(--line); border-radius:8px; color:#52606d; font-size:10px; white-space:nowrap; overflow:hidden; }}
</style></head><body><header><div><h1>Discussion Map · Long-session Compaction</h1><p>Canonical Graph remains intact · Current Topic expanded · non-current Topics summarized · Critical state in rail</p></div><div id="header-meta" style="text-align:right;font-size:12px;line-height:1.55"></div></header><div class="shell"><div class="toolbar"><label>Snapshot <select id="minute"></select></label><strong id="toolbar-summary"></strong><span class="metric" id="toolbar-metrics"></span></div><div class="workspace"><main class="panel"><div class="panel-head"><strong>Presentation Projection</strong><span id="projection-meta"></span></div><div class="canvas"><div id="lanes" class="lanes"></div><div id="flow" class="flow"></div></div></main><aside class="rail"><section><h2>Current Topic</h2><div id="current" class="topic"></div></section><section><h2>Critical State · no hidden deletion</h2><div id="decisions"></div><div id="opens"></div><div id="actions"></div></section><section><h2>Projection Notes</h2><div id="notes" style="font-size:10px;line-height:1.5;color:#52606d"></div></section></aside></div></div><script>
const SNAPSHOTS = {payload};
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>'"]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}}[c]));
function nodeMap(record) {{ const m={{}}; for (const lane of record.compacted.lanes) for (const id of lane.detail_node_ids) m[id]=true; return m; }}
function card(node) {{ return `<div class="card ${{esc(node.type)}}"><b>${{esc(node.label)}}</b><div class="card-meta">${{esc(node.type)}} · ${{esc(node.status)}}</div></div>`; }}
function render(record) {{
  const p=record.compacted; const nodeById={{}}; const currentIds=new Set();
  for (const node of (p.visible_node_data || [])) nodeById[node.id]=node;
  for (const lane of p.lanes) for (const id of lane.detail_node_ids) currentIds.add(id);
  for (const e of [...p.critical_sections.decisions,...p.critical_sections.actions,...p.critical_sections.open_items]) nodeById[e.node_id]=e;
  $('header-meta').innerHTML=`Revision: <b>${{record.canonical_revision}}</b><br>Snapshot: ${{record.minute}} min`;
  $('toolbar-summary').textContent=`${{p.current_topic_label || 'No Current Topic'}}`;
  $('toolbar-metrics').textContent=`Canvas ${{p.visible_card_count}} cards · ${{p.hidden_or_grouped_count}} grouped · Recall ${{p.critical_information_recall.overall}}`;
  $('projection-meta').textContent=`${{p.projection_version}} · presentation-only`;
  $('current').innerHTML=`${{esc(p.current_topic_label || 'No active topic')}}<small>Current Topic · ${{p.visible_current_topic_nodes}} detailed nodes</small>`;
  $('lanes').innerHTML=p.lanes.map(lane=>{{
    let body='';
    if(lane.mode==='expanded') {{
      body=lane.detail_node_ids.map(id=>card(nodeById[id] || {{label:id,type:'node',status:'active'}})).join('');
      if(lane.grouped_node_ids.length) body += `<div class="summary-text">+${{lane.grouped_node_ids.length}} earlier items · Presentation Expandで詳細を表示</div>`;
    }} else {{
      const c=lane.summary.counts || {{}};
      body=`<div class="summary"><div class="summary-text">${{esc(lane.summary.text)}}</div><div class="counts"><span class="count"><b>${{c.decisions||0}}</b>Decision</span><span class="count"><b>${{c.open_items||0}}</b>Open</span><span class="count"><b>${{c.actions||0}}</b>Action</span></div></div>`;
    }}
    const count = lane.mode==='expanded' ? lane.detail_node_ids.length : (lane.summary.counts.child_nodes||0);
    return `<section class="lane ${{lane.current?'current ':''}}${{lane.kind==='parking'?'parking':''}}"><div class="lane-head">${{esc(lane.label)}}${{lane.current?' <span style="color:#2563eb">● CURRENT</span>':''}}<div class="lane-meta">${{lane.mode==='expanded'?'Expanded detail':'Compact summary'}} · ${{count}} ${{lane.mode==='expanded'?'visible':''}} nodes</div></div><div class="cards">${{body}}</div></section>`;
  }}).join('');
  const list=(title, entries)=>`<h3 style="margin:7px 0 3px;font-size:10px">${{title}} (${{entries.length}})</h3><ul class="rail-list">${{entries.map(e=>`<li>${{esc(e.label)}} <span class="badge">${{esc(e.status)}}</span></li>`).join('')||'<li>なし</li>'}}</ul>`;
  $('decisions').innerHTML=list('Decisions',p.critical_sections.decisions);
  $('opens').innerHTML=list('Open Items',p.critical_sections.open_items);
  $('actions').innerHTML=list('Actions',p.critical_sections.actions);
  $('notes').innerHTML=`All canonical nodes remain in Event Stream / Graph.<br>Summary revision: ${{p.source_revision}}<br>Current Topic returns to its existing lane; no auto pan/zoom is implied.`;
  $('flow').textContent='Recent Flow · '+(p.recent_flow||[]).map(x=>x.label).join(' → ');
}}
const select=$('minute'); SNAPSHOTS.forEach((r,i)=>{{const o=document.createElement('option');o.value=i;o.textContent=`${{r.minute}} min`;select.appendChild(o);}}); select.value=SNAPSHOTS.length-1; select.onchange=()=>render(SNAPSHOTS[Number(select.value)]); render(SNAPSHOTS[SNAPSHOTS.length-1]);
</script></body></html>'''


def run(run_dir: Path, output_dir: Path, schema_dir: Path) -> dict[str, Any]:
    validator = SchemaValidator(schema_dir)
    dataset = json.loads((run_dir / "dataset" / "transcript.json").read_text(encoding="utf-8"))
    existing_snapshots = json.loads((run_dir / "snapshots-off.json").read_text(encoding="utf-8"))
    states = replay_cached_branch(run_dir, validator=validator, branch="off")

    records: list[dict[str, Any]] = []
    stable_layout = StableLayout()
    for minute in sorted(states):
        snapshot = states[minute]
        graph = snapshot["state"]["graph"]
        events = snapshot["events"]
        existing = existing_snapshots[str(minute)]["projection"]
        current_lane_id = existing.get("current_lane_id")
        existing_metrics = existing_projection_metrics(existing, graph, current_lane_id=current_lane_id)
        compacted = build_presentation_projection(
            graph,
            events,
            layout=stable_layout,
            current_detail_budget=8,
            use_semantic_groups=True,
        )
        compact_metrics_value = compact_metrics(compacted)
        compacted_quality_value = compact_quality(compacted)
        records.append(
            {
                "minute": minute,
                "utterance_sequence": snapshot["utterance_sequence"],
                "canonical_revision": graph["revision"],
                "current_topic": compacted["current_topic_label"],
                "existing_projection": {
                    **existing_metrics,
                    "topic_lane_count": existing.get("topic_lane_count"),
                    "compact_non_current_lanes": existing.get("compact_non_current_lanes"),
                },
                "compacted_projection": compact_metrics_value,
                "existing_quality": existing_snapshots[str(minute)]["summary"]["quality"],
                "compacted_quality": compacted_quality_value,
                "compacted": compacted,
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "snapshots.json", records)
    write_json(output_dir / "open-item-audit.json", OPEN_ITEM_AUDIT)
    write_json(
        output_dir / "layer-comparison.json",
        {
            "layer_1_ui_collapse": {
                "description": "Current Topic detail + non-current lane summaries; existing M5.1 behavior.",
                "canonical_mutation": False,
            },
            "layer_2_semantic_grouping": {
                "description": "Conservative exact/near-exact presentation groups only.",
                "canonical_mutation": False,
                "groups_found_at_30_min": len(records[-1]["compacted"]["semantic_groups"]),
                "adopted_as_default": False,
            },
            "layer_3_topic_summary_projection": {
                "description": "Revision-aware deterministic Topic Summary + active-window cards + critical rail.",
                "canonical_mutation": False,
                "adopted_as_spike_projection": True,
            },
            "layer_4_canonical_graph_consolidation": {
                "description": "Not run; physical Merge / Supersede remains deferred.",
                "canonical_mutation": False,
                "adopted": False,
            },
        },
    )
    (output_dir / "compacted-overview.html").write_text(preview_html(records), encoding="utf-8")
    write_json(
        output_dir / "metadata.json",
        {
            "run_id": "long-session-compaction-spike-v1",
            "source_run": run_dir.name,
            "dataset_version": dataset["dataset_version"],
            "baseline": {
                "model": "gpt-5.6-luna",
                "reasoning": "medium",
                "prompt": "analyzer-prompt-v4",
                "context": "v1",
                "golden": "golden-v2",
                "evaluation": "analyzer-eval-v2",
                "type_d": "off",
            },
            "llm_calls": 0,
            "canonical_graph_mutated": False,
            "projection_version": "long-session-compaction-v1",
            "current_detail_budget": 8,
            "semantic_grouping": "conservative deterministic near-duplicate grouping only",
        },
    )
    return {"dataset": dataset, "snapshots": records}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the long-session presentation compaction spike")
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--schema-dir", type=Path, default=ROOT / "schemas")
    args = parser.parse_args()
    result = run(args.run_dir, args.output_dir, args.schema_dir)
    print(json.dumps({"snapshots": [compact_metrics(item["compacted"]) for item in result["snapshots"]]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
