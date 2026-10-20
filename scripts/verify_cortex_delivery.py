"""Verify the authoritative running backend. Never create a second Cortex client."""
import asyncio
import json
import time
from pathlib import Path
import httpx
from websockets.asyncio.client import connect

async def main():
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8080',headers={'X-NSS-Local':'1'},timeout=45) as api:
        health=(await api.get('/api/health')).json()
        assert health['version']=='0.1.1-lifecycle', 'Restart the stale backend first'
        r=await api.post('/api/diagnostics',json={});r.raise_for_status()
        d=(await api.get('/api/diagnostics')).json()
        headset=next((h['id'] for h in d['headsets'] if h.get('status')=='connected'),None)
        assert headset,'No connected headset found in diagnostics'
        r=await api.post('/api/source',json={'kind':'cortex','headset':headset,'authorized':True,'activate':False,'debit_one':False});r.raise_for_status()
        names=['dev','eq','met','mot','pow']
        for _ in range(30):
            d=(await api.get('/api/diagnostics')).json()
            if all(d['stream_delivery'].get(n,{}).get('sample_count',0)>0 for n in names): break
            await asyncio.sleep(.5)
        assert all(d['stream_delivery'].get(n,{}).get('sample_count',0)>0 for n in names), 'Not all streams delivered'
        sid=d['session_id']; initial={n:d['stream_delivery'][n]['sample_count'] for n in names}
        began=time.monotonic();checks=0
        while time.monotonic()-began<30:
            # Exercise display reconnects/navigation independently of acquisition.
            if checks % 10 == 0:
                async with connect('ws://127.0.0.1:8080/ws/monitor',origin='http://localhost:8080',proxy=None) as ws:
                    frame=json.loads(await ws.recv())
                    assert frame['cortex_session_id']==sid
                r=await api.post('/api/diagnostics',json={});r.raise_for_status()
            d=(await api.get('/api/diagnostics')).json()
            assert d['session_id']==sid
            assert all(d['stream_delivery'][n]['receiving'] for n in names), 'Stream became stale'
            checks+=1
            await asyncio.sleep(.5)
        elapsed=time.monotonic()-began
        final=(await api.get('/api/diagnostics')).json()
        state=(await api.get('/api/state')).json()
        result={'duration_seconds':elapsed,'session_id':sid,'checks':checks,'count_deltas':{n:final['stream_delivery'][n]['sample_count']-initial[n] for n in names},'delivery':final['stream_delivery'],'sessions':final.get('sessions'),'raw_eeg_available':state['raw_eeg_available'],'recording':state['recording']['active'],'events':final['events']}
        assert all(v>0 for v in result['count_deltas'].values())
        assert not any(e['operation']=='session_teardown' or e['operation']=='warning' and e['outcome']=='0' for e in result['events'])
        Path('artifacts/lifecycle-30s.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k not in ('events','delivery')},indent=2))
        # Leave the authoritative session alive for Live Monitor. No cleanup RPC.

asyncio.run(main())
