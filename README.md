# NeuralSignalStudio · v0.1

Local-first EEG instrumentation and expressive neurofeedback for Windows. React/TypeScript/uPlot frontend, asyncio/FastAPI acquisition, NumPy/SciPy analysis, and local SQLite WAL recordings. All six workspaces run without a headset. This is research software, not a medical diagnostic system or validated emotion detector.

## Run now

From PowerShell in `C:\myProjects\neuro`:

```powershell
.\scripts\start.ps1
```

Open **http://localhost:8080**. The production frontend and local API share port 8080. Stop with Ctrl+C. Dependencies and the production build are already installed in this workspace. If PowerShell blocks scripts, run `powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1` for this invocation only, or use the direct command:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8080 --no-access-log
```

For a fresh installation, use Python 3.12 (recommended; 3.15 is not tested):

```powershell
.\scripts\setup.ps1
# Or: .\scripts\setup.ps1 -Python C:\Path\To\Python312\python.exe
.\scripts\start.ps1
```

Setup uses the installed Codex Python 3.12 runtime when available, otherwise `py -3.12`. Dependencies live in `.venv`; no global Python packages are changed. `npm ci` uses the committed lockfile. Reproducible Python versions are listed in `requirements.lock.txt` (install with `pip install -r requirements.lock.txt`).

## Hardware status observed on October 17, 2026

| Category | Evidence |
|---|---|
| VERIFIED locally | Empty initial workspace; Windows; Node 24.21.0; isolated Python 3.12.14; Launcher installed; Cortex Windows service running. |
| VERIFIED locally | `getCortexInfo` succeeds over **verified** TLS at `wss://localhost:6868`; Cortex **4.13.5.3**, build `7c7e51d`. `getUserLogin` returns a logged-in account. |
| VERIFIED locally | `queryHeadsets` returned `[]` during the audit; two-second LSL resolution returned no streams. These are point-in-time observations, not proof the headset cannot become available. |
| BLOCKED / UNVERIFIED | Replacement app credentials are absent. Approval, authorization, license scopes, quota, registered-device count and actual headset connection have not been verified. No real EEG samples or real streams have been demonstrated. |
| IMPLEMENTED, not hardware-tested | Credential-backed authorization, license inspection, refresh/discovery, confirmed headset connection, session activation and stream subscription; LSL inlet and original-clock capture. |
| SIMULATED and verified | Deterministic two-channel 128 Hz fixture; waveform, recording, offline spectra, replay, CSV+metadata export, markers and responsive aura. Never substituted for hardware data. |

The previously reported activation restriction is user-provided context. No `-32022` was reproduced because no credential-backed activation was attempted. Do not assume a developer license resolves that restriction.

The initial read-only audit is in `artifacts/local-audit.json` (ignored by Git). Repeat with `.\.venv\Scripts\python.exe -m scripts.probe`. The probe never authorizes, activates or records.

## Configure Cortex securely

1. Revoke the secret previously exposed in conversation in your EMOTIV developer account. Generate a replacement; never paste it into chat.
2. Review the `NeuralSignalStudio` app registration. For MN8, check whether **Enable EEG for Professional devices** was unnecessarily selected. The app cannot verify your developer-portal registration without authorization.
3. Run the following locally. The prompts hide all values and store them in **Windows Credential Manager**, under `NeuralSignalStudio.Cortex`.

   ```powershell
   .\.venv\Scripts\python.exe -m backend.security
   ```

4. Open Launcher and sign into the intended account under the same Windows user. Open **Connection & Diagnostics → Run diagnostics**, approve the app in Launcher, and rerun diagnostics.
5. Automatic license selection is the default. An optional locally stored license is used only when explicitly selected. Inspect returned scopes, expiry, device limit, registered devices and quota.
6. Turn on the MN8 and scan again. **Discovered is not connected**. Select the headset and explicitly authorize local acquisition. Check **Activate an EEG session** only when you intend EEG access and the verified license permits it. If local quota is zero, explicit allocation of one session is available; there is no quota retry loop.
7. The backend waits up to 25 seconds for `queryHeadsets` to confirm `connected`, then opens a session and inspects individual subscription results and `cols`. A successful connect command alone never creates a session.

Environment alternatives for development: `NSS_CORTEX_CLIENT_ID`, `NSS_CORTEX_CLIENT_SECRET`, optional `NSS_CORTEX_LICENSE_ID`. Set them **only in the trusted backend process environment**. Do not put secrets into frontend/Vite variables or source files. Environment configuration cannot prove that a secret has been rotated; that remains the owner's responsibility. Clear OS credentials with `python -m backend.security --clear`.

TLS verification uses the OS trust roots plus the public EMOTIV Root CA in `certificates/emotiv-rootCA.pem`, applied only to the local Cortex client context. Hostname verification remains enabled. `NSS_CORTEX_CA` may point at an operator-verified replacement CA. The application never disables TLS verification or modifies system trust.

If `-32022` occurs, arrange an activation transfer or entitlement change with EMOTIV. If `-32232` occurs, review the Professional EEG app registration. The backend retains exact sanitized errors and legitimate recovery steps. It never manipulates licensing files or hardware identities.

## What works

- **Live Monitor:** explicit source selection; bounded waveform buffers; raw/filtered display, 5–30 second windows, amplitude scaling, pause, drag zoom and cursor; separate channel labels; observed sampling rate, discontinuities and interpolation counts; Advanced spectrogram and notch controls; Research metadata.
- **Connection & Diagnostics:** correlated JSON-RPC transport, asynchronous warnings, version/account summary, approval, automatic/manual license selection, discovery, confirmed connection, stream mappings and per-stream errors; redacted JSON report. Diagnostics do not debit or activate sessions.
- **Three source adapters:** Cortex, existing regularly sampled EEG LSL publishers, and deterministic simulation. One source at a time; switching explicitly stops/persists the current recording. No silent fallback. LSL hardware identity is self-declared by the publisher and must be checked locally.
- **Recordings:** explicit participant consent, pseudonymous IDs, session titles, manual markers and separately tagged self-reports; original values/timestamps/channel order and Cortex metadata; bounded writer queue, periodic durable commits, interruption recovery, search and paged replay at 0.25–4×. Replay cannot be re-recorded as new hardware data.
- **Analysis:** Welch spectra and integrated relative bands, contiguous data checks, display-only zero-phase filter, recorded-region analysis (up to 120 seconds / 32,768 samples) and selected-region ZIP export. Exports contain `raw.csv`, source/processing/provenance `metadata.json`, and `events.json`.
- **Neural State:** separate observed signal, proprietary MN8 estimates and experimental interpretation layers. Attention/cognitiveStress require active flags, valid values and freshness. No made-up Cortex metrics in demo mode. Aura/feature avatar map first-channel RMS to visual energy. Real-source visuals suspend when quality is unknown, stale or below 50/100.
- **Experiments:** task context and 0–10 valence, arousal, perceived stress, focus and report-confidence ratings. Annotations are temporary unless a recording is active; the UI states whether they were persisted.
- **Security:** loopback binding, Host/Origin validation, cross-origin write rejection, local write header for CLI clients, WebSocket origin checks, CSP, no credential API, sanitized diagnostics, no automatic uploads.

## Provenance and technical limits

Raw samples are append-only JSON payloads in SQLite with original floating-point values and acquisition timestamps. `received_at` is a separate backend wall-clock timestamp. Cortex counters, interpolation, markers, raw contact quality and session identity remain in sample metadata; auxiliary `met`, `dev`, `eq`, `mot` and `pow` streams are recorded as separate events with their `cols` mapping. The UI currently consumes EEG quality and battery from `eq`; motion and `dev` are preserved but do not have dedicated visualizations yet.

LSL auto timestamp processing is disabled. Original remote `local_clock` timestamps, stream XML and inlet time-correction estimates are preserved. Reconstruct local alignment with `timestamp + time_correction`. This is not XDF. An LSL stream alone is not evidence of a physical headset's identity or licensing.

The live display shows at most eight channels and 8,192 samples; the acquisition buffer holds 32,768 samples. All acquired channels remain in recordings. Waveforms are median-centered for viewing; stored values and raw PSD are unchanged. Display filtering is applied separately across discontinuities and never changes stored raw data. PSD uses the latest uninterrupted non-interpolated segment; gaps are never filled. Source-native units are retained; LSL values are not assumed to be microvolts.

Rendering is independent of acquisition and disk persistence. Writer pressure or disk failure makes recording visibly inactive, preserving committed samples rather than silently dropping a growing queue. Commits occur at least approximately every 100 ms under normal load; an abrupt power/process failure can lose the current in-memory batch. Startup marks unfinished sessions `recovered`. SQLite provides durability, not encryption: local recordings inherit the Windows account's file permissions. Protect the Windows account/device as appropriate for participant data.

Replay keeps original timestamps and source identity. Stream age is time since local replay delivery. EEG acquisition does not automatically reconnect or activate a new paid session after failure. A source restart requires an explicit user action. The app never invokes Cortex cloud recording APIs.

Session listing is capped at 200 results and the session-detail endpoint returns the first 2,000 events. ZIP exports stream all events without that limit; replay pages through annotations. There is no sustained hours-long physical headset test. Visuals are expressive mappings, not whole-brain imaging or emotion classification. The avatar is a simple procedural feature display.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm run build
```

The final verification run passed **27 tests**. Tests exercise deterministic 10 Hz peaks, filter attenuation, gap/interpolation rejection, active/stale MN8 metrics, subscription channel order, discontinuities and bounded memory, exact recording round trips and selected CSV export, crash recovery, writer overflow, sanitized errors, connection-confirmation gating, partial subscriptions, RPC correlation, origin/consent checks, WebSocket payloads, authorization sequencing, disconnect recovery and demo record/export/replay integration. Full results are documented in `docs/DELIVERY.md`.

Optional frontend development: start the backend on 8080 and run `npm run dev` in a second terminal (Vite on 5173 proxies `/api` and `/ws`). Rebuild and restart the backend after production frontend changes. Tests use temporary databases and fake Cortex responses; they never authenticate with real credentials or acquire participant data.

## Next priorities

1. Replace credentials, approve the app, verify license details and connect the real MN8; capture documented real sample counts, channel mapping, rate and duration.
2. Prove long-session stability with the available legitimate source; extend LSL reconnect/clock alignment validation and actual MN8 device metadata handling.
3. Expand event/library pagination, indexed region selection, replay seeking, motion/quality views and import/export formats (XDF/EDF+).
4. Add opt-in OBS overlay and Tauri 2 packaging after hardware validation.
5. Collect session-separated labels; compare personalized models with simple held-out-session baselines before enabling emotional claims.

## Official references reviewed

- [Cortex connection and TLS](https://emotiv.gitbook.io/cortex-api/connecting-to-the-cortex-api)
- [Official Python example](https://github.com/Emotiv/cortex-example/blob/master/python/cortex.py)
- [Consumer versus Professional access](https://emotiv.gitbook.io/cortex-api)
- [Authorization and license selection](https://emotiv.gitbook.io/cortex-api/authentication/authorize)
- [License summary](https://emotiv.gitbook.io/cortex-api/authentication/getlicenseinfo)
- [Headset confirmation and settings](https://emotiv.gitbook.io/cortex-api/headset/headset-object)
- [Subscriptions and partial failures](https://emotiv.gitbook.io/cortex-api/data-subscription/subscribe)
- [Sample columns and MN8 metrics](https://emotiv.gitbook.io/cortex-api/data-subscription/data-sample-object)
- [Asynchronous warnings](https://emotiv.gitbook.io/cortex-api/warning-objects)
- [Error codes](https://emotiv.gitbook.io/cortex-api/error-codes)

The official overview and older subscription page differ in their general wording about paid raw EEG. This app relies on the returned scopes, activation result and stream subscription response rather than promising access based on documentation alone.
