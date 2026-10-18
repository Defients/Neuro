import asyncio
import contextlib
from contextlib import asynccontextmanager
import os
from pathlib import Path
import tempfile
import time
from urllib.parse import urlsplit
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field
from .storage import Store, Recorder
from .sources import Acquisition
from .security import configuration, redact
from .errors import CortexError
from .processing import analyze

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ORIGINS = {'http://localhost:8080', 'http://127.0.0.1:8080', 'http://localhost:5173', 'http://127.0.0.1:5173'}
store = Store(os.getenv('NSS_DATA_DIR', str(ROOT / 'data')) + '/studio.sqlite3')
recorder = Recorder(store)
acquisition = Acquisition(recorder, store)


@asynccontextmanager
async def lifespan(app):
    acquisition.processing_task = asyncio.create_task(acquisition.process())
    discovery = []
    if os.getenv('NSS_AUTODISCOVER', '1') == '1':
        discovery = [asyncio.create_task(acquisition.cortex.diagnose(authenticate=False)), asyncio.create_task(acquisition.discover_lsl())]
    yield
    for task in discovery:
        if not task.done():
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    await acquisition.stop(reason="application shutdown")
    await acquisition.cortex.close()
    acquisition.processing_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await acquisition.processing_task


app = FastAPI(title='NeuralSignalStudio local API', version='0.1.0', lifespan=lifespan)


@app.middleware('http')
async def local_only(request: Request, call_next):
    origin = request.headers.get('origin')
    host = request.headers.get('host', '').split(':')[0]
    if host not in ('127.0.0.1', 'localhost', 'testserver') or origin and origin not in ALLOWED_ORIGINS:
        return JSONResponse({'detail': 'Only trusted loopback origins may access this API.'}, 403)
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin is None and request.headers.get('x-nss-local') != '1':
        return JSONResponse({'detail': 'Local API writes require Origin or X-NSS-Local: 1.'}, 403)
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        length = int(request.headers.get('content-length', '0'))
        if length > 65536:
            return JSONResponse({'detail': 'Request too large.'}, 413)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' ws://localhost:8080 ws://127.0.0.1:8080 ws://localhost:5173 ws://127.0.0.1:5173; img-src 'self' data:; frame-ancestors 'none'"
    return response


@app.exception_handler(ValueError)
async def value_error(request, exc):
    return JSONResponse({'detail': redact(str(exc))}, 400)


@app.exception_handler(CortexError)
async def cortex_error(request, exc):
    return JSONResponse({'detail': exc.report()}, 409)


class SourceRequest(BaseModel):
    kind: str
    uid: str = ''
    headset: str = ''
    activate: bool = False
    debit_one: bool = False
    authorized: bool = False
    speed: float = Field(1, ge=.25, le=4)


class RecordRequest(BaseModel):
    title: str = Field('Untitled session', min_length=1, max_length=150)
    participant: str = Field('participant-01', max_length=80)
    consent: bool = False


class MarkerRequest(BaseModel):
    label: str = Field(min_length=1, max_length=500)
    kind: str = 'marker'
    ratings: dict[str, float] | None = None
    task: str | None = Field(None, max_length=100)


class DiagnosticRequest(BaseModel):
    use_license: bool = False


@app.get('/api/health')
def health():
    return {'ok': True, 'version': '0.1.1-lifecycle', 'local_only': True, 'storage': 'SQLite WAL', 'cloud_upload': False}


@app.get('/api/state')
def state():
    return acquisition.state()


@app.get('/api/config')
def config():
    return configuration()


@app.get('/api/diagnostics')
def diagnostics():
    return acquisition.cortex.report()


@app.post('/api/diagnostics')
async def run_diagnostics(body: DiagnosticRequest):
    async with acquisition.transition:
        if acquisition.source and acquisition.source.kind == 'cortex':
            await acquisition.cortex.reconcile(recover=True)
            return acquisition.cortex.report()
        return await acquisition.cortex.diagnose(body.use_license)


@app.get('/api/diagnostics/export')
def diagnostic_export():
    return JSONResponse(acquisition.cortex.report(), headers={'Content-Disposition': 'attachment; filename="cortex-diagnostics.json"'})


@app.get('/api/lsl')
def lsl_status():
    return acquisition.lsl_report


@app.post('/api/lsl/discover')
async def lsl_discover():
    return await acquisition.discover_lsl()


@app.post('/api/source')
async def select_source(body: SourceRequest):
    async with acquisition.transition:
        if body.kind == 'synthetic':
            await acquisition.demo()
        elif body.kind == 'none':
            await acquisition.stop()
        elif body.kind in ('cortex', 'lsl'):
            if not body.authorized:
                raise ValueError('Participant authorization to acquire this source must be explicit.')
            if body.kind == 'lsl':
                await acquisition.lsl(body.uid)
            else:
                await acquisition.connect_cortex(body.headset, body.activate, body.debit_one)
        elif body.kind == 'replay':
            await acquisition.replay(body.uid, body.speed)
        else:
            raise ValueError('Unknown source.')
    return acquisition.state()


@app.post('/api/replay/speed')
async def replay_speed(body: SourceRequest):
    if not acquisition.source or acquisition.source.kind != 'replay':
        raise ValueError('No replay is running.')
    acquisition.replay_speed = body.speed
    return {'speed': body.speed}


@app.post('/api/record/start')
async def record_start(body: RecordRequest):
    async with acquisition.transition:
        if not body.consent:
            raise ValueError('Explicit participant recording consent is required.')
        if not acquisition.source or not acquisition.state()['arriving'] or not acquisition.source.channels:
            raise ValueError('No verified arriving EEG samples to record.')
        if acquisition.source.kind == 'replay':
            raise ValueError('Replay is read-only. Export a selected region instead.')
        recorder.start(body.title, body.participant, acquisition.source)
    return recorder.status()


@app.post('/api/record/stop')
async def record_stop():
    return await asyncio.to_thread(recorder.stop)


@app.post('/api/markers')
async def marker(body: MarkerRequest):
    if not acquisition.source or not acquisition.state()['arriving']:
        raise ValueError('Start a data source before annotating.')
    if body.kind not in ('marker', 'self_report', 'task'):
        raise ValueError('Unknown annotation kind.')
    if body.ratings:
        allowed = {'valence', 'arousal', 'stress', 'focus', 'confidence'}
        if any(k not in allowed or not 0 <= v <= 10 for k, v in body.ratings.items()):
            raise ValueError('Self-report ratings must be 0–10 and use supported fields.')
    stamp = acquisition.last
    event = {'timestamp': stamp, 'kind': body.kind, 'label': body.label, 'ratings': body.ratings, 'task': body.task, 'origin': 'participant self-report' if body.kind == 'self_report' else 'manual annotation', 'persisted': bool(recorder.sid and not recorder.error)}
    acquisition.annotations.appendleft(event)
    recorder.event(body.kind, event, stamp)
    return event


@app.get('/api/sessions')
async def sessions(q: str = ''):
    return await asyncio.to_thread(store.sessions, q[:150])


@app.get('/api/sessions/{sid}')
async def session(sid: str):
    return {'session': await asyncio.to_thread(store.get, sid), 'events': await asyncio.to_thread(store.events, sid)}


@app.get('/api/sessions/{sid}/analysis')
async def offline_analysis(sid: str, start: float = 0, end: float = 30):
    info = store.get(sid)
    if start < 0 or end <= start or end - start > 120:
        raise ValueError('Choose a region up to 120 seconds, with end greater than start.')
    data = await asyncio.to_thread(store.region, sid, start, end, 32768)
    result = await asyncio.to_thread(analyze, data, info['source']['nominal_rate'])
    return {'session': info, 'analysis': result, 'region': [start, end], 'samples': len(data), 'limit': 32768}


@app.get('/api/sessions/{sid}/export')
async def export(sid: str, start: float = 0, end: float | None = None):
    if start < 0 or end is not None and end <= start:
        raise ValueError('Invalid export time range.')
    store.get(sid)
    fd, path = tempfile.mkstemp(suffix='.zip', prefix='nss-export-')
    os.close(fd)
    try:
        await asyncio.to_thread(store.export, sid, path, start, end)
    except Exception:
        Path(path).unlink(missing_ok=True)
        raise
    return FileResponse(path, filename=f'neuralsignal-{sid[:8]}.zip', background=BackgroundTask(lambda: Path(path).unlink(missing_ok=True)))


@app.websocket('/ws/monitor')
async def monitor(ws: WebSocket):
    if ws.headers.get('origin') not in ALLOWED_ORIGINS or ws.headers.get('host', '').split(':')[0] not in ('localhost', '127.0.0.1', 'testserver'):
        await ws.close(code=1008)
        return
    await ws.accept()
    try:
        seconds = min(30, max(2, int(ws.query_params.get('seconds', '10'))))
        filtered = ws.query_params.get('filtered') == '1'
        notch = int(ws.query_params.get('notch', '0'))
        while True:
            await asyncio.wait_for(ws.send_json(await acquisition.frame(seconds, filtered, notch)), 2)
            await asyncio.sleep(.1)
    except (WebSocketDisconnect, TimeoutError, RuntimeError):
        pass


if (ROOT / 'dist').exists():
    app.mount('/assets', StaticFiles(directory=ROOT / 'dist/assets'), name='assets')


@app.get('/{path:path}')
async def dashboard(path: str):
    if path.startswith(('api/', 'ws/')):
        raise HTTPException(404)
    if not (ROOT / 'dist/index.html').exists():
        return JSONResponse({'message': 'Build the frontend with npm run build, then restart the backend.'}, 503)
    return FileResponse(ROOT / 'dist/index.html')
