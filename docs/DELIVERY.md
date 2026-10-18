# NeuralSignalStudio v0.1 — delivery record

Verified on Windows, October 17, 2026. The workspace began empty and is now an initialized Git repository. No existing project files were replaced. Changes are present locally and have not been committed or published.

## VERIFIED

- The production React/TypeScript frontend builds successfully with Vite and is served by FastAPI at **http://localhost:8080**. Backend binds to `127.0.0.1`; `/api/health` returns `ok: true`, `cloud_upload: false`.
- EMOTIV Launcher is installed at `C:\Program Files\EmotivApps`. The Cortex and Cloud Sync Windows services were running during inspection. NeuralSignalStudio does not use Cloud Sync or Cortex cloud recording.
- Cortex **4.13.5.3**, build **7c7e51d**, replied to `getCortexInfo` at **wss://localhost:6868** with certificate and hostname verification enabled.
- `getUserLogin` returned a logged-in account. The final diagnostic additionally checks that the logged-in OS account matches the current OS account. Email verification is not exposed by this API and is not claimed.
- `queryHeadsets` returned an empty array during the local audit and final startup scan. No MN8 discovery or connection was verified in this implementation session.
- LSL discovery executed successfully and returned **zero streams** during the two-second scans. No currently usable LSL EEG publisher was verified.
- **27 automated tests passed**. The test suite emitted one upstream Starlette/httpx test-client deprecation warning; no test failed.
- Production build passed; the npm dependency audit reported **zero vulnerabilities** at installation time.
- Browser testing verified explicit demo selection, 128 Hz received data, consent-gated recording, saving a marker, reopening the **1,342-sample synthetic validation session**, offline spectral analysis, and a clearly labeled replay with recording disabled.
- A 60.12-second synthetic acquisition/recording/display check reopened **7,689 samples** with **exact original values**, **128.0 Hz** observed rate, **zero discontinuities**, **547 display frames**, **10.0 Hz peaks in both channels**, and no recording error. This is a development-duration synthetic check, not an hours-long hardware soak test.

Local evidence: `artifacts/local-audit.json`, `artifacts/soak-result.json`, the synthetic validation session in `data/studio.sqlite3`, and the screenshot in `artifacts/dashboard.png`. Local artifacts, databases, dependencies and runtime logs are excluded from Git.

## IMPLEMENTED BUT NOT HARDWARE-TESTED

- Correlated asynchronous JSON-RPC Cortex transport; exact error codes, operation names, sanitized messages and legitimate recovery guidance; bounded diagnostic history and redacted report export.
- Secure credential setup in Windows Credential Manager, with a replacement-secret acknowledgment and hidden terminal input. Environment-variable fallback remains backend-only.
- Launcher approval and authorization flow, default automatic license selection, controlled optional developer-license selection, license scope/expiry/quota/device-limit summary.
- Headset refresh/query; connection confirmation through returned `connected` status before session creation; active EEG session and optional explicit one-session debit; individual subscription success/failure inspection and channel mapping from `cols`.
- Asynchronous disconnect handling; a failed hardware transport cannot prevent using demo or offline recordings. Diagnostics and source transitions are serialized, and neither automatically activates paid sessions in a retry loop.
- Cortex raw metadata preservation and separate auxiliary-stream events. Only MN8 `attention` and `cognitiveStress` with active flags and fresh valid values are displayed.
- LSL regularly sampled EEG discovery and inlet; original timestamps, original units, XML and time correction; publisher identity disclosure; one active source at a time.

Hardware behavior has been tested using fake responses and deterministic fixtures, not a connected MN8. The app registration's Professional EEG option cannot be confirmed from the local unauthenticated probe; the owner must review the developer portal.

## SIMULATED — FUNCTIONING NOW

- A deterministic 128 Hz, two-channel software source labeled `SIM-L` / `SIM-R`, with no hardware origin and no synthetic Cortex metrics.
- Scrolling uPlot waveforms; raw/filtered view; time and amplitude controls; pause, cursor and drag zoom; visible discontinuity/interpolation breaks; stream and sample statistics.
- Raw-signal Welch PSD, relative integrated frequency bands, rolling first-channel spectrogram, independent display filtering and notch controls.
- Consent-gated recording, pseudonymous participant IDs, titles, notes, markers, task context and self-reports; background bounded-queue persistence; periodic SQLite WAL commits; recovery of interrupted sessions.
- Searchable library, paged read-only replay, speed selection, offline region analysis and selected-region CSV+metadata+events ZIP export. Exact original values, mapping and timestamps survive recording/export tests.
- Reactive aura and simple feature avatar with smooth visual scaling, sensitivity, intensity and a session baseline. Real-source animation suspends for unknown/stale/poor quality. This is a transparent amplitude mapping, not emotion detection.
- Six workspaces: Live Monitor, Neural State, Recordings, Analysis, Experiments, and Connection & Diagnostics. Responsive layout, keyboard-accessible controls, modal focus handling and reduced-motion support.

## BLOCKED / NOT VERIFIED

| Required fact | Actual state |
|---|---|
| Developer app authorized? | **No authorization verified. Replacement credentials were not supplied.** |
| License permissions verified? | **None.** No scopes, expiry, activation limit, registered-device count or session quota have been obtained for this application. |
| MN8 connected? | **No.** No device was returned in the audit query. |
| Real EEG received? | **No. Zero genuine EEG samples.** Real channel mapping, sample rate and real recording duration remain unknown. |
| Real streams confirmed available? | **None.** No Cortex subscriptions were attempted and no LSL streams were found. |
| Device-limit restriction reproduced? | **No.** The prior account restriction is user-provided context. `-32022` is implemented and tested with mocks; no credential-backed activation was attempted. |

The app remains launchable with these blockers. Synthetic data is never silently substituted for hardware input, and no arbitrary emotion or diagnostic output is displayed.

## Exact startup and recovery path

The app was left running locally on port 8080, without an active recording. Open **http://localhost:8080**. For subsequent starts:

```powershell
cd C:\myProjects\neuro
.\scripts\start.ps1
```

If dependencies need to be re-created, run `.\scripts\setup.ps1` first. The setup script selects the available bundled Python 3.12.14 runtime or `py -3.12`; the default system Python 3.15 is not used for this build. Full instructions and direct commands are in `README.md`.

Before real acquisition:

1. Revoke the exposed client secret and generate its replacement in the EMOTIV developer portal. Review the Professional EEG registration option for MN8.
2. Enter replacement credentials **only in the local terminal**:

   ```powershell
   .\.venv\Scripts\python.exe -m backend.security
   ```

3. Sign into EMOTIV Launcher, run diagnostics, approve NeuralSignalStudio in Launcher and rerun diagnostics. Inspect the actual returned license information.
4. Turn on and scan for the MN8. Authorize acquisition explicitly, then connect. Activate EEG only when scopes/quota permit it. Recording requires separate participant consent.
5. If `-32022` occurs, obtain an activation transfer or entitlement change from EMOTIV support. If `-32232` occurs, correct the app registration/entitlement. Do not repeatedly retry quota-consuming operations.
6. If an independently authorized LSL publisher becomes available, discover it and verify its provenance before selecting it. Never assume LSL bypasses entitlement restrictions.

## Prioritized next milestones

1. **Hardware gate:** obtain replacement credentials/approval, verify license permissions, confirm the physical MN8 and document an actual received-data run (channel mapping, observed rate, sample count and duration).
2. **Reliability gate:** extended real-source recording, disconnect/reconnect and LSL clock tests; library and detail pagination, replay seeking, motion and contact-quality views.
3. **Export/desktop/overlay:** XDF and EDF+ where appropriate, Tauri 2 packaging, and an explicitly opt-in OBS browser-source route. These are planned, not shipped.
4. **Personalization:** collect task annotations and self-reports across sessions; validate against held-out sessions and simple baselines before enabling any categorical personal-state model.

No cloud sharing, model training, medical inference, or validated emotion classification is implemented. The existing quadrant description is explicitly a heuristic from two available Cortex metrics and has no confidence score.
