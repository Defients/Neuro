import asyncio
from collections import deque
import contextlib
import math
import time
import numpy as np
from .models import Source, Sample
from .cortex import Cortex, decode_eeg
from .processing import analyze, active_metrics, filter_values


def synthetic(index, rate=128, epoch=0):
    # Index-only deterministic fixture, no random generator or wall-clock dependency.
    t = index / rate
    envelope = 1 + .28 * math.sin(t * .3)
    left = envelope * 18 * math.sin(2 * math.pi * 10 * t) + 6 * math.sin(2 * math.pi * 5 * t) + 3 * math.sin(2 * math.pi * 22 * t)
    right = envelope * 15 * math.sin(2 * math.pi * 10 * t + .65) + 8 * math.sin(2 * math.pi * 6 * t) + 4 * math.sin(2 * math.pi * 18 * t)
    return Sample(epoch + t, [left, right], index % rate, metadata={'fixture': 'deterministic-v1', 'sample_index': index})


class Acquisition:
    def __init__(self, recorder, store):
        self.recorder, self.store = recorder, store
        self.buffer = deque(maxlen=32768)
        self.source = None
        self.task = None
        self.total = 0
        self.gaps = 0
        self.interpolated = 0
        self.last = None
        self.last_arrival = None
        self.started = None
        self.error = None
        self.features = {'available': False, 'reason': 'No data source selected.'}
        self.metrics = None
        self.quality = None
        self.quality_at = None
        self.battery = None
        self.annotations = deque(maxlen=100)
        self.lsl_streams = {}
        self.lsl_report = {'checked': False, 'streams': []}
        self.cortex = Cortex(self._cortex_data, self._warning)
        self.processing_task = None
        self.replay_speed = 1.0
        self.last_reconcile = 0
        self.transition = asyncio.Lock()

    def reset(self, source):
        self.source = source
        self.buffer.clear()
        self.total = self.gaps = self.interpolated = 0
        self.last = self.last_arrival = None
        self.started = time.time()
        self.error = self.metrics = self.quality = self.quality_at = self.battery = None
        self.features = {'available': False, 'reason': 'Waiting for two seconds of contiguous data.'}
        self.annotations.clear()

    async def stop(self, reason="explicit stop"):
        if self.recorder.sid:
            await asyncio.to_thread(self.recorder.stop)
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task
            self.task = None
        if self.source and self.source.kind == 'cortex':
            try:
                await self.cortex.close_session(reason=reason)
            except Exception as exc:
                # A dead hardware transport must not block demo, replay, or local UI access.
                self.cortex.event('closeSession', 'transport_error', type(exc).__name__)
        self.source = None
        self.buffer.clear()
        self.last = self.last_arrival = self.started = None
        self.total = self.gaps = self.interpolated = 0
        self.error = None
        self.quality = self.quality_at = self.battery = None
        self.features = {'available': False, 'reason': 'Source stopped.'}
        self.metrics = None

    def ingest(self, samples):
        if not self.source:
            return
        accepted = []
        for s in samples:
            if len(s.values) != len(self.source.channels) or not math.isfinite(s.timestamp) or not all(math.isfinite(x) for x in s.values):
                self.error = 'Invalid sample rejected: non-finite value or channel mapping mismatch.'
                self.gaps += 1
                self.last = None
                continue
            if self.last is not None:
                dt = s.timestamp - self.last
                if dt <= 0:
                    s.discontinuity = 'out_of_order_or_clock_reset'
                elif self.source.nominal_rate > 0 and dt > 1.8 / self.source.nominal_rate:
                    s.discontinuity = 'missing_samples_or_clock_jump'
                if s.discontinuity:
                    self.gaps += 1
            self.interpolated += int(s.interpolated)
            self.last = s.timestamp
            self.last_arrival = time.time()
            self.total += 1
            self.buffer.append(s)
            accepted.append(s)
        if accepted:
            self.recorder.append(accepted)

    async def demo(self):
        await self.stop(reason="select synthetic source")
        self.reset(Source('synthetic-v1', 'synthetic', 'Synthetic · two-channel fixture', ['SIM-L', 'SIM-R'], ['µV', 'µV'], 128, 'Unix UTC epoch + sample index / 128', True, {'generator': 'deterministic-v1', 'hardware': 'None', 'seed': 'analytic fixture'}))
        self.task = asyncio.create_task(self._demo())

    async def _demo(self):
        epoch, start, index = time.time(), time.monotonic(), 0
        while True:
            target = int((time.monotonic() - start) * 128)
            samples = [synthetic(i, epoch=epoch) for i in range(index, min(target, index + 128))]
            self.ingest(samples)
            index += len(samples)
            await asyncio.sleep(.05)

    async def discover_lsl(self):
        try:
            from pylsl import resolve_streams
            streams = await asyncio.to_thread(resolve_streams, 2.0)
            self.lsl_streams = {s.uid(): s for s in streams}
            result = []
            for s in streams:
                result.append({'id': s.uid(), 'name': s.name(), 'type': s.type(), 'channels': s.channel_count(), 'nominal_rate': s.nominal_srate(), 'origin': s.hostname(), 'source_id': s.source_id(), 'eeg_candidate': s.type().lower() == 'eeg' and s.nominal_srate() > 0})
            self.lsl_report = {'checked': True, 'streams': result, 'error': None, 'checked_at': time.time(), 'duplication_note': 'Cortex and LSL may represent the same physical headset. Only one source may be acquired at a time; compare source IDs before switching.'}
        except Exception as e:
            self.lsl_report = {'checked': True, 'streams': [], 'error': 'LSL discovery unavailable: ' + type(e).__name__ + ': ' + str(e), 'checked_at': time.time()}
        return self.lsl_report

    async def lsl(self, uid):
        if uid not in self.lsl_streams:
            raise ValueError('Discover LSL streams and select an existing UID first.')
        from pylsl import StreamInlet
        stream = self.lsl_streams[uid]
        if stream.type().lower() != 'eeg' or stream.nominal_srate() <= 0:
            raise ValueError('Only regularly sampled EEG streams are supported in this version.')
        await self.stop(reason='select LSL source')
        inlet = await asyncio.to_thread(StreamInlet, stream, max_buflen=10, recover=True, processing_flags=0)
        try:
            info = await asyncio.to_thread(inlet.info, 5)
            xml = info.as_xml()
            node = info.desc().child('channels').child('channel')
            labels, units = [], []
            for i in range(info.channel_count()):
                labels.append(node.child_value('label') or f'CH{i+1}')
                units.append(node.child_value('unit') or 'unspecified')
                node = node.next_sibling()
            correction = await asyncio.to_thread(inlet.time_correction, 5)
            self.reset(Source('lsl:' + uid, 'lsl', info.name(), labels, units, info.nominal_srate(), 'Remote LSL local_clock (unprocessed); correction metadata retained', False, {'xml': xml, 'source_id': info.source_id(), 'hostname': info.hostname(), 'time_correction': correction, 'units_note': 'Values preserved in stream-declared units; no implicit conversion', 'provenance_note': 'LSL transport verified; publisher hardware origin is self-declared and must be checked by participant.'}))
            self.task = asyncio.create_task(self._lsl(inlet))
        except Exception:
            inlet.close_stream()
            raise

    async def _lsl(self, inlet):
        try:
            last_correction = time.monotonic()
            while True:
                chunk, timestamps = await asyncio.to_thread(inlet.pull_chunk, .2, 256)
                self.ingest([Sample(t, list(map(float, v)), metadata={'time_correction': self.source.metadata['time_correction']}) for t, v in zip(timestamps, chunk)])
                if time.monotonic() - last_correction > 30:
                    self.source.metadata['time_correction'] = await asyncio.to_thread(inlet.time_correction, 2)
                    last_correction = time.monotonic()
                await asyncio.sleep(.01)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.error = 'LSL acquisition stopped: ' + type(e).__name__
        finally:
            await asyncio.to_thread(inlet.close_stream)

    async def connect_cortex(self, headset, activate, debit):
        if self.source and self.source.kind == 'cortex' and self.source.id == 'cortex:' + headset and self.cortex.session:
            if activate == ('eeg' in self.cortex.cols) and not debit and self.cortex.notifications_enabled:
                self.cortex.event('connect', 'reused_session', {'session_id':self.cortex.session})
                return
            raise ValueError('Stop the current Cortex source explicitly before changing session mode or retrying interrupted subscriptions.')
        await self.stop(reason='select Cortex source')
        try:
            source = await self.cortex.connect_headset(headset, activate, debit)
            self.reset(source)
            for name, item in self.cortex.telemetry.items():
                self._cortex_data({'sid':self.cortex.session,'time':item['last_timestamp'],name:item['values']}, self.cortex.cols)
        except Exception:
            with contextlib.suppress(Exception):
                await self.cortex.close_session()
            raise

    def _cortex_data(self, message, cols):
        if not self.source or self.source.kind != 'cortex' or message.get('sid') != self.cortex.session:
            return
        try:
            if 'eeg' in message:
                self.ingest([decode_eeg(message, cols)])
            for stream in ('met', 'eq', 'dev', 'mot', 'pow'):
                if stream not in message:
                    continue
                stamp = float(message['time'])
                self.recorder.event('cortex:' + stream, {'cols': cols.get(stream), 'values': message[stream], 'sid': message.get('sid')}, stamp)
                if stream == 'met':
                    self.metrics = active_metrics(cols.get('met', []), message['met'], stamp, time.time())
                if stream == 'eq':
                    d = dict(zip(cols.get('eq', []), message['eq']))
                    q = d.get('overall')
                    self.quality = float(q) if isinstance(q,(int,float)) and not isinstance(q,bool) and math.isfinite(q) and 0 <= q <= 100 else None
                    self.battery = d.get('batteryPercent')
                    self.quality_at = stamp
        except Exception as e:
            self.error = 'Cortex sample rejected: ' + str(e)

    def _warning(self, warning):
        if self.source and self.source.kind == 'cortex':
            self.error = 'Cortex warning ' + str(warning.get('code')) + ': acquisition interrupted. Review diagnostics.'
            self.last_arrival = None
            self.metrics = None
            self.quality = None
            if self.recorder.sid:
                self.recorder.error = self.error
                asyncio.create_task(asyncio.to_thread(self.recorder.stop))

    async def replay(self, sid, speed):
        info = self.store.get(sid)
        if info['status'] == 'recording':
            raise ValueError('Stop a recording before replay.')
        await self.stop(reason='select replay')
        source = Source(**info['source'])
        source.metadata = {**source.metadata, 'recording_id': sid, 'original_source_kind': source.kind}
        source.kind = 'replay'
        source.name = 'Replay · ' + info['title']
        self.reset(source)
        self.replay_speed = speed
        self.task = asyncio.create_task(self._replay(sid))

    async def _replay(self, sid):
        offset = 0
        event_offset = 0
        events = await asyncio.to_thread(self.store.events, sid, event_offset, 256)
        event_index = 0
        while True:
            samples = await asyncio.to_thread(self.store.read, sid, offset, 32)
            if not samples:
                self.error = 'Replay complete. Original timestamps and values preserved.'
                return
            self.ingest(samples)
            # Keep participant annotations distinct from EEG and proprietary metrics.
            while events and event_index < len(events) and events[event_index]['timestamp'] <= samples[-1].timestamp:
                event = events[event_index]
                if event['kind'] in ('marker', 'self_report', 'task'):
                    payload = event['payload']
                    self.annotations.appendleft({**payload, 'persisted': True, 'replayed': True})
                event_index += 1
                if event_index == len(events):
                    event_offset += len(events)
                    events = await asyncio.to_thread(self.store.events, sid, event_offset, 256)
                    event_index = 0
            offset += len(samples)
            await asyncio.sleep(len(samples) / max(self.source.nominal_rate, 1) / self.replay_speed)

    async def process(self):
        while True:
            if self.source and self.source.kind == 'cortex' and time.monotonic()-self.last_reconcile > 5:
                self.last_reconcile = time.monotonic()
                try:
                    async with self.transition:
                        await self.cortex.reconcile(recover=True)
                except Exception as exc:
                    self.cortex.event('reconcile','error',type(exc).__name__)
            if self.source and self.buffer:
                data = list(self.buffer)[-min(8192, int(self.source.nominal_rate * 8)):]
                self.features = await asyncio.to_thread(analyze, data, self.source.nominal_rate)
            if self.recorder.error and self.recorder.sid:
                await asyncio.to_thread(self.recorder.stop)
            await asyncio.sleep(1)

    def state(self):
        now = time.time()
        fresh = self.last_arrival is not None and now - self.last_arrival < 2
        recent = list(self.buffer)[-2048:]
        regular = [s for s in recent if not s.discontinuity]
        rate = (len(regular) - 1) / (regular[-1].timestamp - regular[0].timestamp) if len(regular) > 1 and regular[-1].timestamp > regular[0].timestamp else None
        metrics = dict(self.metrics) if self.metrics else None
        if metrics and now - metrics['timestamp'] > 15:
            metrics.update(attention=None, cognitiveStress=None, stale=True)
        quality = self.quality if self.quality_at and now - self.quality_at < 5 and self.cortex.notifications_enabled else None
        delivery = self.cortex.delivery() if self.source and self.source.kind == 'cortex' else {}
        return {'cortex_session_id':self.cortex.session if self.source and self.source.kind == 'cortex' else None, 'cortex_session_status':self.cortex.state.get('session_status','unverified'), 'cortex_connected':any(h.get('status')=='connected' for h in self.cortex.state['headsets']), 'cortex_delivery':delivery, 'cortex_subscribed':list(self.cortex.cols) if self.cortex.notifications_enabled and self.source and self.source.kind == 'cortex' else [], 'raw_eeg_available':bool(self.source and self.source.channels), 'receiving_samples':any(x['receiving'] for x in delivery.values()) or fresh, 'source': self.source.to_dict() if self.source else None, 'arriving': fresh, 'total_samples': self.total, 'observed_rate': rate, 'discontinuities': self.gaps, 'interpolated': self.interpolated, 'last_sample_age': now - self.last_arrival if self.last_arrival else None, 'duration': now - self.started if self.started else 0, 'error': self.error, 'quality': quality, 'battery': self.battery, 'metrics': metrics, 'features': self.features if fresh else {'available': False, 'reason': self.error or 'No recent EEG samples.'}, 'recording': self.recorder.status(), 'annotations': list(self.annotations), 'replay_speed': self.replay_speed, 'buffer_samples': len(self.buffer)}

    async def frame(self, seconds=10, filtered=False, notch=0):
        state = self.state()
        data = list(self.buffer)
        if data:
            threshold = data[-1].timestamp - seconds
            data = [s for s in data if s.timestamp >= threshold][-8192:]
        values = [s.values for s in data]
        if filtered and values and self.source:
            # Each uninterrupted segment is filtered separately. Gaps are never bridged.
            transformed = np.asarray(values)
            starts = [0] + [i for i, s in enumerate(data) if i > 0 and (s.discontinuity or s.interpolated)] + [len(data)]
            for lo, hi in zip(starts, starts[1:]):
                transformed[lo:hi] = await asyncio.to_thread(filter_values, transformed[lo:hi], self.source.nominal_rate, notch)
            values = transformed.tolist()
        state['waveform'] = {'timestamps': [s.timestamp for s in data], 'values': values, 'gaps': [i for i, s in enumerate(data) if s.discontinuity or s.interpolated], 'filtered': filtered}
        return state
