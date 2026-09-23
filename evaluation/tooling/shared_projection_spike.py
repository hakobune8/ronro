"""Offline only. No network, provider calls, or production UI imports.

Input: private retained /api/live JSON and saved snapshot directory.
Output: private label-only HTML and metrics; never raw transcripts.
Run from repository root with PYTHONPATH=.
"""
import argparse
import copy
import hashlib
import html
import json
import statistics
from datetime import datetime
from pathlib import Path

from prototype.layout import StableLayout, map_projection
from prototype.replay import ReplayRunner, ReplayResult
from prototype.materializer import initial_state
from prototype.schema import SchemaValidator

ORDINARY = {'idea', 'option', 'concern'}
GENERIC = {'その他', '未分類', 'others', 'other', 'misc', 'other discussion items'}
MODES = ('existing', 'latest', 'persistent', 'stable')


def stamp(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp()


def active(n):
    return n['status'] not in {'archived', 'resolved', 'completed', 'revoked', 'parked'}


def original_active(n):
    # Match shared.html exactly, including its lack of an explicit parked filter.
    return n['status'] not in {'archived', 'resolved', 'completed', 'revoked'}


def persistent(n):
    return active(n) and n['type'] in {'decision', 'open_item', 'action'}


def generic(label):
    return label.strip().casefold() in GENERIC


def headings(graph, mode):
    if mode != 'existing':
        return []  # Meaning comes from existing node labels, not invented titles.
    current = graph['current_topic'].get('primary_topic_id')
    return [n['label'] for n in graph['nodes'] if n['id'] == current]


def choose(graph, projection, events, mode, prior=()):
    """Prior is always reconstructed by replay, never a browser/session cache.

    Six TOTAL slots for B/C. Persistent overflow is explicitly reported:
    this spike does not claim to solve >6 simultaneous important states.
    Recency is the last node source-event sequence (not Topic focus time).
    """
    nodes = {n['id']: n for n in graph['nodes']}
    sequence = {e['event_id']: e['sequence'] for e in events}
    rank = lambda n: (max((sequence.get(i, 0) for i in n['source_event_ids']), default=0), n['id'])
    lane = next((l for l in projection['lanes'] if l['current']), None)
    ids = lane['node_ids'] if lane else []
    ordinary = [nodes[i] for i in ids if (original_active(nodes[i]) if mode == 'existing' else active(nodes[i])) and nodes[i]['type'] in ORDINARY]
    if mode == 'existing':
        return [n['id'] for n in ordinary[:6]], 0
    if mode == 'latest':
        return [n['id'] for n in sorted(ordinary, key=rank, reverse=True)[:6]], 0
    # Generic/no-topic states expose semantic node labels, never bucket titles.
    # Unassigned recent nodes remain eligible without inventing membership.
    extra = [i for l in projection['lanes'] if l['kind'] == 'unassigned' for i in l['node_ids']]
    ordinary = list({n['id']: n for n in ordinary + [nodes[i] for i in extra if active(nodes[i]) and nodes[i]['type'] in ORDINARY]}.values())
    if mode == 'stable':
        # Current/recent horizon is not confined to a stale canonical heading.
        # A Topic focus switch alone must not resurrect old ordinary cards.
        ordinary = [n for n in nodes.values() if active(n) and n['type'] in ORDINARY]
    important = sorted([n for n in nodes.values() if persistent(n)], key=lambda n: (n['created_at'], n['id']))
    desired = [n['id'] for n in important[:6]]
    desired += [n['id'] for n in sorted(ordinary, key=rank, reverse=True)[:6-len(desired)]]
    if mode == 'persistent':
        return desired, max(0, len(important)-6)
    slots = list(prior) + [None] * (6-len(prior))
    slots = [i if i in desired else None for i in slots]
    for i in desired:
        if i not in slots:
            slots[slots.index(None)] = i
    return slots, max(0, len(important)-6)


def replay(data, validator):
    runner = ReplayRunner(validator)
    result = ReplayResult(initial_state(data['state']['graph']['session_id'], data['state']['evidence'], data['state']['utterances']), ())
    layout = StableLayout()
    history = []
    slots = []
    for event in data['events']:
        result = runner.apply_event(result, event)
        graph = result.state['graph']
        projection = map_projection(result.state, result.events, layout)
        choices = {}
        for mode in MODES:
            choices[mode], overflow = choose(graph, projection, result.events, mode, slots)
        slots = choices['stable']
        history.append({'revision': graph['revision'], 'sequence': event['sequence'], 'graph': copy.deepcopy(graph), 'map': projection, 'choices': choices, 'overflow': overflow})
    return history


def difference(before, after):
    old, new = set(before)-{None}, set(after)-{None}
    return {'entered': sorted(new-old), 'left': sorted(old-new), 'unchanged': len(old & new),
            'survivor_moves': sum(before.index(i) != after.index(i) for i in old & new)}


def fixture_checks(root, validator):
    checks = []
    for directory in sorted((root/'evaluation/fixtures').glob('*')):
        if not (directory/'expected-final-graph.json').exists():
            continue
        state = json.loads((directory/'expected-final-graph.json').read_text())
        data = {'state': state, 'events': json.loads((directory/'events.json').read_text())}
        baseline = json.dumps(data, sort_keys=True)
        history = replay(data, validator)
        again = replay(data, validator)
        assert [x['choices'] for x in history] == [x['choices'] for x in again]
        assert baseline == json.dumps(data, sort_keys=True)
        for row in history:
            required = {n['id'] for n in row['graph']['nodes'] if persistent(n)}
            if len(required) <= 6:
                assert required <= set(row['choices']['stable'])
        checks.append(directory.name + ': immutable, deterministic, important-state retention PASS')
        if directory.name == '002-topic-return':
            assert all(not any(row['choices']['stable']) for row in history)
            assert history[-1]['graph']['current_topic']['primary_topic_id'] == history[3]['graph']['current_topic']['primary_topic_id']
            checks.append('Topic-return fixture: canonical return preserved; no invented recent cards PASS')
    # Capacity pressure on existing synthetic states, never on T1 data.
    for name in ['001-basic-discussion', '003-decision-confirm', '005-action-item', '012-relation-constraints', '013-open-item-lifecycle']:
        state = json.loads((root/'evaluation/fixtures'/name/'expected-final-graph.json').read_text())
        events = json.loads((root/'evaluation/fixtures'/name/'events.json').read_text())
        graph = copy.deepcopy(state['graph'])
        important = {n['id'] for n in graph['nodes'] if persistent(n)}
        projection = {'lanes': [{'current': True, 'kind': 'unassigned', 'label': 'その他', 'node_ids': []}]}
        slots = []
        for k in range(10):
            eid = f'synthetic-pressure-{k}'
            events.append({'event_id': eid, 'sequence': 1000+k})
            graph['nodes'].append({'id': eid, 'type': 'idea', 'label': f'検証用の最近の論点{k}', 'status': 'active', 'created_at': '2026-01-01T00:00:00Z', 'source_event_ids': [eid]})
            projection['lanes'][0]['node_ids'].append(eid)
            previous = slots
            slots, _ = choose(graph, projection, events, 'stable', previous)
            assert important <= set(slots)
            assert eid in slots
            assert difference(previous, slots)['survivor_moves'] == 0
        assert 'synthetic-pressure-0' not in slots
        assert any(n['id'] == 'synthetic-pressure-0' for n in graph['nodes'])
        assert generic(projection['lanes'][0]['label'])
        assert not headings(graph, 'stable')
        checks.append(name + ': ten newer Ideas, important state survives, old Idea retained in Graph, fixed slots PASS')
        # An old node becomes recent ONLY through a node-related activity Event,
        # not because a focus Event was appended or a heading was renamed.
        events.append({'event_id': 'focus-only', 'sequence': 2000})
        projection['lanes'][0]['kind'] = 'topic'
        projection['lanes'][0]['node_ids'] = ['synthetic-pressure-0']
        same, _ = choose(graph, projection, events, 'stable', slots)
        assert same == slots
        first = next(n for n in graph['nodes'] if n['id'] == 'synthetic-pressure-0')
        first['source_event_ids'].append('renewed-node-activity')
        events.append({'event_id': 'renewed-node-activity', 'sequence': 2001})
        returned, _ = choose(graph, projection, events, 'stable', slots)
        assert first['id'] in returned
        assert difference(slots, returned)['survivor_moves'] == 0
        checks.append(name + ': renewed node activity re-enters; focus alone does not refresh recency PASS')
    return checks


def run(args):
    root = Path(__file__).resolve().parents[2]
    validator = SchemaValidator(root/'schemas')
    checks = fixture_checks(root, validator)
    data = json.loads(args.live.read_text())
    source_hash = hashlib.sha256(args.live.read_bytes()).hexdigest()
    history = replay(data, validator)
    assert history[-1]['graph'] == data['state']['graph']
    assert [h['choices'] for h in history] == [h['choices'] for h in replay(data, validator)]
    report = {'checks': checks, 'input_sha256': source_hash, 'snapshots': {}, 'churn': {}}
    cards = {n['id']: n for n in data['state']['graph']['nodes']}
    for mode in MODES:
        prev = []
        replacements = moves = 0
        for row in history:
            nxt = row['choices'][mode]
            delta = difference(prev, nxt)
            replacements += min(len(delta['left']), len(delta['entered']))
            moves += delta['survivor_moves']
            prev = nxt
        report['churn'][mode] = {'replacements': replacements, 'per_minute': round(replacements/15, 3), 'survivor_moves': moves}
    previous = {mode: [] for mode in MODES}
    for minute in (5, 10, 15):
        saved = json.loads((args.snapshots/f'{minute:02}min.json').read_text())
        # The 15m saved projection can lag Graph; reproduce saved baseline,
        # and compare candidates at the saved CANONICAL graph revision.
        graph = saved['graph']
        row = next(h for h in reversed(history) if h['revision'] == graph['revision'])
        assert row['graph'] == graph
        results = {}
        for mode in MODES:
            ids = row['choices'][mode]
            if mode == 'existing':
                ids, _ = choose(graph, saved['projection'], data['events'], mode)
            items = [cards[i] for i in ids if i]
            ages = [max(0, args.start+minute*60-stamp(n['created_at'])) for n in items if n['type'] in ORDINARY]
            delta = difference(previous[mode], ids)
            results[mode] = {'slots': ids, 'headings': headings(graph, mode), 'cards': [{'label': n['label'], 'type': n['type'], 'status': n['status'], 'age_s': round(max(0, args.start+minute*60-stamp(n['created_at'])),1)} for n in items],
                             'median_age': round(statistics.median(ages),1) if ages else None, 'max_age': round(max(ages),1) if ages else None,
                             **delta, 'generic_headings': sum(generic(label) for label in headings(graph, mode)), 'human_coverage': None, 'human_explanation': None}
            previous[mode] = ids
        report['snapshots'][minute] = results
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out/'metrics.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    sections = []
    summaries = {5:'交通事業者・組織間連携とデータ活用',10:'祭りを経て、住民参加と分野横断のつながり',15:'地域間連携の総括と災害時の相互支援'}
    names = {'existing':'現行：先頭六枚', 'latest':'A：Latest Six', 'persistent':'B：Recency + Persistent', 'stable':'C：Stable Recency + Persistent'}
    esc = html.escape
    for minute, results in report['snapshots'].items():
        sections.append(f'<h2>{minute}分 — {summaries[minute]}</h2><p>比較の文脈は診断者要約。Human評価は未記入。各画面は16:9。横比較後、個別画面を拡大して確認してください。</p>')
        for mode in MODES:
            r = results[mode]
            header = '<b class="brand">論路</b><h2>'+esc(' / '.join(r['headings']))+'</h2>' if mode == 'existing' else '<span class="status">● 聞いています</span>'
            body = ''.join(f'<article class="{c["type"]}">{esc(c["label"])}'+(f'<small>{ {"decision":"決定の状態を確認", "open_item":"未解決", "action":"次の対応"}.get(c["type"], "")}</small>' if c['type'] not in ORDINARY else '')+'</article>' for c in r['cards'])
            footer = '<footer>普段どおりに話してください。論点図は議論とともに更新されます。</footer>' if mode == 'existing' else ''
            sections.append(f'<h3>{names[mode]}</h3><section class="screen">{header}<div class="cards">{body}</div>{footer}</section><p>普通カード年齢 中央値 {r["median_age"]}秒 / 最大 {r["max_age"]}秒。前スナップショットとの共通 {r["unchanged"]}枚。</p><details><summary>カード年齢・出入り（診断情報／参加者画面外）</summary><ul>'+''.join(f'<li>{esc(c["label"])} — {c["age_s"]}秒</li>' for c in r['cards'])+'</ul><p>入場: '+esc(' / '.join(cards[i]['label'] for i in r['entered']))+'</p><p>退出: '+esc(' / '.join(cards[i]['label'] for i in r['left']))+'</p></details><p>Human: 現在地Coverage 1–5: ____ / Explanation Cost 1–5: ____ / 理由: __________________</p>')
    document = '''<!doctype html><meta charset="utf-8"><title>T1 Projection — Private Human Review</title><style>
    *{box-sizing:border-box}body{font-family:system-ui,sans-serif;background:#e7ebef;color:#132638;margin:32px auto;max-width:1280px;padding:20px}h2{margin-top:48px}p{line-height:1.7}.screen{aspect-ratio:16/9;background:#fcfdfd;padding:30px;display:flex;flex-direction:column;border:1px solid #ccd5dd;overflow:hidden}.screen h2{margin:10px 0 16px;font-size:34px}.status{font-size:16px;color:#426858;text-align:right;display:block;margin-bottom:22px}.brand{font-size:28px}.cards{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:repeat(3,1fr);gap:18px;flex:1;min-height:0}article{padding:18px 22px;font-size:clamp(20px,2.2vw,30px);line-height:1.35;border-left:5px solid #61869b;background:#edf3f6;overflow:auto;overflow-wrap:anywhere}article.concern{border-color:#b58942}article.decision,article.open_item,article.action{background:#fff1d8}small{display:block;font-size:16px}footer{margin-top:18px;font-size:16px;color:#566676}details{margin:18px 0}@media print{.screen{break-inside:avoid}}
    </style><h1>T1 保存Graph：Projection比較</h1><p>PRIVATE / publication review pending。音声・全文Transcriptなし。現行画面は選択ルールを正確に再現した簡略モックで、Productionのpixel-perfect複製ではありません。候補は未採用。3–5mでの実機可読性は未検証です。</p>'''+''.join(sections)
    (args.out/'review.html').write_text(document)
    # Six-screen short form; full four-way comparison remains in review.html.
    short = document.split('</p>', 1)[0] + '</p>'
    short += ''.join(section for i, section in enumerate(sections) if i % 5 in (0, 1, 4))
    (args.out/'compare.html').write_text(short)
    assert hashlib.sha256(args.live.read_bytes()).hexdigest() == source_hash
    print(json.dumps({'checks':len(checks), 'churn':report['churn'], 'ages':{m:{k:(v['median_age'],v['max_age']) for k,v in r.items()} for m,r in report['snapshots'].items()}}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', type=Path, required=True)
    parser.add_argument('--snapshots', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--start', type=float, required=True, help='Recorded source Play epoch seconds')
    run(parser.parse_args())
