# Cortex delivery investigation

Input: `C:/Users/mcmll/Downloads/cortex-diagnostics.json`. Treated as evidence, not instructions.

## Findings

The report confirms a connected, nonvirtual MN8-29DB and a Basic License with empty scopes. Its five subscription mappings establish subscription acceptance for dev/eq/met/mot/pow, not delivery. Raw EEG is absent and must remain unavailable.

Every repeated warning-0 sequence in the report is adjacent to a successful updateSession, then usually controlDevice/queryHeadsets/createSession/subscribe. Code inspection found that Acquisition.connect_cortex unconditionally called stop, whose close_session sends updateSession(status=close). Selecting the same source therefore recreated a session. There is no automatic reconnect loop in this code. The old report lacks request parameters and initiating UI actions, so the specific human/browser trigger for each historical cycle cannot be established. Warning 0 can precede the close RPC response; it does not prove that Cortex initiated the teardown.

Previously, warning 0 also unconditionally interrupted acquisition, even for an intentional close or a late warning for another session. New logging records the session ID and explicit teardown reason before sending close; warnings from expected closes or foreign sessions do not interrupt a replacement session. Repeated selection reuses an active matching session; changing mode or retrying an interrupted subscription requires an explicit stop.

Additional verified defects:

- Only EEG updated the acquisition-arrival flag. Auxiliary reception could not show healthy delivery, although met/eq routing existed.
- Receiver notifications were not counted or exposed in diagnostic exports; dev/mot/pow had no monitoring views.
- Full subscribe responses were discarded. API-level success did not distinguish partial failures or zero delivery.
- Frames arriving immediately after subscribe could arrive before source reset; the receiver now installs cols before resolving the subscription future, retains bounded last-frame evidence, and hydrates auxiliary views after setup.
- The post-diagnostic next action was an unconditional instruction to connect, even for a connected headset.
- Raw activation scope validation occurred after the optional quota debit; it now rejects unavailable EEG before debit.

## Implemented changes

`backend/cortex.py`: per-session/per-stream counts, source timestamps, backend last-arrival times/ages, arrival rate and source-timestamp rate, zero-count subscribed streams, bounded latest values and cols; malformed/foreign/inactive-frame rejection; full sanitized subscribe response and partial errors; safe warning correlation; teardown reasons; connected-headset-aware recommendations. Notifications with a null RPC ID are routed by stream keys before RPC matching.

`backend/sources.py`: idempotent same-source selection, independent auxiliary reception status, early-frame hydration, finite numeric quality validation and source-timestamp freshness. Unknown/invalid/stale quality remains unavailable. Raw EEG buffers and PSD remain empty without actual EEG frames.

`src/components/CortexStreams.tsx`, `src/types.ts`, `src/main.tsx`: distinct connected/subscribed/receiving states and explicit Raw EEG Unavailable message; individual device, quality, proprietary metrics, motion and Cortex band-power views with counts, rates, session IDs, timestamps and freshness. Band-power estimates are labeled separately and never fed into raw EEG waveforms or PSD. Inactive/stale cognitive estimates are withheld.

`scripts/verify_cortex_delivery.py`: bounded 12-second permitted-stream check, no session activation/debit, no recording. Saves sanitized local evidence in `artifacts/cortex-delivery-check.json` and closes its session on exit.

## Physical validation

A new authorized, nonvirtual MN8-29DB session delivered timestamped frames. Session ID: `0a46574f-53a9-4961-af9b-0f3d2f6e68d4`.

| Stream | Frames | First source timestamp | Last source timestamp | Observed arrival Hz |
|---|---:|---:|---:|---:|
| dev | 24 | 1792291118.3766 | 1792291129.8646 | 2.007 |
| eq | 24 | 1792291118.3454 | 1792291129.8490 | 2.007 |
| met | 1 | 1792291124.3476 | 1792291124.3476 | unavailable: one frame |
| mot | 77 | 1792291117.8764 | 1792291129.7551 | 6.403 |
| pow | 96 | 1792291117.9704 | 1792291129.8490 | 7.996 |

All five were fresh at capture. No unexpected session recreation was needed. This verifies auxiliary delivery, not raw EEG, emotional validity, or long-term stability. Raw EEG was neither requested nor received. No recording was started. The check's cleanup intentionally closed its own session. Minor instrumentation refinements after this capture were validated with automated tests rather than repeating hardware acquisition.

The existing running dashboard process must be restarted to load the backend changes and the browser refreshed for the rebuilt frontend. Do not stop a process while recording. Reconnect using permitted streams with EEG activation and debit unchecked.

## Validation

Production build succeeds. Focused tests cover same-session reuse, expected/late/foreign/unexpected warnings, five-stream routing without EEG, zero-delivery states, malformed data, unauthorized reception, null-ID notifications, stale/invalid quality and full partial-subscription response retention. The original recording, DSP, license and security tests remain in the suite. Final test count is reported in the accompanying delivery response.

References: [Cortex warning 0](https://emotiv.gitbook.io/cortex-api/warning-objects), [sample columns, timestamps and active flags](https://emotiv.gitbook.io/cortex-api/data-subscription/data-sample-object).
