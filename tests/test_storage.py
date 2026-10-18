import csv
import io
import json
import zipfile
import time
from backend.storage import Recorder, Store
from backend.models import Source
from backend.sources import synthetic


def source():
    return Source('synthetic-v1','synthetic','fixture',['SIM-L','SIM-R'],['µV','µV'],128,'test',True)


def test_record_roundtrip_reopen_and_selected_export(store, tmp_path):
    rec = Recorder(store)
    sid = rec.start('Roundtrip', 'p01', source())
    samples = [synthetic(i, epoch=12345) for i in range(512)]
    samples[257].interpolated = True
    samples[258].metadata['marker'] = {'label':'blink'}
    rec.append(samples)
    rec.event('self_report', {'focus': 7, 'origin':'participant'}, 12346)
    rec.stop()
    assert rec.error is None
    assert store.get(sid)['sample_count'] == 512
    restored = store.read(sid)
    assert [s.to_dict() for s in restored] == [s.to_dict() for s in samples]
    assert store.get(sid)['source']['channels'] == ['SIM-L', 'SIM-R']
    assert store.get(sid)['status'] == 'complete'
    assert store.events(sid)[0]['kind'] == 'self_report'
    output = tmp_path / 'region.zip'
    store.export(sid, output, 1, 2)
    with zipfile.ZipFile(output) as z:
        rows = list(csv.DictReader(io.StringIO(z.read('raw.csv').decode())))
        meta = json.loads(z.read('metadata.json'))
        assert len(rows) == 129
        assert float(rows[0]['timestamp']) == samples[128].timestamp
        assert float(rows[0]['SIM-L']) == samples[128].values[0]
        assert meta['source']['simulated'] is True
        assert json.loads(z.read('events.json'))[0]['kind'] == 'self_report'


def test_interrupted_session_recovery_marks_last_committed_samples(store):
    sid = store.create('Interrupted', 'p01', source())
    s = synthetic(0, epoch=100)
    with store.db() as db:
        db.execute('INSERT INTO samples VALUES(?,?,?,?)', (sid, 0, s.timestamp, json.dumps(s.to_dict())))
    reopened = Store(store.path)
    info = reopened.get(sid)
    assert info['status'] == 'recovered'
    assert info['sample_count'] == 1
    assert reopened.read(sid)[0].values == s.values


def test_queue_overflow_is_visible_and_fail_closed(store):
    rec = Recorder(store)
    rec.sid = 'test'
    for i in range(129):
        rec.append([synthetic(i)])
    assert 'overflow' in rec.error
    assert not rec.status()['active']
    assert rec.queue.qsize() == 128
