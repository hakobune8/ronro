import copy
import json
import unittest
import re
import shutil
import subprocess
from pathlib import Path

from prototype.shared_projection import SharedProjection, select_shared
from prototype.layout import recent_topic_flow

ROOT = Path(__file__).resolve().parents[1]


class SharedProjectionTests(unittest.TestCase):
    def ordinary(self, count=9):
        nodes = [{'id': str(i), 'type': 'idea', 'status': 'active', 'label': str(i),
                  'created_at': f'2026-01-01T00:00:{i:02}Z', 'source_event_ids': [str(i)]} for i in range(count)]
        return {'nodes': nodes}, [{'event_id': str(i), 'sequence': i+1} for i in range(count)]

    def test_six_overflow_and_stable_slots(self):
        graph, events = self.ordinary()
        prior = []; old = copy.deepcopy(graph)
        for size in range(1,10):
            p = select_shared({'nodes': graph['nodes'][:size]}, events[:size], prior)
            for node_id in set(prior) & set(p['slots']) - {None}:
                self.assertEqual(prior.index(node_id), p['slots'].index(node_id))
            prior = p['slots']
        self.assertEqual((p['eligible'], len([i for i in prior if i]), p['overflow']), (9,6,3))
        self.assertEqual(graph,old)

    def test_rail_groups_dont_compete_and_lifecycle(self):
        graph, events = self.ordinary()
        base = select_shared(graph,events)
        for i,(kind,status) in enumerate([('decision','candidate'),('decision','confirmed'),('open_item','active'),('action','active'),('decision','confirmed')]):
            graph['nodes'].append({'id': 'p'+str(i),'type':kind,'status':status,'label':'内容','created_at':str(i),'source_event_ids':[]})
        p=select_shared(graph,events,base['slots'])
        self.assertEqual(p['slots'],base['slots'])
        self.assertEqual(p['rail']['candidate']['node_ids'],['p0'])
        self.assertEqual(p['rail']['confirmed']['node_ids'],['p1'])
        self.assertEqual(p['rail']['confirmed']['overflow'],1)
        for n in graph['nodes']:
            if n['id']=='p1': n['status']='revoked'
            if n['id']=='p2': n['status']='resolved'
            if n['id']=='p3': n['status']='completed'
        p=select_shared(graph,events,p['slots'])
        self.assertEqual(p['rail']['confirmed']['node_ids'],['p4'])
        self.assertFalse(p['rail']['open_item']['node_ids'])
        self.assertFalse(p['rail']['action']['node_ids'])

    def test_renewed_activity_not_topic_focus_refreshes(self):
        g,e=self.ordinary();p=select_shared(g,e)
        e.append({'event_id':'focus','sequence':100})
        self.assertEqual(select_shared(g,e,p['slots']),p)
        g['nodes'][0]['source_event_ids'].append('renewed');e.append({'event_id':'renewed','sequence':101})
        new=select_shared(g,e,p['slots']);self.assertIn('0',new['slots'])

    def test_fixture_replay_deterministic_reset_and_no_mutation(self):
        from prototype.replay import ReplayRunner, ReplayResult
        from prototype.materializer import initial_state
        from prototype.schema import SchemaValidator
        runner=ReplayRunner(SchemaValidator(ROOT/'schemas'))
        for path in sorted((ROOT/'evaluation/fixtures').glob('*/expected-final-graph.json')):
            with self.subTest(fixture=path.parent.name):
                state=json.loads(path.read_text());events=json.loads((path.parent/'events.json').read_text())
                before=copy.deepcopy(state);cached=SharedProjection()
                result=ReplayResult(initial_state(state['graph']['session_id'],state['evidence'],state['utterances']),())
                for event in events:
                    result=runner.apply_event(result,event)
                    self.assertEqual(cached.project(result.state,result.events),SharedProjection().project(result.state,result.events))
                self.assertEqual(cached.project(state,events),SharedProjection().project(state,events))
                self.assertEqual(state,before)
                cached.reset()
                self.assertEqual(cached.project(state,events),SharedProjection().project(state,events))

    def test_actual_topic_return_flow(self):
        path=ROOT/'evaluation/fixtures/002-topic-return'
        state=json.loads((path/'expected-final-graph.json').read_text())
        events=json.loads((path/'events.json').read_text())
        flow=recent_topic_flow(events,state['graph'])
        self.assertEqual(len(flow),4)
        self.assertEqual(flow[0]['topic_id'],flow[-1]['topic_id'])

    @unittest.skipUnless(shutil.which('node'), 'Node.js needed for DOM logic smoke')
    def test_shared_dom_logic_without_browser_rendering(self):
        source=(ROOT/'prototype/web/shared.html').read_text()
        js=re.search(r'<script>(.*?)</script>',source,re.S).group(1)
        js=js.replace('    refresh();', '').replace('    if (!demoFixture) window.setInterval(refresh, 1000);','')
        harness=r'''
const assert=require('node:assert/strict');
const elements=new Map();
function element(key){if(!elements.has(key))elements.set(key,{innerHTML:'',textContent:'',hidden:false,classList:{toggle(){},add(){}}});return elements.get(key);}
global.document={getElementById:element,querySelector:element,querySelectorAll:()=>[],fonts:{ready:Promise.resolve()},documentElement:element('html')};
global.window={location:{search:''},addEventListener(){}};
'''+js+r'''
const graph={nodes:[{id:'a',type:'idea',label:'意味 <script>',status:'active'}, {id:'t1',type:'topic',label:'交通'}, {id:'t2',type:'topic',label:'住民参加'}],current_topic:{primary_topic_id:'t1'}};
const rail={candidate:{node_ids:['a'],overflow:2},confirmed:{node_ids:['a'],overflow:0},open_item:{node_ids:[],overflow:0},action:{node_ids:[],overflow:0}};
const snapshot={state:{graph},map:{shared:{slots:['a',null,null,null,null,null],overflow:3,rail},recent_flow:[{topic_id:'t1',label:'交通'},{topic_id:'t2',label:'住民参加'},{topic_id:'t1',label:'交通'}]},live_state:{runtime_state:'active'}};
renderShared(snapshot);
assert(element('shared-main').innerHTML.includes('確定事項'));
assert(element('shared-main').innerHTML.includes('決定候補'));
assert(element('shared-main').innerHTML.includes('ほか3件'));
assert(element('shared-main').innerHTML.includes('&lt;script&gt;'));
assert(!element('shared-main').innerHTML.includes('card-reference'));
assert(!element('shared-main').innerHTML.includes('表示枠'));
snapshot.map.shared.slots=[null,'a',null,null,null,null];renderShared(snapshot);
assert(!element('shared-main').innerHTML.includes('card-reference'));
assert(element('shared-main').innerHTML.includes('&lt;script&gt;'));
snapshot.map.shared.slots=['a',null,null,null,null,null];renderShared(snapshot);
assert(!element('.flow-band').hidden);
assert.equal((element('flow-list').innerHTML.match(/flow-item current/g)||[]).length,1);
assert(element('flow-list').innerHTML.startsWith('<span class="flow-item current">交通</span>'));
assert(element('flow-list').innerHTML.includes('←'));
assert(!element('flow-list').innerHTML.includes('→'));
// Non-palindromic history verifies reverse order, truncation, and no source mutation.
graph.nodes.push({id:'t3',type:'topic',label:'地域連携'});
snapshot.map.recent_flow=[{topic_id:'t2',label:'旧い参加'},{topic_id:'t1',label:'旧い交通'},{topic_id:'t3',label:'地域連携'},{topic_id:'t2',label:'住民参加'},{topic_id:'t1',label:'交通'}];
const originalFlow=JSON.stringify(snapshot.map.recent_flow);
renderShared(snapshot);
const flowHtml=element('flow-list').innerHTML;
assert.deepEqual([...flowHtml.matchAll(/class="flow-item(?: current)?">([^<]+)</g)].map(m=>m[1]),['交通','住民参加','地域連携','旧い交通']);
assert.equal(JSON.stringify(snapshot.map.recent_flow),originalFlow);
assert.equal((flowHtml.match(/flow-item current/g)||[]).length,1);
snapshot.map.recent_flow=[{topic_id:'t1',label:'交通'}]; renderShared(snapshot);
assert(element('.flow-band').hidden);
snapshot.live_state.runtime_state='ended';renderShared(snapshot);
assert(element('shared-status').textContent.includes('会議を終了しました'));
assert(element('shared-main').innerHTML.includes('意味'));
snapshot.live_state.runtime_state='idle';renderShared(snapshot);
assert(element('shared-main').innerHTML.includes('/session'));
snapshot.live_state.runtime_state='active';renderShared(snapshot);
assert(element('shared-main').innerHTML.includes('ほか3件'));
'''
        result=subprocess.run([shutil.which('node')],input=harness,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
