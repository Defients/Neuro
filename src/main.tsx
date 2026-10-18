import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  AudioLines,
  Radio,
  Brain,
  FolderOpen,
  ChartNoAxesCombined,
  FlaskConical,
  PlugZap,
  CircleHelp,
  Settings2,
  ChevronDown,
  ArrowUpRight,
  Play,
  Pause,
  Square,
  Circle,
  Plus,
  Download,
  Search,
  ShieldCheck,
  Check,
  X,
  Terminal,
  RefreshCw,
  Waves,
  Zap,
  Clock3,
  Bookmark,
  SlidersHorizontal,
  Maximize2,
  ArrowRight,
  Fingerprint,
  Database,
  Headphones,
  AlertTriangle,
  RotateCcw,
} from "lucide-react";
import type {
  State,
  Session,
  Diagnostic,
  Lsl,
  Features,
  Annotation,
} from "./types";
import { CortexStreams } from "./components/CortexStreams";
import { api } from "./api";
import { Badge, Panel } from "./components/UI";
import {
  WavePlot,
  Spectrum,
  Bands,
  Spectrogram,
  Aura,
} from "./components/SignalViews";
import "./styles.css";

const empty: State = {
  source: null,
  arriving: false,
  total_samples: 0,
  observed_rate: null,
  discontinuities: 0,
  interpolated: 0,
  last_sample_age: null,
  duration: 0,
  error: null,
  quality: null,
  battery: null,
  metrics: null,
  features: { available: false },
  recording: {
    active: false,
    id: null,
    error: null,
    persisted_samples: 0,
    started: null,
  },
  annotations: [],
};
const sections = [
  ["Live Monitor", Activity],
  ["Neural State", Brain],
  ["Recordings", FolderOpen],
  ["Analysis", ChartNoAxesCombined],
  ["Experiments", FlaskConical],
  ["Connection & Diagnostics", PlugZap],
] as const;
const duration = (n: number) =>
  `${Math.floor(n / 3600)
    .toString()
    .padStart(2, "0")}:${Math.floor((n / 60) % 60)
    .toString()
    .padStart(2, "0")}:${Math.floor(n % 60)
    .toString()
    .padStart(2, "0")}`;
const number = (n: number | null | undefined, digits = 1) =>
  n == null ? "—" : n.toFixed(digits);
function App() {
  const [page, setPage] = useState("Live Monitor"),
    [view, setView] = useState("Overview"),
    [state, setState] = useState<State>(empty),
    [online, setOnline] = useState(false),
    [windowSize, setWindow] = useState(10),
    [scale, setScale] = useState(50),
    [filtered, setFiltered] = useState(false),
    [notch, setNotch] = useState(0),
    [paused, setPaused] = useState(false);
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(""),
    [modal, setModal] = useState(false),
    [title, setTitle] = useState("Exploration session"),
    [participant, setParticipant] = useState("participant-01"),
    [consent, setConsent] = useState(false),
    [marker, setMarker] = useState(""),
    [sessions, setSessions] = useState<Session[]>([]),
    [search, setSearch] = useState("");
  const [diag, setDiag] = useState<Diagnostic | null>(null),
    [lsl, setLsl] = useState<Lsl>({ checked: false, streams: [] }),
    [configured, setConfigured] = useState(false),
    [optionalLicense, setOptionalLicense] = useState(false),
    [authConsent, setAuthConsent] = useState(false),
    [activate, setActivate] = useState(false),
    [debit, setDebit] = useState(false),
    [useLicense, setUseLicense] = useState(false),
    [selectedHeadset, setHeadset] = useState("");
  const [selectedSession, setSelectedSession] = useState(""),
    [analysis, setAnalysis] = useState<{
      analysis: Features;
      samples: number;
      region: number[];
    } | null>(null),
    [regionStart, setRegionStart] = useState(0),
    [regionEnd, setRegionEnd] = useState(30),
    [speed, setSpeed] = useState(1),
    [events, setEvents] = useState<Annotation[]>([]);
  const [sensitivity, setSensitivity] = useState(1),
    [intensity, setIntensity] = useState(0.7),
    [visual, setVisual] = useState("aura"),
    [baseline, setBaseline] = useState(0),
    [task, setTask] = useState("Quiet resting baseline"),
    [note, setNote] = useState(""),
    [ratings, setRatings] = useState<Record<string, number>>({
      valence: 5,
      arousal: 5,
      stress: 5,
      focus: 5,
      confidence: 5,
    });
  const action = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Operation failed");
    } finally {
      setBusy("");
    }
  };
  useEffect(() => {
    let ws: WebSocket;
    let timer: ReturnType<typeof setTimeout>;
    let disposed = false;
    const connect = () => {
      ws = new WebSocket(
        `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/monitor?seconds=${windowSize}&filtered=${+filtered}&notch=${notch}`,
      );
      ws.onopen = () => setOnline(true);
      ws.onmessage = (e) => setState(JSON.parse(e.data));
      ws.onclose = () => {
        setOnline(false);
        if (!disposed) timer = setTimeout(connect, 2000);
      };
    };
    connect();
    return () => {
      disposed = true;
      clearTimeout(timer);
      ws.close();
    };
  }, [windowSize, filtered, notch]);
  useEffect(() => {
    api<{ configured: boolean; optional_license: boolean }>("/config")
      .then((c) => {
        setConfigured(c.configured);
        setOptionalLicense(c.optional_license);
      })
      .catch(() => {});
    const refreshDiscovery = () => {
      api<Diagnostic>("/diagnostics")
        .then(setDiag)
        .catch(() => {});
      api<Lsl>("/lsl")
        .then(setLsl)
        .catch(() => {});
    };
    refreshDiscovery();
    const discoveryTimer = setInterval(refreshDiscovery, 5000);
    return () => clearInterval(discoveryTimer);
  }, []);
  useEffect(() => {
    if (!modal) return;
    const previous = document.activeElement as HTMLElement | null;
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setModal(false);
        return;
      }
      if (event.key !== "Tab") return;
      const elements = Array.from(
        document.querySelectorAll<HTMLElement>(
          ".modal button:not(:disabled), .modal input, .modal select, .modal textarea",
        ),
      );
      const first = elements[0],
        last = elements[elements.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        last?.focus();
        event.preventDefault();
      } else if (!event.shiftKey && document.activeElement === last) {
        first?.focus();
        event.preventDefault();
      }
    };
    document.addEventListener("keydown", handler);
    return () => {
      document.removeEventListener("keydown", handler);
      previous?.focus();
    };
  }, [modal]);
  const loadSessions = () =>
    api<Session[]>("/sessions?q=" + encodeURIComponent(search)).then((s) => {
      setSessions(s);
      if (!selectedSession && s[0]) setSelectedSession(s[0].id);
    });
  useEffect(() => {
    if (["Recordings", "Analysis"].includes(page))
      loadSessions().catch(() => {});
  }, [page, search]);
  const selectSource = (kind: string, extra = {}) =>
    action("Switching source", () => api("/source", { kind, ...extra }));
  const actualLive =
    online &&
    state.arriving &&
    !!state.source &&
    state.source.kind !== "replay" &&
    !state.source.simulated;
  const sourceLabel =
    state.source?.kind === "replay"
      ? "REPLAY"
      : state.source?.simulated
        ? "SYNTHETIC DEMO"
        : actualLive
          ? "SOURCE STREAMING"
          : state.source?.kind === "cortex"
            ? online && state.receiving_samples
              ? "RECEIVING SAMPLES"
              : state.cortex_subscribed?.length
                ? "SUBSCRIBED · AWAITING SAMPLES"
                : "CONNECTED · NO ACTIVE SUBSCRIPTIONS"
            : "NO EEG SIGNAL";
  const canRecord =
    online &&
    state.arriving &&
    !!state.source?.channels.length &&
    state.source.kind !== "replay";
  const addMarker = () =>
    action("Adding marker", async () => {
      await api("/markers", { label: marker || "Manual marker" });
      setMarker("");
    });
  const replay = (sid: string) =>
    action("Opening replay", async () => {
      await api("/source", { kind: "replay", uid: sid, speed });
      setPage("Live Monitor");
    });
  const heading: Record<string, string> = {
    "Live Monitor": "A clearer view of your signal.",
    "Neural State": "From signal to expression.",
    Recordings: "Every session, preserved.",
    Analysis: "Look closer. Find the pattern.",
    Experiments: "Start with what you report.",
    "Connection & Diagnostics": "Know exactly where you stand.",
  };
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon">
            <AudioLines size={23} />
          </div>
          <div>
            NEURAL<span>SIGNALSTUDIO</span>
            <small>
              RESEARCH WORKSPACE <em>V0.1</em>
            </small>
          </div>
        </div>
        <div className="workspace-tag">
          <div className="workspace-avatar">S</div>
          <div>
            Personal workspace<small>Local · private by design</small>
          </div>
          <ShieldCheck size={15} />
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          {sections.map(([name, Icon]) => (
            <button
              key={name}
              aria-label={name}
              title={name}
              onClick={() => setPage(name)}
              className={page === name ? "active" : ""}
            >
              <Icon size={18} />
              <span>{name}</span>
              {name === "Connection & Diagnostics" && (
                <i className="nav-alert" />
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="device-card">
            <div>
              <Headphones size={17} />
              <span>EMOTIV MN8</span>
            </div>
            <b>
              {state.source?.kind === "cortex" && state.arriving
                ? "Cortex source active"
                : "Hardware not verified"}
            </b>
            <small>
              {diag?.availability === "reachable"
                ? "Cortex service reachable"
                : "Run connection diagnostics"}
            </small>
            <button onClick={() => setPage("Connection & Diagnostics")}>
              Manage connection <ArrowUpRight size={13} />
            </button>
          </div>
          <button
            className="sidebar-link"
            onClick={() => {
              setPage("Connection & Diagnostics");
              document.getElementById("local-settings")?.scrollIntoView();
            }}
          >
            <Settings2 size={16} />
            Application settings
          </button>
          <div className="privacy">
            <ShieldCheck size={13} /> EEG stays on this computer
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <span>/</span>
            <b>{page}</b>
          </div>
          <div className="topbar-right">
            {state.recording.active && (
              <button
                className="global-recording"
                aria-label="Stop active local recording"
                title={`${state.recording.persisted_samples.toLocaleString()} samples persisted. Click to stop and save.`}
                disabled={!online || !!busy}
                onClick={() =>
                  action("Saving recording", () => api("/record/stop", {}))
                }
              >
                <Square size={10} /> Recording · stop
              </button>
            )}
            <span className={"backend-dot " + (online ? "ok" : "")} />
            <span>
              {online ? "Local engine online" : "Engine disconnected"}
            </span>
            <span className="topbar-divider" />
            <button
              className="icon-button"
              aria-label="Open help and setup"
              onClick={() => setPage("Connection & Diagnostics")}
            >
              <CircleHelp size={18} />
            </button>
            <div className="profile" title="Local participant workspace">
              S
            </div>
          </div>
        </header>
        <main>
          <div className="page-title">
            <div>
              <div className="eyebrow">
                NEURALSIGNALSTUDIO{" "}
                <span>
                  /{" "}
                  {page === "Live Monitor"
                    ? "SIGNAL ACQUISITION"
                    : "RESEARCH WORKSPACE"}
                </span>
              </div>
              <h1>{page}</h1>
              <p>{heading[page]}</p>
            </div>
            <div className="title-actions">
              {page === "Live Monitor" ? (
                <div className="segmented">
                  {["Overview", "Advanced", "Research"].map((v) => (
                    <button
                      key={v}
                      className={view === v ? "selected" : ""}
                      onClick={() => setView(v)}
                    >
                      {v}
                    </button>
                  ))}
                </div>
              ) : (
                <Badge tone="violet">LOCAL WORKSPACE</Badge>
              )}
            </div>
          </div>
          {error && (
            <div className="error-banner" role="alert">
              <AlertTriangle size={18} />
              <span>{error}</span>
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {diag?.blocker && (
            <div className="notice">
              <AlertTriangle size={16} />
              <span>
                <b>Connection blocked · {diag.blocker.code}</b>
                <br />
                {diag.blocker.explanation} {diag.blocker.action}
              </span>
            </div>
          )}
          {busy && (
            <div className="busy-banner" role="status">
              <RefreshCw size={14} className="spin" />
              {busy}…
            </div>
          )}
          {!online && (
            <div className="notice">
              <AlertTriangle size={16} />
              <span>
                The local engine is disconnected. Data, status and recording
                controls are unavailable until it reconnects.
              </span>
            </div>
          )}
          {(page === "Live Monitor" || page === "Neural State") && (
            <>
              <div
                className={
                  "provenance-banner " +
                  (state.source?.simulated ? "demo-banner" : "")
                }
              >
                <div>
                  <span
                    className={
                      "signal-dot " +
                      (state.arriving && online ? "flowing" : "")
                    }
                  />
                  <b>{sourceLabel}</b>
                  <span>
                    {state.source
                      ? state.source.name
                      : "No acquisition source selected"}
                  </span>
                </div>
                <button onClick={() => setPage("Connection & Diagnostics")}>
                  {state.source?.simulated
                    ? "Simulated signals · no headset data"
                    : "View source provenance"}{" "}
                  <ArrowUpRight size={13} />
                </button>
              </div>
              <div className="source-strip">
                <div className="source-picker">
                  <span className="eyebrow">ACQUISITION SOURCE</span>
                  <select
                    aria-label="Acquisition source"
                    disabled={!!busy}
                    value={
                      state.source?.kind === "synthetic"
                        ? "synthetic"
                        : state.source
                          ? "current"
                          : "none"
                    }
                    onChange={(e) =>
                      e.target.value === "setup"
                        ? setPage("Connection & Diagnostics")
                        : selectSource(e.target.value)
                    }
                  >
                    <option value="none">No source · select to begin</option>
                    <option value="synthetic">Synthetic demo · 128 Hz</option>
                    {state.source && state.source.kind !== "synthetic" && (
                      <option value="current">{state.source.name}</option>
                    )}
                    <option value="setup">Connect Cortex / LSL…</option>
                  </select>
                </div>
                <div className="strip-stat">
                  <span>CHANNELS</span>
                  <b>
                    {state.source?.channels.length || "—"}{" "}
                    <small>
                      {state.source?.channels.join(" / ") || "Not receiving"}
                    </small>
                  </b>
                </div>
                <div className="strip-stat">
                  <span>OBSERVED RATE</span>
                  <b>
                    {online && state.arriving
                      ? number(state.observed_rate)
                      : "—"}{" "}
                    <small>Hz</small>
                  </b>
                </div>
                <div className="strip-stat">
                  <span>SIGNAL QUALITY</span>
                  <b>
                    {state.source?.simulated
                      ? "Simulated"
                      : state.quality !== null
                        ? state.quality + " / 100"
                        : "Unknown"}
                  </b>
                </div>
                <div className="record-controls">
                  <div className="session-timer">
                    <Clock3 size={14} />
                    {duration(
                      state.recording.active && state.recording.started
                        ? Date.now() / 1000 - state.recording.started
                        : state.duration,
                    )}
                  </div>
                  <button
                    className={
                      state.recording.active
                        ? "button recording"
                        : "button primary"
                    }
                    disabled={
                      !online ||
                      !!busy ||
                      (!state.recording.active && !canRecord)
                    }
                    onClick={() =>
                      state.recording.active
                        ? action("Saving recording", () =>
                            api("/record/stop", {}),
                          )
                        : (setConsent(false), setModal(true))
                    }
                  >
                    {state.recording.active ? (
                      <Square size={13} />
                    ) : (
                      <Circle size={13} />
                    )}{" "}
                    {state.recording.active
                      ? "Stop recording"
                      : "Record session"}
                  </button>
                </div>
              </div>
              {state.recording.error && (
                <div className="error-banner" role="alert">
                  {state.recording.error}
                </div>
              )}
            </>
          )}
          {page === "Live Monitor" && (
            <>
              {state.source?.kind === "cortex" && (
                <CortexStreams state={state} online={online} />
              )}
              <div className="monitor-grid">
                <Panel
                  title="EEG waveform"
                  eyebrow="TIME DOMAIN"
                  className="wave-panel"
                  action={
                    <div className="inline-actions">
                      <Badge
                        tone={state.arriving && online ? "cyan" : "neutral"}
                      >
                        {paused
                          ? "DISPLAY PAUSED"
                          : state.arriving && online
                            ? "RECEIVING"
                            : "AWAITING DATA"}
                      </Badge>
                      <button
                        className="icon-button"
                        title="Pause display; acquisition and recording continue"
                        aria-label={paused ? "Resume display" : "Pause display"}
                        onClick={() => setPaused(!paused)}
                      >
                        {paused ? <Play size={16} /> : <Pause size={16} />}
                      </button>
                    </div>
                  }
                >
                  <div className="wave-toolbar">
                    <div className="segmented small">
                      <button
                        className={!filtered ? "selected" : ""}
                        onClick={() => setFiltered(false)}
                      >
                        Raw
                      </button>
                      <button
                        className={filtered ? "selected" : ""}
                        onClick={() => setFiltered(true)}
                      >
                        Filtered
                      </button>
                    </div>
                    <label>
                      Window
                      <select
                        aria-label="Waveform time window"
                        value={windowSize}
                        onChange={(e) => setWindow(+e.target.value)}
                      >
                        {[5, 10, 20, 30].map((n) => (
                          <option key={n} value={n}>
                            {n} s
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Scale
                      <select
                        aria-label="Amplitude scale"
                        value={scale}
                        onChange={(e) => setScale(+e.target.value)}
                      >
                        {[25, 50, 100, 250, 1000].map((n) => (
                          <option key={n} value={n}>
                            ±{n}
                          </option>
                        ))}
                      </select>
                    </label>
                    <button
                      className="text-button push"
                      onClick={() => {
                        setWindow(10);
                        setScale(50);
                        setPaused(false);
                      }}
                    >
                      <RotateCcw size={13} />
                      Reset view
                    </button>
                  </div>
                  <WavePlot
                    state={online ? state : empty}
                    windowSize={windowSize}
                    scale={scale}
                    paused={paused}
                  />
                  <div className="wave-footer">
                    <span>
                      <i className="legend-dot violet" />
                      {state.source?.channels[0] || "Channel 1"}
                      <i className="legend-dot cyan" />
                      {state.source?.channels[1] || "Channel 2"}
                    </span>
                    <span>
                      Median-centered display · drag to zoom · gaps remain
                      visible
                    </span>
                  </div>
                </Panel>
                <Panel
                  title="Stream health"
                  eyebrow="ACQUISITION INTEGRITY"
                  className="health-panel"
                  action={<Radio size={16} className="muted" />}
                >
                  <div className="health-hero">
                    <div
                      className={
                        "health-symbol " +
                        (state.arriving && online ? "good" : "")
                      }
                    >
                      <Waves size={25} />
                    </div>
                    <div>
                      <h2>
                        {online && state.arriving
                          ? "Data arriving"
                          : "Awaiting signal"}
                      </h2>
                      <span>
                        {state.source?.kind === "replay"
                          ? "Original recording · local replay"
                          : state.source?.simulated
                            ? "Deterministic synthetic fixture"
                            : "No verified neurological measurements"}
                      </span>
                    </div>
                  </div>
                  <dl className="health-rows">
                    <div>
                      <dt>Received samples</dt>
                      <dd>
                        {online ? state.total_samples.toLocaleString() : "—"}
                      </dd>
                    </div>
                    <div>
                      <dt>Discontinuities</dt>
                      <dd className={state.discontinuities ? "amber" : ""}>
                        {state.discontinuities}
                      </dd>
                    </div>
                    <div>
                      <dt>Interpolated samples</dt>
                      <dd>{state.interpolated}</dd>
                    </div>
                    <div>
                      <dt>Last arrival</dt>
                      <dd>
                        {online && state.last_sample_age !== null
                          ? number(state.last_sample_age * 1000, 0) + " ms ago"
                          : "—"}
                      </dd>
                    </div>
                    <div>
                      <dt>Nominal rate</dt>
                      <dd>
                        {state.source ? state.source.nominal_rate + " Hz" : "—"}
                      </dd>
                    </div>
                    {state.battery !== null && (
                      <div>
                        <dt>Battery</dt>
                        <dd>{state.battery}%</dd>
                      </div>
                    )}
                    <div>
                      <dt>Recording</dt>
                      <dd>
                        {state.recording.active ? (
                          <span className="red">● Recording locally</span>
                        ) : (
                          "Off · explicit consent required"
                        )}
                      </dd>
                    </div>
                  </dl>
                  <div className="health-note">
                    <ShieldCheck size={15} />
                    <span>
                      Original samples preserved.
                      <br />
                      No automatic cloud uploads.
                    </span>
                  </div>
                </Panel>
                <Panel
                  title="Power spectral density"
                  eyebrow="FREQUENCY DOMAIN"
                  action={<span className="unit">dB re 1 unit²/Hz</span>}
                >
                  <Spectrum
                    features={online ? state.features : { available: false }}
                  />
                  <div className="chart-caption">
                    <span>Welch · 2 s Hann window</span>
                    <span>1–45 Hz · raw signal</span>
                  </div>
                </Panel>
                <Panel
                  title="Frequency bands"
                  eyebrow="OBSERVED SIGNAL FEATURES"
                  action={<ChartNoAxesCombined size={16} className="muted" />}
                >
                  <Bands
                    features={online ? state.features : { available: false }}
                  />
                </Panel>
                <Panel
                  title="Neural aura"
                  eyebrow="EXPRESSIVE SIGNAL MAPPING"
                  className="mini-aura"
                  action={
                    <button
                      className="icon-button"
                      aria-label="Open Neural State"
                      onClick={() => setPage("Neural State")}
                    >
                      <ArrowUpRight size={17} />
                    </button>
                  }
                >
                  <Aura state={online ? state : empty} />
                </Panel>
              </div>
              {view !== "Overview" && (
                <div className="advanced-grid">
                  <Panel
                    title="Rolling spectrogram"
                    eyebrow="FIRST CHANNEL · RAW PSD"
                  >
                    <Spectrogram state={online ? state : empty} />
                  </Panel>
                  <Panel title="Processing controls" eyebrow="DISPLAY ONLY">
                    <label className="field">
                      Notch frequency
                      <select
                        value={notch}
                        onChange={(e) => setNotch(+e.target.value)}
                      >
                        <option value="0">Off</option>
                        <option value="50">50 Hz</option>
                        <option value="60">60 Hz</option>
                      </select>
                    </label>
                    <p className="footnote">
                      Filtered display: 4th order Butterworth, 1–40 Hz, zero
                      phase. Notch applies only in filtered mode. Raw recordings
                      and PSD are unchanged.
                    </p>
                  </Panel>
                </div>
              )}
              <div className="bottom-grid">
                <Panel
                  title="Session timeline"
                  action={<Badge>{state.annotations.length} EVENTS</Badge>}
                >
                  <div className="timeline-events">
                    {state.annotations.length ? (
                      state.annotations.slice(0, 4).map((e, i) => (
                        <div className="timeline-event" key={i}>
                          <Bookmark size={13} />
                          <span>{e.label}</span>
                          <small>
                            {e.kind === "self_report"
                              ? "SELF-REPORT"
                              : e.kind.toUpperCase()}{" "}
                            · {e.persisted ? "SAVED" : "TEMPORARY"}
                          </small>
                        </div>
                      ))
                    ) : (
                      <div className="timeline-empty">
                        <Bookmark size={16} />
                        <span>Your annotations will appear here.</span>
                        <small>Markers align with source timestamps.</small>
                      </div>
                    )}
                  </div>
                  <form
                    className="marker-form"
                    onSubmit={(e) => {
                      e.preventDefault();
                      addMarker();
                    }}
                  >
                    <input
                      aria-label="Marker label"
                      placeholder="Add a note or event marker…"
                      value={marker}
                      onChange={(e) => setMarker(e.target.value)}
                    />
                    <button
                      className="button subtle"
                      disabled={!online || !state.arriving || !!busy}
                    >
                      <Plus size={14} />
                      Add marker
                    </button>
                  </form>
                </Panel>
                <div className="research-note">
                  <div className="research-icon">
                    <Fingerprint size={22} />
                  </div>
                  <div>
                    <span className="eyebrow">A SIGNAL, WITH CONTEXT</span>
                    <h3>Observe first. Interpret carefully.</h3>
                    <p>
                      EEG features describe electrical signals. Cognitive
                      estimates are proprietary. Personal interpretations remain
                      experimental.
                    </p>
                    <button
                      className="text-button"
                      onClick={() => setPage("Neural State")}
                    >
                      Explore Neural State <ArrowRight size={14} />
                    </button>
                  </div>
                </div>
              </div>
              {view === "Research" && (
                <Panel
                  title="Source metadata & reproducibility"
                  eyebrow="RESEARCH"
                >
                  <pre>
                    {JSON.stringify(
                      {
                        source: state.source,
                        buffer_samples: (
                          state as State & { buffer_samples?: number }
                        ).buffer_samples,
                        features: state.features.available
                          ? {
                              samples_used: state.features.samples_used,
                              peak_hz: state.features.peak_hz,
                            }
                          : state.features,
                      },
                      null,
                      2,
                    )}
                  </pre>
                </Panel>
              )}
            </>
          )}
          {page === "Neural State" && (
            <>
              <div className="neural-grid">
                <Panel
                  title="A living expression of signal"
                  eyebrow="LAYER A · OBSERVED FEATURES"
                  action={
                    <div className="segmented small">
                      <button
                        className={visual === "aura" ? "selected" : ""}
                        onClick={() => setVisual("aura")}
                      >
                        Aura
                      </button>
                      <button
                        className={visual === "avatar" ? "selected" : ""}
                        onClick={() => setVisual("avatar")}
                      >
                        Feature avatar
                      </button>
                    </div>
                  }
                >
                  <Aura
                    state={online ? state : empty}
                    sensitivity={sensitivity}
                    intensity={intensity}
                    style={visual}
                    baseline={baseline}
                  />
                  <div className="aura-controls">
                    <label>
                      Sensitivity{" "}
                      <input
                        type="range"
                        min=".2"
                        max="3"
                        step=".1"
                        value={sensitivity}
                        onChange={(e) => setSensitivity(+e.target.value)}
                      />
                    </label>
                    <label>
                      Intensity{" "}
                      <input
                        type="range"
                        min=".1"
                        max="1"
                        step=".05"
                        value={intensity}
                        onChange={(e) => setIntensity(+e.target.value)}
                      />
                    </label>
                    <button
                      className="button subtle"
                      disabled={!state.features.available}
                      onClick={() => setBaseline(state.features.rms?.[0] || 0)}
                    >
                      Set amplitude baseline
                    </button>
                    <button
                      className="icon-button"
                      aria-label="Reset baseline"
                      onClick={() => setBaseline(0)}
                    >
                      <RotateCcw size={15} />
                    </button>
                  </div>
                  <p className="footnote padded">
                    First-channel RMS minus baseline → size and motion. No
                    emotion classification. Hardware visuals pause when signal
                    quality is unknown, stale, or below 50/100.
                  </p>
                </Panel>
                <div className="stack">
                  <Panel
                    title="Cognitive estimates"
                    eyebrow="LAYER B · CORTEX PROPRIETARY"
                  >
                    <div className="metric-tile">
                      <span>Attention</span>
                      <b>
                        {online && state.metrics?.attention != null
                          ? number(state.metrics.attention, 2)
                          : "Unavailable"}
                      </b>
                    </div>
                    <div className="metric-tile">
                      <span>Cognitive strain</span>
                      <b>
                        {online && state.metrics?.cognitiveStress != null
                          ? number(state.metrics.cognitiveStress, 2)
                          : "Unavailable"}
                      </b>
                    </div>
                    <p className="footnote">
                      MN8 attention and cognitiveStress only. Active flags are
                      required; estimates older than 15 seconds are suppressed.
                      Demo EEG does not generate Cortex metrics.
                    </p>
                  </Panel>
                  <Panel
                    title="Personal interpretation"
                    eyebrow="LAYER C · EXPERIMENTAL"
                  >
                    <div className="interpretation">
                      <Brain size={26} />
                      <h3>
                        {online &&
                        state.metrics?.attention != null &&
                        state.metrics.cognitiveStress != null
                          ? `${state.metrics.attention >= 0.5 ? "Focused" : "Lower focus"} / ${state.metrics.cognitiveStress >= 0.5 ? "higher" : "lower"} strain`
                          : "Estimate unavailable"}
                      </h3>
                      <p>
                        Transparent quadrant mapping at 0.5. Descriptive only;
                        no validated mood model exists.
                      </p>
                    </div>
                  </Panel>
                </div>
              </div>
              <div className="notice">
                <FlaskConical size={17} />
                <span>
                  Emotion models require participant labels and evaluation on
                  held-out sessions. Self-reports are stored separately from EEG
                  features.
                </span>
              </div>
              <Panel title="Recent participant timeline">
                <div className="timeline-events">
                  {state.annotations.length ? (
                    state.annotations.map((e, i) => (
                      <div className="timeline-event" key={i}>
                        <Bookmark size={14} />
                        <b>{e.label}</b>
                        <small>
                          {e.kind} ·{" "}
                          {e.ratings
                            ? JSON.stringify(e.ratings)
                            : "manual annotation"}
                        </small>
                      </div>
                    ))
                  ) : (
                    <p className="muted padded">
                      Add self-reports in Experiments to compare signal features
                      with your experience.
                    </p>
                  )}
                </div>
              </Panel>
            </>
          )}
          {page === "Recordings" && (
            <>
              <div className="library-toolbar">
                <div className="search-field">
                  <Search size={16} />
                  <input
                    aria-label="Search recordings"
                    placeholder="Search sessions or participant ID…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </div>
                <div className="inline-actions">
                  <span className="muted">
                    {sessions.length} local sessions
                  </span>
                  <button
                    className="button subtle"
                    onClick={() => action("Refreshing library", loadSessions)}
                  >
                    <RefreshCw size={14} />
                    Refresh
                  </button>
                </div>
              </div>
              <Panel
                title="Session library"
                eyebrow="ORIGINAL SIGNALS · LOCAL STORAGE"
              >
                <div className="session-table">
                  <div className="session-row table-head">
                    <span>SESSION</span>
                    <span>SOURCE</span>
                    <span>SAMPLES</span>
                    <span>STATUS</span>
                    <span>ACTIONS</span>
                  </div>
                  {sessions.map((s) => (
                    <div className="session-row" key={s.id}>
                      <div>
                        <b>{s.title}</b>
                        <small>
                          {new Date(s.started * 1000).toLocaleString()} ·{" "}
                          {s.participant}
                        </small>
                      </div>
                      <div>
                        <Badge tone={s.source.simulated ? "amber" : "cyan"}>
                          {s.source.simulated
                            ? "SYNTHETIC"
                            : s.source.kind.toUpperCase()}
                        </Badge>
                        <small>{s.source.channels.join(" / ")}</small>
                      </div>
                      <span className="mono">
                        {s.sample_count.toLocaleString()}
                      </span>
                      <span>{s.status}</span>
                      <div className="inline-actions">
                        <button
                          title="Replay recording"
                          className="icon-button"
                          disabled={
                            !!busy ||
                            s.status === "recording" ||
                            !s.sample_count
                          }
                          onClick={() => replay(s.id)}
                        >
                          <Play size={16} />
                        </button>
                        <button
                          title="Analyze recording"
                          className="icon-button"
                          onClick={() => {
                            setSelectedSession(s.id);
                            setAnalysis(null);
                            setPage("Analysis");
                          }}
                        >
                          <ChartNoAxesCombined size={16} />
                        </button>
                        <a
                          className="icon-button"
                          title="Export original samples and metadata"
                          href={`/api/sessions/${s.id}/export`}
                        >
                          <Download size={16} />
                        </a>
                      </div>
                    </div>
                  ))}
                  {!sessions.length && (
                    <div className="empty-library">
                      <Database size={32} />
                      <h2>No recordings yet</h2>
                      <p>Select a source, then record your first session.</p>
                      <button
                        className="button primary"
                        onClick={() => setPage("Live Monitor")}
                      >
                        Open Live Monitor <ArrowRight size={15} />
                      </button>
                    </div>
                  )}
                </div>
              </Panel>
              <div className="notice">
                <ShieldCheck size={17} />
                <span>
                  Append-only raw samples · periodic SQLite commits ·
                  interrupted sessions recover on restart. Exports include
                  channel mapping, timestamps, provenance, original metadata and
                  participant annotations.
                </span>
              </div>
            </>
          )}
          {page === "Analysis" && (
            <>
              <Panel title="Open a recorded signal" eyebrow="OFFLINE ANALYSIS">
                <div className="analysis-controls">
                  <label className="field">
                    Session
                    <select
                      value={selectedSession}
                      onChange={(e) => {
                        setSelectedSession(e.target.value);
                        setAnalysis(null);
                        setEvents([]);
                      }}
                    >
                      <option value="">Select a local session</option>
                      {sessions.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.title} {s.source.simulated ? "[SYNTHETIC]" : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    From (seconds)
                    <input
                      type="number"
                      min="0"
                      value={regionStart}
                      onChange={(e) => setRegionStart(+e.target.value)}
                    />
                  </label>
                  <label className="field">
                    To (seconds)
                    <input
                      type="number"
                      min="1"
                      value={regionEnd}
                      onChange={(e) => setRegionEnd(+e.target.value)}
                    />
                  </label>
                  <button
                    className="button primary"
                    disabled={!selectedSession || !!busy}
                    onClick={() =>
                      action("Analyzing region", async () => {
                        setAnalysis(
                          await api(
                            `/sessions/${selectedSession}/analysis?start=${regionStart}&end=${regionEnd}`,
                          ),
                        );
                        const result = await api<{
                          events: Array<{ payload: Annotation }>;
                        }>(`/sessions/${selectedSession}`);
                        setEvents(
                          result.events
                            .filter((e) =>
                              ["self_report", "task", "marker"].includes(
                                e.payload.kind,
                              ),
                            )
                            .map((e) => e.payload),
                        );
                      })
                    }
                  >
                    Analyze region <ArrowRight size={15} />
                  </button>
                  {selectedSession && (
                    <a
                      className="button subtle"
                      href={`/api/sessions/${selectedSession}/export?start=${regionStart}&end=${regionEnd}`}
                    >
                      <Download size={15} />
                      Export region
                    </a>
                  )}
                </div>
                <p className="footnote padded">
                  Up to 120 seconds / 32,768 samples per analysis. Spectral
                  estimates use contiguous, non-interpolated data. Region export
                  preserves original values.
                </p>
              </Panel>
              <div className="advanced-grid">
                <Panel
                  title="Recorded power spectrum"
                  action={analysis && <Badge>{analysis.samples} SAMPLES</Badge>}
                >
                  <Spectrum
                    features={
                      analysis?.analysis || {
                        available: false,
                        reason: "Select a session and analyze a region.",
                      }
                    }
                  />
                </Panel>
                <Panel title="Recorded frequency bands">
                  <Bands
                    features={analysis?.analysis || { available: false }}
                  />
                </Panel>
              </div>
              <Panel title="Replay & participant context">
                <div className="analysis-controls">
                  <label className="field">
                    Replay speed
                    <select
                      value={speed}
                      onChange={(e) => {
                        setSpeed(+e.target.value);
                        if (state.source?.kind === "replay")
                          action("Updating speed", () =>
                            api("/replay/speed", {
                              kind: "replay",
                              speed: +e.target.value,
                            }),
                          );
                      }}
                    >
                      {[0.25, 0.5, 1, 2, 4].map((s) => (
                        <option key={s} value={s}>
                          {s}×
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    className="button subtle"
                    disabled={!selectedSession || !!busy}
                    onClick={() => replay(selectedSession)}
                  >
                    <Play size={15} />
                    Replay in monitor
                  </button>
                </div>
                {events.map((e, i) => (
                  <div className="timeline-event" key={i}>
                    <Bookmark size={14} />
                    <b>{e.label}</b>
                    <small>
                      {e.kind} · {e.ratings ? JSON.stringify(e.ratings) : ""}
                    </small>
                  </div>
                ))}
              </Panel>
            </>
          )}
          {page === "Experiments" && (
            <div className="experiment-grid">
              <Panel
                title="Participant self-report"
                eyebrow="YOUR EXPERIENCE, IN YOUR WORDS"
                action={<Badge tone="violet">SELF-REPORTED</Badge>}
              >
                <form
                  className="report-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    action("Saving self-report", async () => {
                      await api("/markers", {
                        kind: "self_report",
                        label: note || task,
                        task,
                        ratings,
                      });
                      setNote("");
                    });
                  }}
                >
                  <label className="field">
                    Task context
                    <select
                      value={task}
                      onChange={(e) => setTask(e.target.value)}
                    >
                      {[
                        "Quiet resting baseline",
                        "Music listening",
                        "Focused puzzle solving",
                        "Gaming",
                        "Reaction-time challenge",
                        "Personal event",
                      ].map((t) => (
                        <option key={t}>{t}</option>
                      ))}
                    </select>
                  </label>
                  {Object.entries(ratings).map(([key, v]) => (
                    <label className="rating" key={key}>
                      <span>
                        {key === "valence"
                          ? "Mood valence"
                          : key === "confidence"
                            ? "Confidence in this report"
                            : key === "stress"
                              ? "Perceived stress"
                              : key[0].toUpperCase() + key.slice(1)}
                      </span>
                      <input
                        type="range"
                        min="0"
                        max="10"
                        step="1"
                        value={v}
                        onChange={(e) =>
                          setRatings({ ...ratings, [key]: +e.target.value })
                        }
                      />
                      <b>{v}/10</b>
                    </label>
                  ))}
                  <label className="field">
                    Optional note
                    <textarea
                      maxLength={500}
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      placeholder="What did you notice?"
                    />
                  </label>
                  <div className="notice compact">
                    <Bookmark size={16} />
                    <span>
                      {state.recording.active
                        ? "Self-reports will be saved with the current session."
                        : "Reports are temporary until you explicitly start recording."}
                    </span>
                  </div>
                  <button
                    className="button primary"
                    disabled={!online || !state.arriving || !!busy}
                  >
                    <Plus size={15} />
                    Add self-report to timeline
                  </button>
                </form>
              </Panel>
              <div className="stack">
                <Panel
                  title="A thoughtful starting point"
                  eyebrow="CALIBRATION GROUNDWORK"
                >
                  <ol className="steps">
                    <li>
                      <b>Establish context</b>
                      <p>
                        Choose a participant ID and a task. A task does not
                        guarantee a particular emotion.
                      </p>
                    </li>
                    <li>
                      <b>Record with consent</b>
                      <p>
                        Capture raw signal and timed annotations. Keep
                        participant reports separate from measured features.
                      </p>
                    </li>
                    <li>
                      <b>Compare across sessions</b>
                      <p>
                        Future models must beat simple baselines on held-out
                        sessions before categorical claims are shown.
                      </p>
                    </li>
                  </ol>
                </Panel>
                <div className="research-note">
                  <FlaskConical size={25} />
                  <div>
                    <h3>Model training is planned.</h3>
                    <p>
                      This version collects labels and task context. It does not
                      train or validate an emotion classifier.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}
          {page === "Connection & Diagnostics" && (
            <>
              <div className="diagnostic-grid">
                <Panel
                  title="Cortex connection"
                  eyebrow="P0 · LOCAL HARDWARE DIAGNOSTIC"
                  action={
                    <Badge
                      tone={
                        diag?.availability === "reachable" ? "cyan" : "amber"
                      }
                    >
                      {diag?.availability || "NOT CHECKED"}
                    </Badge>
                  }
                >
                  <div className="endpoint">
                    <Terminal size={18} />
                    <code>wss://localhost:6868</code>
                    <ShieldCheck size={16} />
                  </div>
                  <div className="cortex-summary">
                    <span>
                      Cortex{" "}
                      <b>{String(diag?.version?.version || "Unverified")}</b>
                    </span>
                    <span>
                      Account{" "}
                      <b>
                        {diag?.account?.logged_in ? "Signed in" : "Unverified"}
                      </b>
                    </span>
                  </div>
                  <div className="diagnostic-steps">
                    {[
                      [
                        "Secure Cortex socket",
                        diag?.availability === "reachable",
                      ],
                      ["Application credentials", configured],
                      ["Launcher approval", diag?.approval === "approved"],
                      ["Application authorized", diag?.authorized],
                      ["License information", !!diag?.license],
                      [
                        "Connected headset",
                        diag?.headsets.some((h) => h.status === "connected"),
                      ],
                      [
                        "EEG samples received",
                        actualLive && state.source?.kind === "cortex",
                      ],
                    ].map(([text, done], i) => (
                      <div key={i}>
                        <span className={"step-number " + (done ? "done" : "")}>
                          {done ? (
                            <Check size={13} />
                          ) : (
                            String(i + 1).padStart(2, "0")
                          )}
                        </span>
                        <b>{text}</b>
                        <small>{done ? "VERIFIED" : "UNVERIFIED"}</small>
                      </div>
                    ))}
                  </div>
                  <div className="diagnostic-action">
                    <button
                      className="button primary"
                      disabled={!!busy}
                      onClick={() =>
                        action("Inspecting Cortex", async () => {
                          setDiag(
                            await api("/diagnostics", {
                              use_license: useLicense,
                            }),
                          );
                          const c = await api<{ configured: boolean }>(
                            "/config",
                          );
                          setConfigured(c.configured);
                        })
                      }
                    >
                      <RefreshCw size={15} />
                      Run diagnostics
                    </button>
                    <a href="/api/diagnostics/export" className="button subtle">
                      <Download size={15} />
                      Redacted report
                    </a>
                  </div>
                  <div className="notice compact">
                    <ArrowRight size={16} />
                    <span>
                      {diag?.next_action ||
                        "Run diagnostics. No session is activated and no quota is debited."}
                    </span>
                  </div>
                </Panel>
                <div className="stack">
                  <Panel
                    title="Secure local configuration"
                    eyebrow="CREDENTIALS STAY IN THE BACKEND"
                    action={<ShieldCheck size={18} className="cyan-text" />}
                  >
                    <div className="config-status">
                      <Fingerprint size={23} />
                      <div>
                        <b>
                          {configured
                            ? "Credentials configured locally"
                            : "Replacement credentials needed"}
                        </b>
                        <small>Windows Credential Manager</small>
                      </div>
                    </div>
                    <p className="body-copy">
                      Revoke the previously exposed secret in your EMOTIV
                      developer account. Configure the matching app ID and
                      replacement secret in a local terminal:
                    </p>
                    <code className="command">
                      .\.venv\Scripts\python.exe -m backend.security
                    </code>
                    <p className="footnote">
                      Input is hidden. No credentials are entered here or sent
                      to frontend JavaScript.
                    </p>
                    <p className="body-copy">
                      For MN8, check whether “Enable EEG for Professional
                      devices” was unnecessarily enabled in the developer app
                      registration.
                    </p>
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        disabled={!optionalLicense}
                        checked={useLicense}
                        onChange={(e) => setUseLicense(e.target.checked)}
                      />
                      Use locally configured developer license (manual
                      alternative)
                    </label>
                    <p className="footnote">
                      Automatic selection is the default. Use an explicit
                      license only to resolve a documented entitlement mismatch.
                    </p>
                  </Panel>
                  <Panel
                    title="License summary"
                    eyebrow="ONLY RETURNED ENTITLEMENTS"
                  >
                    {diag?.license ? (
                      <pre>{JSON.stringify(diag.license, null, 2)}</pre>
                    ) : (
                      <div className="muted padded">
                        No license permissions verified. Authorization is
                        required before Cortex will disclose this information.
                      </div>
                    )}
                  </Panel>
                </div>
              </div>
              <div className="advanced-grid">
                <Panel
                  title="Discovered headsets"
                  eyebrow="DISCOVERY ≠ CONNECTION"
                  action={<Headphones size={17} />}
                >
                  {diag?.headsets.length ? (
                    <>
                      <label className="field padded">
                        Select headset
                        <select
                          value={selectedHeadset || diag.headsets[0].id}
                          onChange={(e) => setHeadset(e.target.value)}
                        >
                          {diag.headsets.map((h) => (
                            <option key={h.id} value={h.id}>
                              {h.customName || h.id} · {h.status}
                            </option>
                          ))}
                        </select>
                      </label>
                      <div className="connection-options">
                        <label className="checkbox">
                          <input
                            type="checkbox"
                            checked={authConsent}
                            onChange={(e) => setAuthConsent(e.target.checked)}
                          />
                          Participant authorizes local acquisition of this
                          source
                        </label>
                        <label className="checkbox">
                          <input
                            type="checkbox"
                            checked={activate}
                            onChange={(e) => setActivate(e.target.checked)}
                          />
                          Activate an EEG session (requires verified EEG scope
                          and quota)
                        </label>
                        <label className="checkbox">
                          <input
                            type="checkbox"
                            checked={debit}
                            disabled={!activate}
                            onChange={(e) => setDebit(e.target.checked)}
                          />
                          Explicitly allocate one license session; no automatic
                          retries
                        </label>
                        <button
                          className="button primary"
                          disabled={!!busy || !authConsent || !diag.authorized}
                          onClick={() =>
                            action("Connecting headset", async () => {
                              try {
                                await api("/source", {
                                  kind: "cortex",
                                  headset:
                                    selectedHeadset || diag.headsets[0].id,
                                  activate,
                                  debit_one: debit,
                                  authorized: authConsent,
                                });
                                setPage("Live Monitor");
                              } finally {
                                setDiag(await api("/diagnostics"));
                              }
                            })
                          }
                        >
                          <PlugZap size={15} />
                          Connect selected headset
                        </button>
                      </div>
                    </>
                  ) : (
                    <div className="empty-small">
                      <Headphones size={27} />
                      <b>No verified headset discovery yet</b>
                      <p>
                        Open Launcher, sign in, and run diagnostics. A
                        discovered MN8 still requires an authorized connection.
                      </p>
                    </div>
                  )}
                </Panel>
                <Panel
                  title="Lab Streaming Layer"
                  eyebrow="INDEPENDENT SOURCE DISCOVERY"
                  action={
                    <button
                      className="button subtle"
                      disabled={!!busy}
                      onClick={() =>
                        action("Discovering LSL streams", async () =>
                          setLsl(await api("/lsl/discover", {})),
                        )
                      }
                    >
                      <Search size={14} />
                      Discover
                    </button>
                  }
                >
                  {lsl.error ? (
                    <p className="amber padded">{lsl.error}</p>
                  ) : lsl.streams.length ? (
                    <div className="lsl-list">
                      {lsl.streams.map((s) => (
                        <div key={s.id}>
                          <div>
                            <b>{s.name}</b>
                            <small>
                              {s.type} · {s.channels} channels ·{" "}
                              {s.nominal_rate} Hz
                            </small>
                          </div>
                          <button
                            className="button subtle"
                            disabled={
                              !!busy || !s.eeg_candidate || !authConsent
                            }
                            onClick={() =>
                              selectSource("lsl", {
                                uid: s.id,
                                authorized: authConsent,
                              })
                            }
                          >
                            Use source
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="empty-small">
                      <Radio size={27} />
                      <b>
                        {lsl.checked
                          ? "No LSL streams found"
                          : "LSL has not been checked"}
                      </b>
                      <p>
                        Discovery does not create a stream or unlock EEG access.
                        Start an authorized publisher, then discover again.
                      </p>
                    </div>
                  )}
                  <label className="checkbox padded">
                    <input
                      type="checkbox"
                      checked={authConsent}
                      onChange={(e) => setAuthConsent(e.target.checked)}
                    />
                    Participant authorizes local acquisition
                  </label>
                  <p className="footnote padded">
                    One source at a time prevents concurrent duplicates. Check
                    publisher identity; an LSL stream may describe the same MN8
                    as Cortex.
                  </p>
                </Panel>
              </div>
              <Panel
                title="Diagnostic console"
                eyebrow="TIMESTAMPED · SANITIZED"
                action={<Badge>{diag?.events.length || 0} EVENTS</Badge>}
              >
                <div className="console">
                  {diag?.events.length ? (
                    diag.events
                      .slice()
                      .reverse()
                      .map((e, i) => (
                        <div
                          className={
                            "console-row " +
                            (e.outcome === "error" ? "console-error" : "")
                          }
                          key={i}
                        >
                          <time>
                            {new Date(e.timestamp * 1000).toLocaleTimeString()}
                          </time>
                          <b>{e.operation}</b>
                          <span>{e.outcome.toUpperCase()}</span>
                          {e.detail != null && (
                            <pre>
                              {typeof e.detail === "string"
                                ? e.detail
                                : JSON.stringify(e.detail, null, 2)}
                            </pre>
                          )}
                        </div>
                      ))
                  ) : (
                    <p>
                      No diagnostic calls yet. Run diagnostics to inspect the
                      local service.
                    </p>
                  )}
                </div>
              </Panel>
              <Panel
                title="Local settings & current scope"
                eyebrow="PRIVACY BY DESIGN"
                className="settings-panel"
              >
                <div id="local-settings" className="settings-grid">
                  <div>
                    <h4>Data location</h4>
                    <p>data/studio.sqlite3</p>
                    <small>
                      Local SQLite WAL database. No cloud sync or broadcast
                      route enabled.
                    </small>
                  </div>
                  <div>
                    <h4>Demo source</h4>
                    <p>Deterministic two-channel fixture</p>
                    <button
                      className="text-button"
                      onClick={() => selectSource("synthetic")}
                    >
                      Start synthetic demo <ArrowRight size={14} />
                    </button>
                  </div>
                  <div>
                    <h4>Planned capabilities</h4>
                    <p>
                      Tauri packaging · XDF / EDF+ · opt-in OBS overlay ·
                      validated personalized models
                    </p>
                  </div>
                </div>
              </Panel>
            </>
          )}
          {state.source && (
            <div className="source-stop">
              <span className="muted">
                {state.source.kind === "replay"
                  ? "Replay"
                  : state.source.simulated
                    ? "Synthetic source"
                    : "Acquisition source"}
                : {state.source.name}
              </span>
              <button
                className="text-button"
                disabled={!!busy}
                onClick={() => selectSource("none")}
              >
                <Square size={12} />
                Stop source {state.recording.active ? "and save recording" : ""}
              </button>
            </div>
          )}
          <footer>
            <span>
              <AudioLines size={13} /> NEURALSIGNALSTUDIO <small>V0.1</small>
            </span>
            <span>
              Research & personal exploration · Not a medical diagnostic system
            </span>
            <span>
              <ShieldCheck size={12} /> LOCAL FIRST
            </span>
          </footer>
        </main>
      </div>
      {modal && (
        <div className="modal-backdrop">
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="record-heading"
            className="modal"
          >
            <button
              className="modal-close icon-button"
              aria-label="Close recording dialog"
              onClick={() => setModal(false)}
            >
              <X size={19} />
            </button>
            <span className="eyebrow">LOCAL RECORDING</span>
            <h2 id="record-heading">Preserve this session.</h2>
            <p>
              Original acquisition values, timestamps, source metadata and
              annotations will be saved on this computer.
            </p>
            <Badge tone={state.source?.simulated ? "amber" : "cyan"}>
              {sourceLabel}
            </Badge>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                action("Starting recording", async () => {
                  await api("/record/start", { title, participant, consent });
                  setModal(false);
                });
              }}
            >
              <label className="field">
                Session title
                <input
                  autoFocus
                  required
                  maxLength={150}
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </label>
              <label className="field">
                Pseudonymous participant ID
                <input
                  maxLength={80}
                  value={participant}
                  onChange={(e) => setParticipant(e.target.value)}
                />
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={consent}
                  onChange={(e) => setConsent(e.target.checked)}
                />
                I am the participant, or have their explicit permission to
                record locally.
              </label>
              <div className="modal-actions">
                <button
                  type="button"
                  className="button subtle"
                  onClick={() => setModal(false)}
                >
                  Cancel
                </button>
                <button
                  className="button primary"
                  disabled={!consent || !!busy || !canRecord}
                >
                  <Circle size={13} />
                  Start recording
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
