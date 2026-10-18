"""Real-time synthetic acquisition / concurrent display / durable recording check.

Uses an isolated temporary database. Never touches hardware, credentials or user sessions.
"""
import asyncio
import argparse
import json
from pathlib import Path
import tempfile
import time
from backend.storage import Store, Recorder
from backend.sources import Acquisition, synthetic


async def run(seconds):
    with tempfile.TemporaryDirectory(prefix='nss-validation-') as temp:
        store = Store(Path(temp) / 'validation.sqlite3')
        recorder = Recorder(store)
        source = Acquisition(recorder, store)
        await source.demo()
        sid = recorder.start('Synthetic concurrent validation', 'synthetic-test', source.source)
        processing = asyncio.create_task(source.process())
        began = time.monotonic()
        frames = 0
        while time.monotonic() - began < seconds:
            frame = await source.frame(10, filtered=True, notch=50)
            frames += 1
            await asyncio.sleep(.1)
        # Freeze the source at a defined sample boundary before comparing counts.
        source.task.cancel()
        try:
            await source.task
        except asyncio.CancelledError:
            pass
        source.task = None
        await asyncio.to_thread(recorder.stop)
        status = source.state()
        samples = store.read(sid, limit=32768)
        assert len(samples) == recorder.count == status['total_samples']
        for sample in samples:
            assert sample.values == synthetic(sample.metadata['sample_index']).values
        assert status['discontinuities'] == 0
        assert status['features']['available']
        assert recorder.error is None
        result = {'duration_seconds': round(time.monotonic()-began,2), 'received_and_reopened_samples':len(samples), 'observed_rate':status['observed_rate'], 'display_frames':frames, 'discontinuities':status['discontinuities'], 'raw_values_exact':True, 'peak_hz':status['features']['peak_hz'], 'recording_error':recorder.error, 'source':'synthetic only'}
        await source.stop()
        processing.cancel()
        try:
            await processing
        except asyncio.CancelledError:
            pass
        Path('artifacts').mkdir(exist_ok=True)
        Path('artifacts/soak-result.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2))


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--seconds',type=float,default=60)
    args=parser.parse_args()
    asyncio.run(run(args.seconds))
