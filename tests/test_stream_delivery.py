import time
import pytest
from backend.cortex import Cortex
from backend.sources import Acquisition
from backend.storage import Recorder
from backend.models import Source


def prepared(store):
    a=Acquisition(Recorder(store),store)
    a.reset(Source('cortex:MN8','cortex','MN8',[],[],128,'Unix'))
    c=a.cortex
    c.session='current'
    c.notifications_enabled=True
    c.token='test'
    c.cols={'eq':['overall','batteryPercent'],'met':['attention.isActive','attention','cognitiveStress.isActive','cognitiveStress'], 'pow':['T7/alpha'], 'mot':['Q0'], 'dev':['Battery']}
    return a,c


def test_five_streams_deliver_without_raw_eeg(store):
    a,c=prepared(store)
    for name,values in [('eq',[72,80]),('met',[True,.6,False,None]),('pow',[2.5]),('mot',[.5]),('dev',[4])]:
        c.notification({'sid':'current','time':time.time(),name:values})
    state=a.state()
    assert state['receiving_samples'] and not state['arriving']
    assert not state['raw_eeg_available'] and not state['features']['available']
    assert state['quality']==72 and state['metrics']['attention']==.6
    assert state['metrics']['cognitiveStress'] is None
    assert all(x['sample_count']==1 for x in c.report()['stream_delivery'].values())
    assert not a.buffer


def test_foreign_malformed_stale_and_invalid_quality(store):
    a,c=prepared(store)
    assert c.delivery()['eq']['sample_count']==0
    c.notification({'sid':'other','time':time.time(),'eq':[100,80]})
    c.notification({'sid':'current','time':time.time(),'eq':[100]})
    assert a.state()['quality'] is None and not c.telemetry
    c.notification({'sid':'current','time':time.time(),'eq':[True,80]})
    assert a.state()['quality'] is None
    c.telemetry['eq']['last_arrival']-=20
    assert not c.delivery()['eq']['receiving']


async def test_repeated_selection_reuses_session(store):
    a,c=prepared(store)
    async def forbidden(*args,**kwargs):
        raise AssertionError('Must not teardown or recreate')
    a.stop=forbidden
    c.connect_headset=forbidden
    await a.connect_cortex('MN8',False,False)
    assert c.session=='current'
    assert c.events[-1]['outcome']=='reused_session'


async def test_expected_close_and_late_warning_do_not_interrupt_new_session(store):
    a,c=prepared(store)
    async def call(method,params):
        c.warning({'code':0,'message':{'sessionId':'current'}})
        assert a.error is None
    c.call=call
    await c.close_session(reason='test user stop')
    c.session='new';c.notifications_enabled=True
    c.warning({'code':0,'message':{'sessionId':'current'}})
    assert c.notifications_enabled and a.error is None
    c.warning({'code':0,'message':{'sessionId':'new'}})
    assert not c.notifications_enabled and a.error


def test_unauthorized_notifications_cannot_claim_delivery(store):
    a,c=prepared(store)
    c.notifications_enabled=False
    c.notification({'sid':'current','time':time.time(),'eq':[100,90]})
    assert not a.state()['receiving_samples'] and a.state()['quality'] is None


def test_stale_source_timestamp_cannot_publish_quality(store):
    a,c=prepared(store)
    c.notification({'sid':'current','time':time.time()-100,'eq':[100,80]})
    assert a.state()['quality'] is None


async def test_notification_with_null_id_is_routed_before_rpc(store):
    a,c=prepared(store)
    import json
    class Socket:
        def __aiter__(self):
            return self.run()
        async def run(self):
            yield json.dumps({'id':None,'sid':'current','time':time.time(),'pow':[2.5]})
    c.socket=Socket()
    await c._receive()
    assert c.telemetry['pow']['sample_count']==1
