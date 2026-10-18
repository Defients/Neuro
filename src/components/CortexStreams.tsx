import type { State } from "../types";
import { Panel, Badge } from "./UI";

export function CortexStreams({
  state,
  online,
}: {
  state: State;
  online: boolean;
}) {
  const subscribed = state.cortex_subscribed || [];
  return (
    <div style={{ marginBottom: 20 }}>
      <div className="notice"><span>Headset: {state.cortex_connected ? 'Connected' : 'Unverified'} · Session: {state.cortex_session_status || 'Unverified'} ({state.cortex_session_id || 'none'}) · Subscriptions: {subscribed.length} · Incoming samples: {online && state.receiving_samples ? 'Receiving' : 'Not receiving'}</span></div>
      <div className="notice">
        <span>
          <b>Connected source: {state.source?.name}</b> ·{" "}
          {subscribed.length
            ? `Subscribed: ${subscribed.join(", ")}`
            : "No active subscriptions"}
          <br />
          {online && state.receiving_samples
            ? "Receiving timestamped Cortex samples."
            : "Data delivery has not been confirmed or is stale."}
          <br />
          {!state.raw_eeg_available &&
            "Raw EEG Unavailable — no raw waveform or raw PSD. License checks remain enforced. Band estimates below are Cortex outputs, not raw EEG."}
        </span>
      </div>
      <div className="advanced-grid">
        {["dev", "eq", "met", "mot", "pow"].map((name) => {
          const item = state.cortex_delivery?.[name];
          const fresh = online && item?.receiving;
          return (
            <Panel
              key={name}
              title={
                {
                  dev: "Device & contact quality",
                  eq: "EEG quality measurements",
                  met: "Proprietary cognitive estimates",
                  mot: "Head motion",
                  pow: "Cortex band-power estimates",
                }[name] || name
              }
              action={
                <Badge tone={fresh ? "cyan" : "neutral"}>
                  {fresh
                    ? "RECEIVING"
                    : subscribed.includes(name)
                      ? "SUBSCRIBED"
                      : "UNAVAILABLE"}
                </Badge>
              }
            >
              <div className="padded">
                <p className="footnote">
                  {item?.sample_count || 0} frames · arrival rate{" "}
                  {item?.observed_rate?.toFixed(2) ?? "—"} Hz · last arrival{" "}
                  {item?.sample_count
                    ? item.last_arrival_age.toFixed(1) + " s ago"
                    : "never"}
                </p>
                {!!item?.sample_count && (
                  <>
                    <p className="footnote">
                      Session {item.session_id}
                      <br />
                      Source timestamp {item.last_timestamp.toFixed(6)} (Unix
                      seconds)
                    </p>
                    {fresh ? (
                      <dl className="health-rows">
                        {item.cols.map((label, i) => (
                          <div key={i}>
                            <dt>
                              {Array.isArray(label)
                                ? label.join(" / ")
                                : String(label)}
                            </dt>
                            <dd>
                              {name === "met" &&
                              !String(label).endsWith(".isActive") &&
                              state.metrics?.[
                                String(label) as "attention" | "cognitiveStress"
                              ] == null
                                ? "Estimate unavailable"
                                : JSON.stringify(item.values[i])}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    ) : (
                      <p className="footnote">
                        No recent measurement; previous values withheld.
                      </p>
                    )}
                  </>
                )}
              </div>
            </Panel>
          );
        })}
      </div>
    </div>
  );
}
