"""Append-only raw samples, bounded writer queue and SQLite WAL recovery."""
import csv
from dataclasses import asdict
import io
import json
from pathlib import Path
import queue
import sqlite3
import threading
import time
import uuid
import zipfile
from contextlib import contextmanager
from .models import Sample
from .processing import SETTINGS


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, title TEXT, participant TEXT, started REAL, stopped REAL, status TEXT, source TEXT, processing TEXT);
                CREATE TABLE IF NOT EXISTS samples(session TEXT, seq INTEGER, timestamp REAL, payload TEXT, PRIMARY KEY(session,seq));
                CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, session TEXT, timestamp REAL, kind TEXT, payload TEXT);
                CREATE INDEX IF NOT EXISTS samples_time ON samples(session,timestamp);
                UPDATE sessions SET status='recovered', stopped=(SELECT MAX(timestamp) FROM samples WHERE session=sessions.id) WHERE status='recording';
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute('PRAGMA synchronous=FULL')
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, title, participant, source):
        sid = str(uuid.uuid4())
        with self.db() as db:
            db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?)', (sid, title, participant, time.time(), None, 'recording', json.dumps(source.to_dict()), json.dumps(SETTINGS)))
        return sid

    def sessions(self, query=''):
        with self.db() as db:
            rows = db.execute('SELECT *, (SELECT COUNT(*) FROM samples WHERE session=sessions.id) AS sample_count FROM sessions WHERE title LIKE ? OR participant LIKE ? ORDER BY started DESC LIMIT 200', ('%' + query + '%', '%' + query + '%')).fetchall()
        return [self._decode(r) for r in rows]

    @staticmethod
    def _decode(row):
        d = dict(row)
        for k in ('source', 'processing', 'payload'):
            if k in d:
                d[k] = json.loads(d[k])
        return d

    def get(self, sid):
        with self.db() as db:
            row = db.execute('SELECT *, (SELECT COUNT(*) FROM samples WHERE session=sessions.id) AS sample_count FROM sessions WHERE id=?', (sid,)).fetchone()
        if row is None:
            raise ValueError('Recording not found.')
        return self._decode(row)

    def read(self, sid, offset=0, limit=2048):
        with self.db() as db:
            rows = db.execute('SELECT payload FROM samples WHERE session=? AND seq>=? ORDER BY seq LIMIT ?', (sid, offset, limit)).fetchall()
        return [Sample(**json.loads(r[0])) for r in rows]

    def region(self, sid, start=0, end=None, limit=20000):
        with self.db() as db:
            first = db.execute('SELECT timestamp FROM samples WHERE session=? ORDER BY seq LIMIT 1', (sid,)).fetchone()
            if not first:
                return []
            rows = db.execute('SELECT payload FROM samples WHERE session=? AND timestamp>=? AND timestamp<=? ORDER BY seq LIMIT ?', (sid, first[0] + start, first[0] + end if end is not None else float('inf'), limit)).fetchall()
        return [Sample(**json.loads(r[0])) for r in rows]

    def event(self, sid, kind, payload, stamp=None):
        with self.db() as db:
            db.execute('INSERT INTO events(session,timestamp,kind,payload) VALUES(?,?,?,?)', (sid, time.time() if stamp is None else stamp, kind, json.dumps(payload)))

    def events(self, sid, offset=0, limit=2000):
        with self.db() as db:
            rows = db.execute('SELECT * FROM events WHERE session=? ORDER BY timestamp,id LIMIT ? OFFSET ?', (sid, limit, offset)).fetchall()
        return [self._decode(r) for r in rows]

    def export(self, sid, target, start=0, end=None):
        """Stream a region into a temporary ZIP on disk; memory does not grow with session size."""
        info = self.get(sid)
        with self.db() as db, zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
            first = db.execute('SELECT timestamp FROM samples WHERE session=? ORDER BY seq LIMIT 1', (sid,)).fetchone()
            with z.open('raw.csv', 'w') as raw:
                with io.TextIOWrapper(raw, encoding='utf-8', newline='') as txt:
                    writer = csv.writer(txt)
                    writer.writerow(['timestamp', 'received_at', *info['source']['channels'], 'counter', 'interpolated', 'discontinuity', 'metadata_json'])
                    if first:
                        for row in db.execute('SELECT payload FROM samples WHERE session=? AND timestamp>=? AND timestamp<=? ORDER BY seq', (sid, first[0] + start, first[0] + end if end is not None else float('inf'))):
                            s = Sample(**json.loads(row[0]))
                            writer.writerow([s.timestamp, s.received_at, *s.values, s.counter, s.interpolated, s.discontinuity, json.dumps(s.metadata)])
            info['export_region_seconds'] = [start, end]
            info['format_notes'] = 'Original values; no gap filling. CSV + metadata + events. XDF and EDF+ not implemented. Quality/markers are in sample metadata or events. Source timestamps retain original clock domain.'
            z.writestr('metadata.json', json.dumps(info, indent=2))
            with z.open('events.json', 'w') as raw_events:
                raw_events.write(b'[')
                for i, row in enumerate(db.execute('SELECT * FROM events WHERE session=? ORDER BY id', (sid,))):
                    if i:
                        raw_events.write(b',')
                    raw_events.write(json.dumps(self._decode(row)).encode('utf-8'))
                raw_events.write(b']')


class Recorder:
    def __init__(self, store):
        self.store = store
        self.sid = None
        self.last_sid = None
        self.queue = queue.Queue(maxsize=128)
        self.thread = None
        self.error = None
        self.count = 0
        self.started = None

    def start(self, title, participant, source):
        if self.sid or self.thread and self.thread.is_alive():
            raise ValueError('A recording is already running or finalizing.')
        self.queue = queue.Queue(maxsize=128)
        self.error = None
        self.count = 0
        self.started = time.time()
        self.sid = self.store.create(title, participant, source)
        self.last_sid = self.sid
        self.thread = threading.Thread(target=self._write, args=(self.sid,), daemon=True)
        self.thread.start()
        return self.sid

    def append(self, samples):
        if self.sid and not self.error:
            try:
                self.queue.put_nowait(('samples', [s.to_dict() for s in samples]))
            except queue.Full:
                self.error = 'Recording stopped: disk writer queue overflow. Some samples were not recorded; inspect the recovered session.'

    def event(self, kind, payload, stamp):
        if self.sid and not self.error:
            try:
                self.queue.put_nowait(('event', (kind, payload, stamp)))
            except queue.Full:
                self.error = 'Recording stopped: event writer queue overflow.'

    def _write(self, sid):
        try:
            with self.store.db() as db:
                stopped = False
                while True:
                    item = self.queue.get()
                    if item is None:
                        break
                    items = [item]
                    deadline = time.monotonic() + .1
                    while len(items) < 64 and time.monotonic() < deadline:
                        try:
                            item = self.queue.get(timeout=max(.001, deadline - time.monotonic()))
                            if item is None:
                                stopped = True
                                break
                            items.append(item)
                        except queue.Empty:
                            break
                    count = 0
                    for kind, payload in items:
                        if kind == 'samples':
                            db.executemany('INSERT INTO samples VALUES(?,?,?,?)', [(sid, self.count + count + i, s['timestamp'], json.dumps(s, allow_nan=False)) for i, s in enumerate(payload)])
                            count += len(payload)
                        else:
                            k, data, stamp = payload
                            db.execute('INSERT INTO events(session,timestamp,kind,payload) VALUES(?,?,?,?)', (sid, stamp, k, json.dumps(data)))
                    db.commit()
                    self.count += count
                    if stopped:
                        break
                db.execute('UPDATE sessions SET status=?,stopped=? WHERE id=?', ('interrupted' if self.error else 'complete', time.time(), sid))
                db.commit()
        except Exception as e:
            self.error = 'Recording persistence failed: ' + type(e).__name__
        finally:
            self.sid = None

    def stop(self):
        if self.thread and self.thread.is_alive():
            self.queue.put(None, timeout=10)
            self.thread.join(timeout=15)
            if self.thread.is_alive():
                self.error = 'Recording is still finalizing; do not close the application.'
        return self.status()

    def status(self):
        return {'active': bool(self.sid) and not self.error, 'id': self.sid, 'last_id': self.last_sid, 'error': self.error, 'persisted_samples': self.count, 'started': self.started}
