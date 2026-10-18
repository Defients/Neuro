import pytest
from backend.cortex import Cortex
from tests.test_stream_delivery import prepared


async def test_verified_cancellation_recovers_once_on_same_session(store):
    a,c=prepared(store)
    c.desired_streams=['dev','eq','met','mot','pow']
    calls=[]
    async def call(method,params):
        calls.append((method,params))
        if method=='querySessions':
            return [{'id':'current','status':'opened','streams':[]}]
        if method=='subscribe':
            return {'success':[{'streamName':n,'cols':c.cols[n]} for n in c.desired_streams],'failure':[]}
        raise AssertionError(method)
    c.call=call
    c.warning({'code':0,'message':{'sessionId':'current'}})
    await c.reconcile(recover=True)
    await c.reconcile(recover=True)
    assert sum(m=='subscribe' for m,p in calls)==1
    assert c.session=='current'
    assert not any(m in ('createSession','updateSession','authorize') for m,p in calls)


async def test_missing_session_does_not_create_or_activate(store):
    a,c=prepared(store)
    async def call(method,params):
        assert method=='querySessions'
        return []
    c.call=call
    assert (await c.reconcile(True))['status']=='missing_or_closed'
    assert not c.notifications_enabled


async def test_navigation_and_duplicate_display_sockets_never_close_source(tmp_path,monkeypatch):
    from tests.test_api import client
    c,module=client(tmp_path,monkeypatch)
    from backend.models import Source
    with c:
        module.acquisition.reset(Source('cortex:test','cortex','test',[],[],128,'Unix'))
        module.acquisition.cortex.session='session'
        module.acquisition.cortex.notifications_enabled=True
        with c.websocket_connect('/ws/monitor',headers={'Origin':'http://localhost:8080'}) as first:
            first.receive_json()
            with c.websocket_connect('/ws/monitor?seconds=20',headers={'Origin':'http://localhost:8080'}) as second:
                second.receive_json()
                c.get('/api/state')
                c.get('/api/diagnostics')
        assert module.acquisition.cortex.session=='session'
        assert not any(e['operation']=='session_teardown' for e in module.acquisition.cortex.events)
        # Avoid a real cleanup RPC in the fake-session test.
        module.acquisition.cortex.session=None


async def test_concurrent_open_creates_only_one_transport(monkeypatch):
    import asyncio
    c=Cortex()
    calls=[]
    async def open_once():
        if c.socket is None:
            await asyncio.sleep(.01)
            calls.append(1)
            c.socket=object()
    c._open=open_once
    await asyncio.gather(c.open(),c.open())
    assert len(calls)==1
