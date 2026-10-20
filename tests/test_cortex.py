import asyncio
import json
import pytest
from backend.cortex import Cortex
from backend.errors import CortexError, ERRORS
from backend.security import redact, remember


def test_error_codes_and_secret_redaction():
    remember('secret-fixture-value', 'token-fixture-value')
    for code in [-32021,-32022,-32027,-32019,-32016,-32102,-32232]:
        result = CortexError(code, 'original secret-fixture-value', 'authorize').report()
        assert 'secret-fixture-value' not in json.dumps(result)
        assert result['code'] == code
        assert result['action'] and result['alternative']
    assert not CortexError(-32022, 'limit', 'authorize').report()['retry']
    assert 'transfer' in ERRORS[-32022][1]
    r = redact({'nested':{'cortexToken':'token-fixture-value'},'clientSecret':'secret-fixture-value','message':'Bearer abc.def secret-fixture-value'})
    assert 'token-fixture-value' not in json.dumps(r)
    assert 'abc.def' not in json.dumps(r)


class FakeCortex(Cortex):
    def __init__(self, connected):
        super().__init__()
        self.token = 'fixture'
        self.connected = connected
        self.calls = []
        self.fail_active = False
        self.state['license'] = {'scopes':['eeg']}

    async def call(self, method, params=None):
        self.calls.append((method, params))
        if method == 'controlDevice':
            return {'message':'accepted but not proof of connection'}
        if method == 'queryHeadsets':
            if not self.connected:
                raise CortexError(-32022,'Device limit has been reached','queryHeadsets')
            return [{'id':'MN8-test','status':'connected','samplingRate':128}]
        if method == 'createSession':
            if self.fail_active and (params or {}).get('status') == 'active':
                raise CortexError(-32230, 'Headset is not supported by this license', 'createSession')
            return {'id':'session'}
        if method == 'subscribe':
            streams = (params or {}).get('streams', [])
            cols = {'eeg': ['COUNTER','INTERPOLATED','T7','T8','MARKERS']}
            return {'success':[{'streamName':s,'cols':cols.get(s,[s+'_col'])} for s in streams if s != 'met'], 'failure':[{'streamName':'met','code':-32016,'message':'Unavailable'}] if 'met' in streams else []}


async def test_connection_acceptance_never_creates_session_without_confirmation():
    c = FakeCortex(False)
    with pytest.raises(CortexError):
        await c.connect_headset('MN8-test', True)
    assert 'createSession' not in [m for m,p in c.calls]
    assert 'authorize' not in [m for m,p in c.calls]


async def test_connected_session_subscription_cols_and_partial_failure():
    c = FakeCortex(True)
    source = await c.connect_headset('MN8-test', True)
    assert source.channels == ['T7','T8']
    assert source.metadata['session'] == 'session'
    assert c.calls[2][0] == 'createSession'
    assert c.calls[2][1]['status'] == 'active'
    assert c.events[-1]['operation'] == 'subscribe:met'
    assert 'eeg' in [s['streamName'] for s in c.state['subscribe_response']['success']]
    assert c.state['subscribe_response']['failure'][0]['code']==-32016


async def test_scopeless_activation_still_attempted_and_rejection_falls_back():
    c = FakeCortex(True)
    c.state['license'] = {'scopes':[]}
    c.fail_active = True
    source = await c.connect_headset('MN8-test', True)
    creates = [p['status'] for m,p in c.calls if m == 'createSession']
    assert creates == ['active','open']
    assert any(e['operation']=='eeg_activation' and e['outcome']=='rejected' for e in c.events)
    assert c.state['eeg_activation'] == {'requested': True, 'accepted': False, 'error': c.state['eeg_activation']['error']}
    assert not source.channels


async def test_scopeless_activation_accepted_streams_eeg():
    c = FakeCortex(True)
    c.state['license'] = {'scopes':[]}
    source = await c.connect_headset('MN8-test', True)
    assert c.state['eeg_activation'] == {'requested': True, 'accepted': True}
    assert source.channels == ['T7','T8']


async def test_rpc_correlates_out_of_order_replies_and_does_not_log_params():
    class Socket:
        def __init__(self):
            self.sent=[]
        async def send(self, message):
            self.sent.append(json.loads(message))
    c=Cortex();c.socket=Socket()
    tasks=[asyncio.create_task(c.call('getCortexInfo')),asyncio.create_task(c.call('getUserLogin'))]
    await asyncio.sleep(0)
    for req in reversed(c.socket.sent):
        c.pending[req['id']].set_result({'id':req['id'],'result':req['method']})
    assert await asyncio.gather(*tasks)==['getCortexInfo','getUserLogin']
    assert not c.pending
