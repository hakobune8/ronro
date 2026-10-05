"""Loopback-only, read-only Product HTTP server with allowlisted saved states.

No audio manager, provider, arbitrary filesystem endpoint or mutation routes.
The actual Product Shared HTML is served by the existing Product HTTP handler.
"""
import argparse
import copy
import json
from pathlib import Path

from prototype.app import DeveloperPrototypeApp
from prototype.layout import StableLayout, map_projection
from prototype.server import create_server
from prototype.schema import SchemaValidator
from prototype.shared_projection import select_shared
from shared_projection_spike import replay
from final_shared_candidate import synthetic


def main(args):
    root=Path(__file__).resolve().parents[2]
    data=json.loads(args.live.read_text())
    history=replay(data,SchemaValidator(root/'schemas'))
    states={}
    for minute in (5,10,15):
        saved=json.loads((args.snapshots/f'{minute:02}min.json').read_text())
        row=next(r for r in reversed(history) if r['revision']==saved['graph']['revision'])
        state={**data['state'],'graph':saved['graph']}
        events=[e for e in data['events'] if e['sequence']<=row['sequence']]
        projection=map_projection(state,events,StableLayout())
        states[f't1-{minute}']={'state':{'graph':saved['graph']},'map':projection,'live_state':{'runtime_state':'active'}}
    for name,graph,events in synthetic(root):
        states[name]={'state':{'graph':graph},'map':{'shared':select_shared(graph,events),'recent_flow':[]},'live_state':{'runtime_state':'active'}}
    # Existing genuine Topic-return fixture plus the synthetic capacity state:
    # separate explicitly synthetic visual-density/flow case, not T1 evidence.
    app=DeveloperPrototypeApp(root/'evaluation/fixtures',root/'schemas')
    app.reset_session('002',mode='events')
    returned=app.session_snapshot('002')
    dense=copy.deepcopy(states['persistent-9'])
    dense['state']['graph']['nodes'] += [n for n in returned['state']['graph']['nodes'] if n['type']=='topic']
    dense['state']['graph']['current_topic']=copy.deepcopy(returned['state']['graph']['current_topic'])
    dense['map']['recent_flow']=copy.deepcopy(returned['map']['recent_flow'])
    states['persistent-flow']=dense

    class ReadOnlyApp:
        handler_sessions={}
        def reset_session(self,fixture_id,*args,**kwargs):
            if fixture_id not in states: raise ValueError('Unknown QA case')
        def session_snapshot(self,fixture_id):
            return copy.deepcopy(states[fixture_id])
        def list_fixtures(self):
            return list(states)
    server=create_server(ReadOnlyApp(),'127.0.0.1',args.port,live_manager=None)
    server.RequestHandlerClass.do_POST=lambda self:self._send(405,b'QA is read-only')
    print(f'QA Product HTTP ready on 127.0.0.1:{server.server_address[1]}; cases: '+', '.join(states),flush=True)
    server.serve_forever()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--live',type=Path,required=True);p.add_argument('--snapshots',type=Path,required=True);p.add_argument('--port',type=int,default=18884)
    main(p.parse_args())
