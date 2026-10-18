import math
import numpy as np
import pytest
from backend.sources import synthetic, Acquisition
from backend.models import Sample, Source
from backend.processing import analyze, filter_values, active_metrics
from backend.cortex import decode_eeg


def test_deterministic_fixture_and_ten_hz_peak():
    samples = [synthetic(i) for i in range(128 * 8)]
    assert samples[100].values == synthetic(100).values
    result = analyze(samples, 128)
    assert result['available']
    assert result['peak_hz'] == [10, 10]
    assert result['bands']['Alpha'][0] > result['bands']['Theta'][0] * 3


def test_filter_attenuates_line_noise_without_mutating_raw():
    t = np.arange(128 * 8) / 128
    raw = (np.sin(2 * np.pi * 10 * t) + np.sin(2 * np.pi * 50 * t))[:, None]
    copy = raw.copy()
    filtered = filter_values(raw, 128, 50)
    assert np.array_equal(raw, copy)
    spectrum = np.abs(np.fft.rfft(filtered[256:-256, 0]))
    freq = np.fft.rfftfreq(len(filtered) - 512, 1/128)
    assert spectrum[np.argmin(abs(freq-10))] > 20 * spectrum[np.argmin(abs(freq-50))]


def test_psd_wont_bridge_gaps_or_interpolated_samples():
    s = [synthetic(i) for i in range(1024)]
    s[-128].discontinuity = 'clock_jump'
    assert not analyze(s, 128)['available']
    s[-128].discontinuity = None
    s[-128].interpolated = True
    assert not analyze(s, 128)['available']


def test_metrics_require_active_flags_current_timestamp_and_mn8_labels():
    cols = ['attention.isActive', 'attention', 'cognitiveStress.isActive', 'cognitiveStress', 'str']
    assert active_metrics(cols, [True, .8, False, .4, .9], 100, 101)['attention'] == .8
    assert active_metrics(cols, [True, .8, False, .4, .9], 100, 101)['cognitiveStress'] is None
    assert active_metrics(cols, [True, .8, True, .4, .9], 100, 116)['attention'] is None
    assert active_metrics(['attention'], [.8], 100, 100)['attention'] is None
    assert active_metrics(cols, [True, None, True, float('nan'), .9], 100, 100)['cognitiveStress'] is None


def test_eeg_mapping_is_from_cols_and_preserves_metadata():
    cols = {'eeg': ['INTERPOLATED', 'T8', 'COUNTER', 'T7', 'MARKER_HARDWARE', 'MARKERS']}
    s = decode_eeg({'time':12.5,'sid':'session','eeg':[1,2.25,7,-3.125,1,[{'value':'blink'}]]}, cols)
    assert s.values == [2.25, -3.125]
    assert s.interpolated and s.counter == 7
    assert s.metadata['cortex']['MARKERS'] == [{'value':'blink'}]
    with pytest.raises(ValueError):
        decode_eeg({'time':12.5,'eeg':[1,2]}, cols)


def test_integrity_preserves_out_of_order_and_tracks_missing(store):
    from backend.storage import Recorder
    a = Acquisition(Recorder(store), store)
    a.reset(Source('fixture','synthetic','fixture',['L'],['µV'],128,'test',True))
    a.ingest([Sample(10,[1]), Sample(10+1/128,[2]), Sample(10+3/128,[3]), Sample(9,[4])])
    assert a.gaps == 2
    assert list(a.buffer)[-1].timestamp == 9
    assert list(a.buffer)[-1].discontinuity == 'out_of_order_or_clock_reset'
    a.ingest([Sample(11,[float('nan')])])
    assert a.total == 4
    assert len(a.buffer) == 4


def test_buffer_is_bounded(store):
    from backend.storage import Recorder
    a = Acquisition(Recorder(store), store)
    a.reset(Source('fixture','synthetic','fixture',['L'],['µV'],128,'test',True))
    a.ingest([Sample(i/128,[i]) for i in range(40000)])
    assert len(a.buffer) == 32768
    assert a.total == 40000
