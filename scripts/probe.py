"""Read-only local integration audit. No authentication, session activation or recording."""
import asyncio
import json
from pathlib import Path
import tempfile
from backend.cortex import Cortex
from backend.sources import Acquisition
from backend.storage import Store, Recorder


async def main():
    c = Cortex()
    report = {'credentials_used': False}
    try:
        report['cortex_info'] = await c.call('getCortexInfo')
        login = await c.call('getUserLogin')
        report['account_logged_in'] = bool(login)
        try:
            report['headsets'] = await c.call('queryHeadsets')
        except Exception as e:
            report['headset_query'] = str(e)
    except Exception as e:
        report['transport_error'] = str(e)
    finally:
        await c.close()
    with tempfile.TemporaryDirectory(prefix='nss-probe-') as temp:
        store = Store(Path(temp) / 'probe.sqlite3')
        a = Acquisition(Recorder(store), store)
        report['lsl'] = await a.discover_lsl()
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/local-audit.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


asyncio.run(main())
