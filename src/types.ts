export type Source = {
  id: string;
  kind: string;
  name: string;
  channels: string[];
  units: string[];
  nominal_rate: number;
  clock_domain: string;
  simulated: boolean;
  metadata: Record<string, unknown>;
};
export type Features = {
  available: boolean;
  reason?: string;
  frequencies?: number[];
  psd?: number[][];
  bands?: Record<string, number[]>;
  rms?: number[];
  peak_hz?: number[];
  samples_used?: number;
};
export type Recording = {
  active: boolean;
  id: string | null;
  error: string | null;
  persisted_samples: number;
  started: number | null;
};
export type Annotation = {
  timestamp: number;
  kind: string;
  label: string;
  persisted: boolean;
  ratings?: Record<string, number>;
};
export type Delivery = {
  sample_count: number;
  session_id: string;
  first_timestamp: number;
  last_timestamp: number;
  last_arrival: number;
  last_arrival_age: number;
  receiving: boolean;
  observed_rate: number | null;
  cols: unknown[];
  values: unknown[];
};
export type State = {
  cortex_connected?: boolean;
  cortex_session_id?: string | null;
  cortex_session_status?: string;
  cortex_delivery?: Record<string, Delivery>;
  cortex_subscribed?: string[];
  receiving_samples?: boolean;
  raw_eeg_available?: boolean;
  source: Source | null;
  arriving: boolean;
  total_samples: number;
  observed_rate: number | null;
  discontinuities: number;
  interpolated: number;
  last_sample_age: number | null;
  duration: number;
  error: string | null;
  quality: number | null;
  battery: number | null;
  metrics: null | {
    attention: number | null;
    cognitiveStress: number | null;
    stale: boolean;
  };
  features: Features;
  recording: Recording;
  annotations: Annotation[];
  waveform?: {
    timestamps: number[];
    values: number[][];
    gaps: number[];
    filtered: boolean;
  };
};
export type Session = {
  id: string;
  title: string;
  participant: string;
  started: number;
  stopped: number | null;
  status: string;
  source: Source;
  sample_count: number;
};
export type Diagnostic = {
  blocker?: { code: number; explanation: string; action: string } | null;
  account?: { logged_in: boolean; same_os_account?: boolean };
  availability: string;
  approval: string;
  authorized: boolean;
  version?: Record<string, unknown>;
  license: Record<string, unknown> | null;
  headsets: Array<{ id: string; status: string; customName?: string }>;
  streams: Array<{ streamName: string; cols: unknown[] }>;
  next_action: string;
  events: Array<{
    timestamp: number;
    operation: string;
    outcome: string;
    detail: unknown;
  }>;
};
export type Lsl = {
  checked: boolean;
  error?: string;
  streams: Array<{
    id: string;
    name: string;
    type: string;
    channels: number;
    nominal_rate: number;
    eeg_candidate: boolean;
  }>;
};
