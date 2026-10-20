"""Display-only transforms. Raw acquisition is never overwritten."""
import numpy as np
from scipy.signal import butter, sosfiltfilt, welch, stft, iirnotch, filtfilt

BANDS = {'Delta': (1, 4), 'Theta': (4, 8), 'Alpha': (8, 13), 'Beta': (13, 30), 'Gamma': (30, 45)}
SETTINGS = {'psd': 'Welch, Hann, 2 s windows, 50% overlap, constant detrend', 'bands_hz': BANDS, 'filter': 'Butterworth order 4, 1–40 Hz, zero-phase display only', 'version': 1}


def filter_values(values, rate, notch=0):
    a = np.asarray(values, dtype=float)
    if len(a) < max(32, rate) or rate < 90:
        return a
    a = sosfiltfilt(butter(4, [1, 40], fs=rate, btype='bandpass', output='sos'), a, axis=0)
    if notch in (50, 60) and rate > notch * 2:
        b, c = iirnotch(notch, 30, rate)
        a = filtfilt(b, c, a, axis=0)
    return a


def analyze(samples, rate, notch=0):
    if rate <= 0 or len(samples) < rate * 2:
        return {'available': False, 'reason': 'At least two seconds of regularly sampled data are required.'}
    # Use the most recent uninterrupted, non-interpolated segment. Never bridge gaps for PSD.
    cut = 0
    for i, s in enumerate(samples):
        if s.discontinuity or s.interpolated or not np.all(np.isfinite(s.values)):
            cut = i + 1
    samples = samples[cut:]
    if len(samples) < rate * 2:
        return {'available': False, 'reason': 'Insufficient contiguous samples after a gap or interpolated sample.'}
    a = np.asarray([s.values for s in samples])
    f, p = welch(a, fs=rate, nperseg=min(len(a), int(rate * 2)), axis=0)
    keep = (f >= 1) & (f <= min(45, rate / 2))
    bands = {name: np.trapezoid(p[(f >= lo) & (f < hi)], f[(f >= lo) & (f < hi)], axis=0).tolist() for name, (lo, hi) in BANDS.items()}
    rms = np.sqrt(np.mean((a - a.mean(axis=0)) ** 2, axis=0))
    return {'available': True, 'frequencies': f[keep].tolist(), 'psd': p[keep].T.tolist(), 'bands': bands, 'rms': rms.tolist(), 'peak_hz': f[keep][np.argmax(p[keep], axis=0)].tolist(), 'samples_used': len(samples), 'settings': SETTINGS}


FLAGGED_METRICS = {'attention', 'cognitiveStress', 'str', 'eng', 'exc', 'rel', 'int'}


def active_metrics(cols, values, stamp, now):
    mapped = dict(zip(cols, values))
    fresh = -1 <= now - stamp <= 15
    out = {'timestamp': stamp, 'stale': not fresh, 'origin': 'Cortex proprietary performance estimates'}
    for key in (c for c in cols if isinstance(c, str) and not c.endswith('.isActive')):
        flag = mapped.get(key + '.isActive')
        active_ok = flag is True if (key in FLAGGED_METRICS or flag is not None) else True
        v = mapped.get(key)
        out[key] = float(v) if active_ok and isinstance(v, (float, int)) and not isinstance(v, bool) and 0 <= v <= 1 and fresh else None
    return out
