"""Single Cortex socket, correlated RPC futures, independent asynchronous stream dispatch."""
import asyncio
from collections import deque
import contextlib
import json
import os
from pathlib import Path
import ssl
import time
from websockets.asyncio.client import connect

from .errors import CortexError
from .security import credentials, remember, redact
from .models import Source, Sample

ROOT = Path(__file__).resolve().parents[1]
EEG_METADATA = {'COUNTER', 'INTERPOLATED', 'RAW_CQ', 'MARKER_HARDWARE', 'MARKERS'}


class Cortex:
    def __init__(self, on_data=None, on_warning=None):
        self.socket = None
        self.reader = None
        self.pending = {}
        self.seq = 0
        self.open_lock = asyncio.Lock()
        self.recovery_attempts = 0
        self.desired_streams = []
        self.token = None
        self.session = None
        self.cols = {}
        self.events = deque(maxlen=200)
        self.telemetry = {}
        self.closing_sessions = {}
        self.notifications_enabled = False
        self.on_data = on_data
        self.on_warning = on_warning
        self.lock = asyncio.Lock()
        self.state = {'availability': 'not_checked', 'approval': 'not_checked', 'authorized': False, 'license': None, 'headsets': [], 'streams': [], 'next_action': 'Run diagnostics to inspect local Cortex.'}

    def event(self, operation, outcome, detail=None):
        self.events.append({'timestamp': time.time(), 'operation': operation, 'outcome': outcome, 'detail': redact(detail)})

    def report(self):
        return redact({**self.state, 'session_id': self.session, 'stream_delivery': self.delivery(), 'events': list(self.events), 'endpoint': 'wss://localhost:6868', 'generated_at': time.time(), 'session_open': bool(self.session), 'credentials_included': False})

    def delivery(self):
        now = time.time()
        result = {name: {**{k:v for k,v in item.items() if k != 'arrival_window'},
                       'timestamp_sample_rate': (item['sample_count']-1)/(item['last_timestamp']-item['first_timestamp']) if item['sample_count']>1 and item['last_timestamp']>item['first_timestamp'] else None,
                       'last_arrival_age': now-item['last_arrival'],
                       'receiving': self.notifications_enabled and now-item['last_arrival'] < (35 if name == 'met' else 5),
                       'observed_rate': (len(item['arrival_window'])-1)/(item['arrival_window'][-1]-item['arrival_window'][0]) if len(item['arrival_window'])>1 and item['arrival_window'][-1]>item['arrival_window'][0] else None}
                for name,item in self.telemetry.items()}
        for name in self.cols:
            result.setdefault(name, {'sample_count':0, 'session_id':self.session, 'receiving':False, 'last_arrival':None, 'last_arrival_age':None, 'last_timestamp':None, 'first_timestamp':None, 'observed_rate':None, 'cols':self.cols[name], 'values':[]})
        return result

    def notification(self, message):
        sid = message.get('sid')
        if not self.notifications_enabled or not self.session or sid != self.session:
            self.event('notification', 'rejected', {'session_id': sid, 'reason': 'inactive or foreign session'})
            return
        for name, cols in self.cols.items():
            if name not in message:
                continue
            values, stamp = message[name], message.get('time')
            import math
            if not isinstance(values, list) or len(values) != len(cols) or not isinstance(stamp, (int,float)) or not math.isfinite(stamp):
                self.event('notification:'+name, 'malformed', {'session_id':sid})
                continue
            now = time.time()
            item = self.telemetry.setdefault(name, {'sample_count':0, 'first_timestamp':stamp, 'session_id':sid, 'arrival_window':deque(maxlen=256)})
            item.update(last_timestamp=stamp, last_arrival=now, cols=cols, values=redact(values))
            item['sample_count'] += 1
            item['arrival_window'].append(now)
            if self.on_data:
                try:
                    self.on_data({'sid':sid,'time':stamp,name:values}, self.cols)
                except Exception as exc:
                    self.event('route:'+name, 'error', type(exc).__name__)

    def warning(self, w):
        detail = w.get('message')
        sid = detail.get('sessionId') if isinstance(detail,dict) else None
        expected = sid in self.closing_sessions
        foreign = sid is not None and sid != self.session
        self.event('warning', str(w.get('code')), {'message': detail, 'session_id':sid, 'intentional':expected, 'reason':self.closing_sessions.get(sid)})
        if w.get('code') in (0,1,3,100,101,102,103,113) and not expected and not foreign:
            self.notifications_enabled = False
            if self.on_warning:
                self.on_warning(w)
        if w.get('code') == 9:
            self.state['approval'] = 'approved'
        if w.get('code') == 3:
            self.token = None
            self.state['authorized'] = False

    async def open(self):
        async with self.open_lock:
            await self._open()

    async def _open(self):
        if self.socket is not None:
            return
        context = ssl.create_default_context()
        context.load_verify_locations(os.getenv('NSS_CORTEX_CA', str(ROOT / 'certificates/emotiv-rootCA.pem')))
        self.socket = await connect('wss://localhost:6868', ssl=context, open_timeout=6, max_queue=512, proxy=None)
        self.state['availability'] = 'reachable'
        self.reader = asyncio.create_task(self._receive())

    async def _receive(self):
        failure = None
        try:
            async for raw in self.socket:
                message = json.loads(raw)
                if any(name in message for name in ('eeg','dev','eq','met','mot','pow')):
                    self.notification(message)
                elif 'id' in message:
                    future = self.pending.get(message['id'])
                    if future and not future.done():
                        result = message.get('result')
                        if isinstance(result,dict) and isinstance(result.get('success'),list):
                            self.cols.update({x['streamName']:x['cols'] for x in result['success']})
                        future.set_result(message)
                elif 'warning' in message:
                    self.warning(message['warning'])
                else:
                    self.notification(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            failure = exc
        finally:
            self.socket = None
            self.notifications_enabled = False
            self.state['availability'] = 'disconnected'
            for f in self.pending.values():
                if not f.done():
                    f.set_exception(ConnectionError('Cortex socket disconnected'))
            if self.on_warning:
                self.on_warning({'code': 103, 'message': 'Cortex socket disconnected'})
            if failure:
                self.event('transport', 'disconnected', type(failure).__name__)

    async def call(self, method, params=None, caller=None):
        if method == 'updateSession':
            import inspect
            self.event('updateSession_request', 'requested', {'status':(params or {}).get('status'), 'session_id':(params or {}).get('session'), 'caller':caller or inspect.stack()[1].function})
        await self.open()
        self.seq += 1
        seq = self.seq
        future = asyncio.get_running_loop().create_future()
        self.pending[seq] = future
        try:
            request = {'id': seq, 'jsonrpc': '2.0', 'method': method}
            if params is not None:
                request['params'] = params
            await self.socket.send(json.dumps(request))
            result = await asyncio.wait_for(future, timeout=12)
            if 'error' in result:
                e = result['error']
                error = CortexError(e.get('code'), e.get('message', 'Unknown Cortex error'), method)
                self.event(method, 'error', error.report())
                raise error
            self.event(method, 'success')
            return result.get('result')
        finally:
            self.pending.pop(seq, None)

    async def diagnose(self, use_license=False, authenticate=True):
        async with self.lock:
            # Diagnostics never activate a session or debit quota.
            self.state['blocker'] = None
            try:
                info = await self.call('getCortexInfo')
                self.state['version'] = {k: info.get(k) for k in ('version', 'buildDate', 'buildNumber')}
                login = await self.call('getUserLogin')
                same_os = bool(login) and login[0].get('currentOSUId') == login[0].get('loggedInOSUId')
                self.state['account'] = {'logged_in': bool(login), 'same_os_account': same_os, 'email_verified': 'not exposed by getUserLogin', 'verification': 'Launcher account present' if login else 'Sign into EMOTIV Launcher'}
                if login and not same_os:
                    self.state['next_action'] = 'The logged-in Cortex user belongs to another Windows account. Sign in through Launcher under this Windows account.'
                    return self.report()
                c = credentials() if authenticate else {}
                if not c.get('clientId') or not c.get('clientSecret'):
                    self.state['next_action'] = 'Configure replacement app credentials locally with python -m backend.security, then rerun diagnostics.'
                    # Discovery may be unavailable until approval; preserve the exact rejection.
                    try:
                        self.state['headsets'] = await self.call('queryHeadsets')
                    except CortexError:
                        pass
                    return self.report()
                self.token = None
                self.state['authorized'] = False
                self.state['license'] = None
                params = {k: c[k] for k in ('clientId', 'clientSecret')}
                access = await self.call('requestAccess', params)
                approved = access.get('accessGranted', False)
                self.state['approval'] = 'approved' if approved else 'awaiting_launcher_approval'
                if not approved:
                    self.state['next_action'] = 'Approve NeuralSignalStudio in EMOTIV Launcher, then rerun diagnostics.'
                    return self.report()
                if use_license:
                    if not c.get('license'):
                        raise ValueError('No optional license configured locally.')
                    params['license'] = c['license']
                result = await self.call('authorize', params)
                self.token = result['cortexToken']
                self.selected_license = params.get('license')
                remember(self.token)
                self.state['authorized'] = True
                lic = await self.call('getLicenseInfo', {'cortexToken': self.token})
                # Strict summary prevents identifiers or nested credentials entering reports.
                l = lic.get('license', {})
                self.state['license'] = {k: l.get(k) for k in ('licenseName', 'scopes', 'expired', 'validFrom', 'validTo', 'localQuota', 'totalRegisteredDevices', 'deviceInfo', 'hardLimitTime')}
                self.state['license']['isOnline'] = lic.get('isOnline')
                if result.get('warning'):
                    self.event('authorize', 'warning', result['warning'])
                await self.call('controlDevice', {'command': 'refresh'})
                await asyncio.sleep(2)
                self.state['headsets'] = await self.call('queryHeadsets')
                self.state['next_action'] = 'Headset already connected. Open a permitted-stream session; raw EEG requires EEG scope.' if any(h.get('status') == 'connected' for h in self.state['headsets']) else 'Select the MN8 and explicitly connect. Discovery alone is not a connection.'
            except CortexError as e:
                self.state['next_action'] = e.report()['action']
                self.state['blocker'] = e.report()
                # Discovery and authorization are independent facts even if licensing fails.
                try:
                    self.state['headsets'] = await self.call('queryHeadsets')
                except Exception:
                    pass
            except Exception as e:
                self.state['next_action'] = 'Open EMOTIV Launcher; verify local Cortex and its trusted certificate. ' + redact(str(e))
                self.event('diagnostic', 'error', {'type': type(e).__name__, 'message': redact(str(e))})
                if not self.socket:
                    self.state['availability'] = 'unreachable'
            return self.report()

    async def connect_headset(self, headset_id, activate=False, debit_one=False):
        async with self.lock:
            if not self.token:
                raise ValueError('Authorize the application through diagnostics first.')
            if self.session:
                raise ValueError('Stop the current source before opening another Cortex session.')
            if not any(h.get('id') == headset_id and h.get('status') == 'connected' for h in self.state['headsets']):
                await self.call('controlDevice', {'command': 'connect', 'headset': headset_id})
            deadline = time.monotonic() + 25
            headset = None
            while time.monotonic() < deadline:
                headsets = await self.call('queryHeadsets')
                self.state['headsets'] = headsets
                headset = next((h for h in headsets if h['id'] == headset_id and h.get('status') == 'connected'), None)
                if headset:
                    break
                await asyncio.sleep(1)
            if not headset:
                self.event('connect', 'timeout', 'No queryHeadsets confirmation of connected status.')
                raise ValueError('Headset connection was not confirmed. Review warnings and entitlement; no session was created.')
            self.event('connect', 'verified', {'headset': headset_id, 'status': 'connected'})
            if activate and 'eeg' not in ((self.state.get('license') or {}).get('scopes') or []):
                raise ValueError('Verified license has no EEG scope. No quota debit or activation attempted.')
            if debit_one:
                if not activate:
                    raise ValueError('Quota allocation requires an explicit active EEG session request.')
                c = credentials()
                quota_params = {'clientId': c['clientId'], 'clientSecret': c['clientSecret'], 'debit': 1}
                if getattr(self, 'selected_license', None):
                    quota_params['license'] = self.selected_license
                result = await self.call('authorize', quota_params)
                self.token = result['cortexToken']
                remember(self.token)
            scopes = (self.state.get('license') or {}).get('scopes') or []
            if activate and 'eeg' not in scopes:
                raise ValueError('Verified license has no EEG scope. No session activation attempted.')
            session = await self.call('createSession', {'cortexToken': self.token, 'headset': headset_id, 'status': 'active' if activate else 'open'})
            self.session = session['id']
            self.telemetry = {}
            self.notifications_enabled = True
            self.recovery_attempts = 0
            self.desired_streams = ['dev','eq','met','mot','pow'] + (['eeg'] if activate else [])
            result = await self.call('subscribe', {'cortexToken': self.token, 'session': self.session, 'streams': ['dev', 'eq', 'met', 'mot', 'pow'] + (['eeg'] if activate else [])})
            self.cols = {s['streamName']: s['cols'] for s in result.get('success', [])}
            self.state['subscribe_response'] = redact(result)
            self.event('subscribe_response', 'received', result)
            self.state['streams'] = result.get('success', [])
            self.state['next_action'] = 'Subscribed; inspect per-stream delivery counters. Raw EEG unavailable.' if 'eeg' not in self.cols else 'Subscribed; inspect actual EEG delivery counters.'
            for failure in result.get('failure', []):
                self.event('subscribe:' + failure.get('streamName', '?'), 'error', CortexError(failure.get('code'), failure.get('message'), 'subscribe').report())
            eeg = self.cols.get('eeg', [])
            channels = [c for c in eeg if isinstance(c, str) and c not in EEG_METADATA]
            rate = (headset.get('settings') or {}).get('eegRate') or headset.get('samplingRate') or 128
            return Source('cortex:' + headset_id, 'cortex', headset.get('customName') or headset_id, channels, ['µV'] * len(channels), float(rate), 'Cortex Unix seconds UTC', bool(headset.get('isVirtual')), {'headset': headset, 'cols': self.cols, 'session': self.session, 'nominal_rate_note': 'headset settings.eegRate or documented 128 Hz fallback; compare observed rate'})

    async def reconcile(self, recover=False):
        """Verify server truth; recovery reuses only the existing session, never activates."""
        async with self.lock:
            if not self.token:
                return {'status':'unauthorized'}
            sessions = await self.call('querySessions', {'cortexToken':self.token})
            self.state['sessions'] = [{'id':x.get('id'), 'status':x.get('status'), 'streams':x.get('streams',[]), 'headset':(x.get('headset') or {}).get('id')} for x in sessions]
            self.state['reconciled_at'] = time.time()
            current = next((x for x in sessions if x.get('id') == self.session), None)
            if not current or current.get('status') not in ('opened','open','active','activated'):
                self.notifications_enabled = False
                self.state['session_status'] = 'missing_or_closed'
                self.state['next_action'] = 'Session missing or closed. Explicitly stop and reconnect; no automatic session creation.'
                return {'status':'missing_or_closed'}
            self.state['session_status'] = current['status']
            server_streams = current.get('streams', [])
            missing = [name for name in self.desired_streams if name not in server_streams]
            if missing:
                self.notifications_enabled = False
                if recover and self.recovery_attempts < 1:
                    self.recovery_attempts += 1
                    self.event('subscription_recovery', 'attempt', {'session_id':self.session,'streams':missing})
                    self.notifications_enabled = True
                    result = await self.call('subscribe', {'cortexToken':self.token,'session':self.session,'streams':missing})
                    self.state['subscribe_response'] = redact(result)
                    self.event('subscribe_response','recovery',result)
                    self.cols.update({x['streamName']:x['cols'] for x in result.get('success',[])})
                    self.state['streams'] = [{'streamName':name,'cols':cols,'sid':self.session} for name,cols in self.cols.items() if name in server_streams or name in [x['streamName'] for x in result.get('success',[])]]
                    self.notifications_enabled = not bool(result.get('failure'))
                return {'status':'missing_subscriptions','missing':missing}
            self.notifications_enabled = True
            return {'status':'verified','session_id':self.session,'streams':server_streams}

    async def close_session(self, reason='explicit stop or source switch'):
        if self.session:
            self.closing_sessions[self.session] = reason
            if len(self.closing_sessions) > 32:
                self.closing_sessions.pop(next(iter(self.closing_sessions)))
            self.event('session_teardown', 'requested', {'session_id': self.session, 'reason':reason})
            self.notifications_enabled = False
            self.desired_streams = []
            self.state['session_status'] = 'closing'
            try:
                await self.call('updateSession', {'cortexToken': self.token, 'session': self.session, 'status': 'close'})
            finally:
                self.session = None
                self.cols = {}
                self.state['streams'] = []

    async def close(self):
        with contextlib.suppress(Exception):
            await self.close_session()
        if self.socket:
            await self.socket.close()
        if self.reader:
            self.reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.reader


def decode_eeg(message, cols):
    labels = cols.get('eeg', [])
    values = message.get('eeg', [])
    if len(labels) != len(values):
        raise ValueError('EEG sample length differs from subscription cols; refusing ambiguous mapping.')
    mapping = dict(zip(labels, values))
    return Sample(float(message['time']), [float(v) for c, v in zip(labels, values) if c not in EEG_METADATA], mapping.get('COUNTER'), bool(mapping.get('INTERPOLATED')), {'sid': message.get('sid'), 'cortex': mapping})
