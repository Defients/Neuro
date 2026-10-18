import asyncio
import time
import pytest
from backend.models import Source, Sample
from backend.storage import Recorder
from backend.sources import Acquisition, synthetic
from backend.cortex import Cortex
from backend.errors import CortexError
from backend.processing import active_metrics


def fixture():
    return Source('synthetic','synthetic','fixture',['SIM-L','SIM-R'],['µV','µV'],128,'Unix',True)


async def test_source_stop_clears_arriving_state(store):
    a=Acquisition(Recorder(store),store)
    await a.demo()
    await asyncio.sleep(.08)
    assert a.state()['arriving']
    await a.stop()
    state=a.state()
    assert state['source'] is None
    assert not state['arriving']
    assert state['total_samples']==0
    assert not state['features']['available']


async def test_replay_preserves_annotations_and_source_provenance(store):
    r=Recorder(store)
    sid=r.start('Replay','fixture',fixture())
    r.append([synthetic(i,epoch=100) for i in range(64)])
    r.event('self_report',{'timestamp':100.1,'label':'Participant rating','kind':'self_report','ratings':{'focus':6}},100.1)
    r.stop()
    a=Acquisition(r,store)
    await a.replay(sid,4)
    await asyncio.sleep(.1)
    assert a.source.kind=='replay'
    assert a.source.metadata['original_source_kind']=='synthetic'
    assert a.source.simulated
    assert a.annotations[0]['kind']=='self_report'
    assert a.annotations[0]['replayed']
    assert a.buffer[0].timestamp==100
    assert a.buffer[0].values==synthetic(0,epoch=100).values
    await a.stop()


async def test_disconnect_stops_recording_and_suppresses_proprietary_metrics(store):
    r=Recorder(store)
    a=Acquisition(r,store)
    a.reset(Source('cortex:fixture','cortex','fixture',['T7'],['µV'],128,'Unix'))
    r.start('Disconnected','fixture',a.source)
    a.ingest([Sample(time.time(),[1])])
    a.metrics={'timestamp':time.time(),'attention':.8,'cognitiveStress':.4,'stale':False}
    a._warning({'code':103})
    await asyncio.sleep(.2)
    assert not a.state()['arriving']
    assert a.state()['metrics'] is None
    assert not r.status()['active']
    assert store.get(r.last_sid)['status']=='interrupted'


async def test_startup_readonly_diagnostic_never_requests_credentials_or_activation(monkeypatch):
    class Stub(Cortex):
        def __init__(self):
            super().__init__();self.calls=[]
        async def call(self,method,params=None):
            self.calls.append(method)
            return {'version':'test'} if method=='getCortexInfo' else [{'currentOSUId':'1','loggedInOSUId':'1'}] if method=='getUserLogin' else []
    def forbidden():
        raise AssertionError('Startup must not read secrets')
    monkeypatch.setattr('backend.cortex.credentials',forbidden)
    c=Stub()
    await c.diagnose(authenticate=False)
    assert c.calls==['getCortexInfo','getUserLogin','queryHeadsets']
    assert not c.state['authorized']


async def test_diagnostic_flow_auto_license_first_and_no_debit(monkeypatch):
    class Stub(Cortex):
        def __init__(self):
            super().__init__();self.calls=[]
        async def call(self,method,params=None):
            self.calls.append((method,params))
            results={'getCortexInfo':{'version':'test'},'getUserLogin':[{'currentOSUId':'1','loggedInOSUId':'1'}],'requestAccess':{'accessGranted':True},'authorize':{'cortexToken':'fixture-secret-token'},'getLicenseInfo':{'license':{'scopes':['eeg'],'localQuota':0,'totalRegisteredDevices':1,'deviceInfo':{'deviceLimit':1}}},'controlDevice':{},'queryHeadsets':[]}
            return results[method]
    monkeypatch.setattr('backend.cortex.credentials',lambda:{'clientId':'fixture-id','clientSecret':'fixture-secret','license':'fixture-license'})
    async def no_delay(_):
        pass
    monkeypatch.setattr('backend.cortex.asyncio.sleep',no_delay)
    c=Stub()
    result=await c.diagnose()
    params=next(p for m,p in c.calls if m=='authorize')
    assert 'license' not in params and 'debit' not in params
    assert [m for m,p in c.calls]==['getCortexInfo','getUserLogin','requestAccess','authorize','getLicenseInfo','controlDevice','queryHeadsets']
    assert result['license']['totalRegisteredDevices']==1
    assert 'fixture-secret-token' not in str(result)


async def test_failed_approval_never_authorizes(monkeypatch):
    class Stub(Cortex):
        async def call(self,method,params=None):
            if method=='getCortexInfo': return {'version':'test'}
            if method=='getUserLogin': return [{'currentOSUId':'1','loggedInOSUId':'1'}]
            if method=='requestAccess': return {'accessGranted':False}
            raise AssertionError('Unauthorized follow-up: '+method)
    monkeypatch.setattr('backend.cortex.credentials',lambda:{'clientId':'fixture-id','clientSecret':'fixture-secret'})
    c=Stub()
    await c.diagnose()
    assert c.state['approval']=='awaiting_launcher_approval'
    assert c.token is None


def test_metrics_reject_future_clock_values():
    result=active_metrics(['attention','attention.isActive'],[.9,True],200,100)
    assert result['attention'] is None
    assert result['stale']


async def test_device_limit_preserves_exact_blocker_and_independent_discovery(monkeypatch):
    class Stub(Cortex):
        def __init__(self):
            super().__init__();self.calls=[]
        async def call(self,method,params=None):
            self.calls.append(method)
            if method=='getCortexInfo': return {'version':'test'}
            if method=='getUserLogin': return [{'currentOSUId':'1','loggedInOSUId':'1'}]
            if method=='requestAccess': return {'accessGranted':True}
            if method=='authorize': raise CortexError(-32022,'Device limit has been reached',method)
            if method=='queryHeadsets': return [{'id':'MN8-fixture','status':'discovered'}]
            raise AssertionError('Unexpected retry or activation: '+method)
    monkeypatch.setattr('backend.cortex.credentials',lambda:{'clientId':'fixture-id','clientSecret':'fixture-secret'})
    c=Stub()
    report=await c.diagnose()
    assert report['blocker']['code']==-32022
    assert 'transfer' in report['next_action']
    assert report['headsets'][0]['status']=='discovered'
    assert c.calls.count('authorize')==1
    assert not report['authorized']


async def test_dead_cortex_does_not_block_demo_switch(store):
    a=Acquisition(Recorder(store),store)
    a.reset(Source('cortex:fixture','cortex','fixture',['T7'],['µV'],128,'Unix'))
    async def fail_close():
        raise ConnectionError('Transport unavailable')
    a.cortex.close_session=fail_close
    await a.demo()
    await asyncio.sleep(.08)
    assert a.source.simulated and a.source.kind=='synthetic'
    assert a.state()['arriving']
    assert a.cortex.events[-1]['outcome']=='transport_error'
    await a.stop()
