"""Private offline review artifact. Never imported by the Product runtime."""
import argparse
import copy
import hashlib
import html
import json
import statistics
from pathlib import Path

from shared_projection_spike import (
    ORDINARY, active, persistent, replay, choose, difference, stamp,
)
from prototype.schema import SchemaValidator

RAIL_TYPES = ('decision', 'open_item', 'action')
RAIL_GROUPS = ('candidate', 'confirmed', 'open_item', 'action')
RAIL_CAPACITY = 1  # One per category; no reduction in typography on overflow.


def in_rail_group(node, group):
    if not persistent(node):
        return False
    if group in ('candidate', 'confirmed'):
        return node['type'] == 'decision' and node['status'] == group
    return node['type'] == group


def final_projection(graph, events, previous=()):
    sequences = {e['event_id']: e['sequence'] for e in events}
    ordinary = [n for n in graph['nodes'] if active(n) and n['type'] in ORDINARY]
    rank = lambda n: (max((sequences.get(e, 0) for e in n['source_event_ids']), default=0), n['id'])
    selected = [n['id'] for n in sorted(ordinary, key=rank, reverse=True)[:6]]
    slots = list(previous) + [None]*(6-len(previous))
    slots = [i if i in selected else None for i in slots]
    for node_id in selected:
        if node_id not in slots:
            slots[slots.index(None)] = node_id
    rail = {}
    for kind in RAIL_GROUPS:
        items = sorted([n for n in graph['nodes'] if in_rail_group(n, kind)],
                       key=lambda n: (n['created_at'], n['id']))
        rail[kind] = {'ids': [n['id'] for n in items[:RAIL_CAPACITY]],
                      'eligible': len(items), 'overflow': max(0, len(items)-RAIL_CAPACITY)}
    return {'slots': slots, 'eligible': len(ordinary), 'visible': len(selected),
            'overflow': len(ordinary)-len(selected), 'rail': rail}


def project_history(data, validator):
    history = replay(data, validator)
    previous = []
    for row in history:
        events = [e for e in data['events'] if e['sequence'] <= row['sequence']]
        row['final'] = final_projection(row['graph'], events, previous)
        previous = row['final']['slots']
    return history


def serial_view(graph, slots, eligible, rail, now):
    nodes = {n['id']: n for n in graph['nodes']}
    def card(i):
        if not i:
            return None
        n = nodes[i]
        return {'id': i, 'label': n['label'], 'type': n['type'], 'status': n['status'],
                'age': round(max(0, now-stamp(n['created_at'])), 1)}
    cards = [card(i) for i in slots]
    ages = [n['age'] for n in cards if n and n['type'] in ORDINARY]
    topic = next((n['label'] for n in graph['nodes'] if n['id'] == graph['current_topic'].get('primary_topic_id')), '')
    return {'cards': cards, 'topic': topic, 'eligible': eligible,
            'visible': sum(n is not None for n in cards),
            'overflow': max(0, eligible-sum(n is not None for n in cards)),
            'rail': {k: {'cards': [card(i) for i in v['ids']], 'overflow': v['overflow'], 'eligible': v['eligible']} for k,v in rail.items()},
            'median_age': statistics.median(ages) if ages else None,
            'max_age': max(ages) if ages else None}


def synthetic(root):
    """Presentation-only pressure states derived from public synthetic fixtures."""
    load = lambda name: json.loads((root/'evaluation/fixtures'/name/'expected-final-graph.json').read_text())['graph']
    base = copy.deepcopy(load('001-basic-discussion'))
    action = load('005-action-item')
    decision = load('012-relation-constraints')
    confirmed = next(n for n in load('003-decision-confirm')['nodes'] if n['type'] == 'decision' and n['status'] == 'confirmed')
    seeds = {k: next(n for n in (action if k != 'decision' else decision)['nodes'] if n['type'] == k and persistent(n)) for k in RAIL_TYPES}
    labels = ['点検の対象範囲をそろえる', '現場写真の共有方法を検討する', '地域ごとの状況を比較する',
              '移動時間を減らす方法を考える', '資料の見つけやすさを改善する', '関係者の連絡経路を確認する',
              '住民が参加しやすい時間帯を考える', '既存の設備を活用する', '地域間で経験を共有する']
    events = []
    ordinary = []
    for i, label in enumerate(labels):
        eid = f'pressure-{i}'
        events.append({'event_id': eid, 'sequence': i+1})
        ordinary.append({'id': eid, 'type': 'idea', 'label': label, 'status': 'active',
                         'created_at': f'2026-01-01T00:00:{i:02}Z', 'source_event_ids': [eid]})
    results = []
    for count in (1, 3, 9):
        g = copy.deepcopy(base)
        g['nodes'] = copy.deepcopy(ordinary)
        g['edges'] = []  # Derived presentation fixture, not a canonical replay.
        for i in range(count):
            kind = RAIL_TYPES[i % 3] if count > 1 else 'action'
            node = copy.deepcopy(confirmed if kind == 'decision' and count == 3 else seeds[kind]); node['id'] = f'rail-{i}'
            node['created_at'] = f'2026-01-01T00:01:{i:02}Z'
            node['source_event_ids'] = [f'rail-event-{i}']
            node['label'] = {
                'decision': ['資料の共有先を一本化する', '点検結果を同じ様式でまとめる', '連絡会を継続する'],
                'open_item': ['参加者の移動手段は未整理', '費用の分担方法が残っている', '写真の利用範囲を確認する'],
                'action': ['関係資料を集める', '次回の候補日を確認する', '現場の状況を共有する'],
            }[kind][i//3 if count > 1 else 0]
            # Explicit synthetic states, not inferred decisions from T1.
            if kind == 'decision' and i >= 3:
                node['status'] = 'confirmed'
            g['nodes'].append(node)
        results.append((f'persistent-{count}', g, events))
    return results


def checks(root, validator):
    passed = []
    for name,g,events in synthetic(root):
        before = copy.deepcopy(g)
        p = final_projection(g, events)
        assert p['eligible'] == 9 and p['visible'] == 6 and p['overflow'] == 3
        assert sum(v['eligible'] for v in p['rail'].values()) == int(name.split('-')[1])
        assert all(v['eligible'] == len(v['ids']) + v['overflow'] for v in p['rail'].values())
        assert len([i for i in p['slots'] if i]) == 6  # Rail never consumes slots.
        assert g == before and p == final_projection(g, events)
        if name == 'persistent-9':
            assert p['rail']['candidate']['eligible'] == 1
            assert p['rail']['confirmed']['eligible'] == 2
            assert p['rail']['candidate']['ids'] and p['rail']['confirmed']['ids']
            assert set(p['rail']['candidate']['ids']).isdisjoint(p['rail']['confirmed']['ids'])
        # Rail lifecycle updates must never take away an ordinary slot.
        changed = copy.deepcopy(g)
        first = next(n for n in changed['nodes'] if persistent(n))
        first['status'] = {'decision': 'revoked', 'open_item': 'resolved', 'action': 'completed'}[first['type']]
        after = final_projection(changed, events, p['slots'])
        assert after['slots'] == p['slots']
        assert sum(v['eligible'] for v in after['rail'].values()) == sum(v['eligible'] for v in p['rail'].values())-1
        passed.append(name+': six ordinary slots + exact rail/ordinary overflow + determinism + immutability')
    _,g,events = synthetic(root)[1]
    previous = final_projection(g, events)
    # Topic return alone has no effect; renewed actual node activity does.
    events = events + [{'event_id': 'focus-return', 'sequence': 100}]
    g['current_topic']['primary_topic_id'] = 'old-topic'
    assert final_projection(g, events, previous['slots']) == previous
    g['nodes'][0]['source_event_ids'].append('renewed')
    events.append({'event_id': 'renewed', 'sequence': 101})
    renewed = final_projection(g, events, previous['slots'])
    assert g['nodes'][0]['id'] in renewed['slots']
    assert difference(previous['slots'], renewed['slots'])['survivor_moves'] == 0
    assert renewed['rail'] == previous['rail']
    passed.append('renewed activity returns; Topic switch alone does not revive old content; rail unchanged')
    for directory in sorted((root/'evaluation/fixtures').glob('*')):
        if not (directory/'expected-final-graph.json').exists():
            continue
        data = {'state': json.loads((directory/'expected-final-graph.json').read_text()),
                'events': json.loads((directory/'events.json').read_text())}
        first = project_history(data, validator)
        again = project_history(data, validator)
        assert [r['final'] for r in first] == [r['final'] for r in again]
        for row in first:
            p = row['final']
            assert p['eligible'] == p['visible'] + p['overflow']
            assert p['visible'] <= 6
            for kind in RAIL_GROUPS:
                assert p['rail'][kind]['eligible'] == sum(in_rail_group(n, kind) for n in row['graph']['nodes'])
        passed.append(directory.name+': deterministic saved-event replay, capacity and lifecycle filtering')
    return passed


def main(args):
    root = Path(__file__).resolve().parents[2]
    validator = SchemaValidator(root/'schemas')
    input_bytes = args.live.read_bytes()
    data = json.loads(input_bytes)
    history = project_history(data, validator)
    assert history[-1]['graph'] == data['state']['graph']
    second = project_history(data, validator)
    assert [r['final'] for r in history] == [r['final'] for r in second]
    metrics = {'checks': checks(root, validator), 'source_sha256': hashlib.sha256(input_bytes).hexdigest(),
               'churn': {}, 'snapshots': {}}
    prior = []; replaced = moves = 0
    for row in history:
        d = difference(prior, row['final']['slots'])
        replaced += min(len(d['entered']), len(d['left']))
        moves += d['survivor_moves']; prior = row['final']['slots']
    metrics['churn'] = {'replacements': replaced, 'replacements_per_minute': replaced/15, 'survivor_moves': moves}
    cases = []
    summaries = {5:'交通・組織間連携とデータ活用',10:'祭りを経て、住民参加と分野横断のつながり',15:'地域間連携の総括と災害時の相互支援'}
    previous_checkpoint = []
    for minute in (5, 10, 15):
        saved = json.loads((args.snapshots/f'{minute:02}min.json').read_text())
        row = next(r for r in reversed(history) if r['revision'] == saved['graph']['revision'])
        assert row['graph'] == saved['graph']
        g = row['graph']; p = row['final']; now = args.start+60*minute
        events = [e for e in data['events'] if e['sequence'] <= row['sequence']]
        old, _ = choose(g, saved['projection'], events, 'existing')
        lane = next(l for l in saved['projection']['lanes'] if l['current'])
        nodes = {n['id']: n for n in g['nodes']}
        old_eligible = sum(nodes[i]['type'] in ORDINARY and active(nodes[i]) for i in lane['node_ids'])
        empty = {k: {'ids': [], 'eligible': 0, 'overflow': 0} for k in RAIL_GROUPS}
        views = {'current': serial_view(g, old, old_eligible, empty, now),
                 'previous': serial_view(g, row['choices']['stable'], p['eligible'], empty, now),
                 'final': serial_view(g, p['slots'], p['eligible'], p['rail'], now)}
        metrics['snapshots'][minute] = {'counts': {k:p[k] for k in ('eligible','visible','overflow')},
            'median_age': views['final']['median_age'], 'max_age': views['final']['max_age'],
            'changes': difference(previous_checkpoint,p['slots'])}
        previous_checkpoint=p['slots']
        cases.append({'id': str(minute), 'title': f'T1 · {minute}分', 'summary': summaries[minute], 'views': views})
    for name,g,events in synthetic(root):
        p = final_projection(g,events)
        empty = {k: {'ids': [], 'eligible': 0, 'overflow': 0} for k in RAIL_GROUPS}
        mapping = {'lanes':[{'current':True, 'kind':'unassigned', 'node_ids':[n['id'] for n in g['nodes']]}]}
        previous,_=choose(g,mapping,events,'stable')
        old,_=choose(g,mapping,events,'existing')
        now=stamp('2026-01-01T00:05:00Z')
        cases.append({'id':name,'title':f'合成 · 重要状態{sum(v["eligible"] for v in p["rail"].values())}件',
                      'summary':'既存fixtureから派生した表示容量テスト。T1には含まれません。',
                      'views': {'current':serial_view(g,old,p['eligible'],p['rail'],now),
                                'previous':serial_view(g,previous,len([n for n in g['nodes'] if active(n)]),empty,now),
                                'final':serial_view(g,p['slots'],p['eligible'],p['rail'],now)}})
    payload = {'cases':cases,'metrics':metrics}
    args.out.mkdir(parents=True, exist_ok=False)
    template = Path(__file__).with_name('final_shared_review.html').read_text()
    encoded = json.dumps(payload,ensure_ascii=False).replace('<','\\u003c')
    (args.out/'index.html').write_text(template.replace('__REVIEW_DATA__',encoded))
    (args.out/'metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2))
    assert args.live.read_bytes() == input_bytes
    print(json.dumps(metrics,ensure_ascii=False))


if __name__ == '__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--live',type=Path,required=True)
    ap.add_argument('--snapshots',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--start',type=float,required=True)
    main(ap.parse_args())
