import importlib
import time
import pytest
from starlette.websockets import WebSocketDisconnect
from fastapi.testclient import TestClient


def client(tmp_path, monkeypatch):
    monkeypatch.setenv('NSS_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('NSS_AUTODISCOVER', '0')
    import backend.app as module
    module=importlib.reload(module)
    return TestClient(module.app), module


def test_loopback_origin_security_and_consent(tmp_path, monkeypatch):
    c, module = client(tmp_path, monkeypatch)
    with c:
        assert c.get('/api/health').json()['ok']
        assert c.post('/api/source',json={'kind':'synthetic'}).status_code==403
        assert c.post('/api/source',json={'kind':'synthetic'},headers={'Origin':'https://evil.example'}).status_code==403
        assert c.get('/api/health',headers={'Host':'evil.example'}).status_code==403
        assert c.post('/api/source',json={'kind':'cortex'},headers={'X-NSS-Local':'1'}).status_code==400
        assert c.post('/api/record/start',json={'consent':False},headers={'X-NSS-Local':'1'}).status_code==400
        config=c.get('/api/config').json()
        assert 'clientSecret' not in config and 'clientId' not in config


def test_end_to_end_demo_record_stop_reopen_export_and_replay(tmp_path, monkeypatch):
    c, module = client(tmp_path, monkeypatch)
    headers={'X-NSS-Local':'1'}
    with c:
        assert c.post('/api/source',json={'kind':'synthetic'},headers=headers).status_code==200
        time.sleep(.25)
        state=c.get('/api/state').json()
        assert state['source']['simulated'] and state['arriving']
        assert state['metrics'] is None
        r=c.post('/api/record/start',json={'title':'Integration fixture','consent':True},headers=headers)
        assert r.status_code==200
        sid=r.json()['id']
        assert c.post('/api/markers',json={'kind':'self_report','label':'Focused','ratings':{'focus':7}},headers=headers).status_code==200
        time.sleep(.4)
        assert c.post('/api/record/stop',json={},headers=headers).status_code==200
        info=c.get('/api/sessions/'+sid).json()
        assert info['session']['sample_count']>30
        assert info['events'][0]['kind']=='self_report'
        exported=c.get('/api/sessions/'+sid+'/export')
        assert exported.status_code==200 and exported.content[:2]==b'PK'
        assert c.post('/api/source',json={'kind':'replay','uid':sid,'speed':2},headers=headers).status_code==200
        time.sleep(.1)
        assert c.get('/api/state').json()['source']['kind']=='replay'
        assert c.post('/api/record/start',json={'consent':True},headers=headers).status_code==400


def test_websocket_origin_and_real_synthetic_payload(tmp_path, monkeypatch):
    c, module = client(tmp_path, monkeypatch)
    with c:
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect('/ws/monitor', headers={'Origin':'https://evil.example'}):
                pass
        c.post('/api/source', json={'kind':'synthetic'}, headers={'X-NSS-Local':'1'})
        time.sleep(.2)
        with c.websocket_connect('/ws/monitor?seconds=5&filtered=1', headers={'Origin':'http://localhost:8080'}) as ws:
            message=ws.receive_json()
            assert message['source']['simulated']
            assert len(message['waveform']['timestamps'])>0
            assert len(message['waveform']['values'][0])==2
            assert message['waveform']['filtered']
