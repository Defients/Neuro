import React, { useEffect, useRef } from "react";
import { Waves } from "lucide-react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import type { State, Features } from "../types";
export function WavePlot({
  state,
  windowSize,
  scale,
  paused,
}: {
  state: State;
  windowSize: number;
  scale: number;
  paused: boolean;
}) {
  const host = useRef<HTMLDivElement>(null),
    plots = useRef<uPlot[]>([]),
    sourceId = state.source?.id;
  const channels = state.source?.channels.slice(0, 8) || ["CH 01", "CH 02"];
  useEffect(() => {
    if (!host.current) return;
    const el = host.current;
    plots.current = channels.map(
      (name, i) =>
        new uPlot(
          {
            width: el.clientWidth,
            height: 116,
            padding: [12, 18, 4, 14],
            cursor: {
              show: true,
              drag: { x: true, y: false },
              points: { show: true },
            },
            legend: { show: false },
            select: { show: true, left: 0, top: 0, width: 0, height: 0 },
            scales: {
              x: { time: false },
              y: { auto: false, range: () => [-scale, scale] },
            },
            axes: [
              {
                show: i === channels.length - 1,
                stroke: "#646b80",
                grid: { stroke: "#1b2030", width: 1 },
                ticks: { show: false },
                font: "10px monospace",
                size: 23,
                values: (_u, vs) => vs.map((v) => v.toFixed(1) + " s"),
              },
              { show: false, grid: { show: true, stroke: "#1b2030" } },
            ],
            series: [
              {},
              {
                label: name,
                stroke: i % 2 === 0 ? "#b7a1ff" : "#60d6db",
                width: 1.3,
                spanGaps: false,
              },
            ],
            hooks: {
              draw: [
                (u) => {
                  const ctx = u.ctx;
                  ctx.save();
                  ctx.strokeStyle = "#202536";
                  ctx.lineWidth = 1;
                  const y = u.valToPos(0, "y", true);
                  ctx.beginPath();
                  ctx.moveTo(u.bbox.left, y);
                  ctx.lineTo(u.bbox.left + u.bbox.width, y);
                  ctx.stroke();
                  ctx.restore();
                },
              ],
            },
          },
          [[], []],
          el,
        ),
    );
    const ro = new ResizeObserver(() =>
      plots.current.forEach((p) =>
        p.setSize({ width: el.clientWidth, height: 116 }),
      ),
    );
    ro.observe(el);
    return () => {
      ro.disconnect();
      plots.current.forEach((p) => p.destroy());
      plots.current = [];
    };
  }, [sourceId, scale, channels.length]);
  useEffect(() => {
    if (paused) return;
    const w = state.waveform;
    if (!w?.timestamps.length) {
      plots.current.forEach((p) => p.setData([[], []]));
      return;
    }
    const start = w.timestamps[w.timestamps.length - 1] - windowSize;
    const gaps = new Set(w.gaps);
    plots.current.forEach((p, c) => {
      const vals = w.values.map((v) => v[c]);
      const sorted = [...vals].sort((a, b) => a - b);
      const center = sorted[Math.floor(sorted.length / 2)] || 0;
      p.setData([
        w.timestamps.map((t) => t - start),
        vals.map((v, i) => (gaps.has(i) ? null : v - center)),
      ] as uPlot.AlignedData);
      p.setScale("x", { min: 0, max: windowSize });
    });
  }, [state, windowSize, paused]);
  return (
    <div className="wave-area">
      <div className="channel-labels">
        {channels.map((c, i) => (
          <div key={c} style={{ top: i * 116 + 16 }}>
            <b style={{ color: i % 2 ? "#60d6db" : "#b7a1ff" }}>{c}</b>
            <span>
              ±{scale} {state.source?.units[i] || "µV"}
            </span>
          </div>
        ))}
      </div>
      <div ref={host} className="wave-plots" />
      {!state.source && (
        <div className="no-signal">
          <Waves size={28} />
          <b>Your signal starts here</b>
          <span>
            Connect an authorized source or explore the synthetic demo.
          </span>
        </div>
      )}
    </div>
  );
}
export function Spectrum({ features }: { features: Features }) {
  const f = features.frequencies || [],
    p = features.psd || [];
  const path = (ch: number) => {
    const db = (p[ch] || []).map((v) => 10 * Math.log10(Math.max(v, 1e-8)));
    return db
      .map(
        (v, i) =>
          `${i ? "L" : "M"}${20 + (f[i] / 45) * 480},${140 - ((Math.max(-30, Math.min(30, v)) + 30) / 60) * 115}`,
      )
      .join(" ");
  };
  return (
    <div className="spectrum">
      <svg
        viewBox="0 0 520 174"
        role="img"
        aria-label="Power spectral density in decibels"
      >
        <defs>
          <linearGradient id="spectralFill" x1="0" y1="0" x2="0" y2="1">
            <stop stopColor="#a88bff" stopOpacity=".22" />
            <stop offset="1" stopColor="#a88bff" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[25, 63, 102, 140].map((y) => (
          <line
            key={y}
            x1="20"
            x2="505"
            y1={y}
            y2={y}
            stroke="#222737"
            strokeDasharray="3 4"
          />
        ))}
        {[0, 10, 20, 30, 40].map((x) => (
          <text
            key={x}
            x={20 + (x / 45) * 480}
            y="165"
            fill="#737c93"
            fontSize="10"
          >
            {x} Hz
          </text>
        ))}
        {p.length > 0 && (
          <>
            <path
              d={path(0) + " L500,140 L20,140 Z"}
              fill="url(#spectralFill)"
            />
            <path d={path(0)} fill="none" stroke="#b49aff" strokeWidth="1.6" />
            {p.length > 1 && (
              <path
                d={path(1)}
                fill="none"
                stroke="#60d6db"
                strokeWidth="1.3"
                opacity=".75"
              />
            )}
          </>
        )}
      </svg>
      {!features.available && (
        <span className="chart-empty">
          {features.reason || "Waiting for signal"}
        </span>
      )}
    </div>
  );
}
export function Bands({ features }: { features: Features }) {
  const ranges = ["1–4 Hz", "4–8 Hz", "8–13 Hz", "13–30 Hz", "30–45 Hz"];
  const names = ["Delta", "Theta", "Alpha", "Beta", "Gamma"];
  const sums = names.map((n) =>
    (features.bands?.[n] || []).reduce((a, b) => a + b, 0),
  );
  const total = sums.reduce((a, b) => a + b, 0);
  return (
    <div className="bands">
      {names.map((name, i) => (
        <div className="band" key={name}>
          <div>
            <span className={"band-dot b" + i} />
            <b>{name}</b>
            <small>{ranges[i]}</small>
          </div>
          <div className="band-track">
            <i
              style={{
                width: `${features.available && total ? (sums[i] / total) * 100 : 0}%`,
              }}
              className={"b" + i}
            />
          </div>
          <span className="mono">
            {features.available && total
              ? Math.round((sums[i] / total) * 100) + "%"
              : "—"}
          </span>
        </div>
      ))}
      <p className="footnote">
        Relative integrated power · all displayed channels · signal features
      </p>
    </div>
  );
}
export function Spectrogram({ state }: { state: State }) {
  const ref = useRef<HTMLCanvasElement>(null),
    last = useRef(0);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || !state.features.available || !state.arriving) return;
    const stamp = Math.floor(Date.now() / 1000);
    if (stamp === last.current) return;
    last.current = stamp;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(canvas, -5, 0);
    const p = state.features.psd?.[0] || [];
    for (let y = 0; y < canvas.height; y++) {
      const i = Math.min(
        p.length - 1,
        Math.floor((1 - y / canvas.height) * p.length),
      );
      const db = 10 * Math.log10(Math.max(p[i] || 0, 1e-8));
      const k = Math.max(0, Math.min(1, (db + 25) / 50));
      ctx.fillStyle = `hsl(${260 - k * 80} ${30 + k * 50}% ${6 + k * 58}%)`;
      ctx.fillRect(canvas.width - 5, y, 5, 1);
    }
  }, [state]);
  useEffect(() => {
    const c = ref.current;
    const x = c?.getContext("2d");
    if (x && c) {
      x.fillStyle = "#0d1019";
      x.fillRect(0, 0, c.width, c.height);
    }
  }, [state.source?.id]);
  return (
    <div className="spectrogram">
      <div className="spec-axis">
        <span>45 Hz</span>
        <span>22</span>
        <span>1 Hz</span>
      </div>
      <canvas
        width="600"
        height="115"
        ref={ref}
        aria-label="Rolling spectrogram of first channel"
      />
      <div className="spec-bottom">
        <span>120 seconds of received spectra</span>
        <span>now</span>
      </div>
    </div>
  );
}
export function Aura({
  state,
  sensitivity = 1,
  intensity = 0.7,
  style = "aura",
  baseline = 0,
}: {
  state: State;
  sensitivity?: number;
  intensity?: number;
  style?: string;
  baseline?: number;
}) {
  const simulated = state.source?.simulated;
  const usable =
    state.arriving &&
    state.features.available &&
    (simulated || (state.quality !== null && state.quality >= 50));
  const value = usable
    ? Math.min(
        1,
        Math.max(
          0,
          (((state.features.rms?.[0] || 0) - baseline) / 40) * sensitivity,
        ),
      )
    : 0;
  return (
    <div
      className={"aura-stage " + (!usable ? "suspended " : "") + style}
      style={
        {
          "--reactivity": value,
          "--aura-scale": 0.8 + value * 0.3,
          "--intensity": intensity,
        } as React.CSSProperties
      }
    >
      <div className="orbital o1" />
      <div className="orbital o2" />
      <div className="orbital o3" />
      <div className="aura-orb">
        <div className="orb-core" />
        {style === "avatar" && (
          <div className="avatar-face">
            <i />
            <i />
            <span />
          </div>
        )}
      </div>
      <div className="aura-label">
        <span className="eyebrow">
          {style === "avatar" ? "FEATURE AVATAR" : "NEURAL AURA"}
        </span>
        <b>{usable ? "Signal in motion" : "Visualization suspended"}</b>
        <small>
          {usable
            ? simulated
              ? "Synthetic amplitude → visual energy"
              : "EEG amplitude → visual energy"
            : "Requires recent samples and known adequate quality"}
        </small>
      </div>
    </div>
  );
}
