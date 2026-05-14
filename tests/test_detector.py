"""
Tests for the THUNBIT detectors.

These are lightweight sanity checks, not an exhaustive benchmark.
They verify that:
  - detectors return output with the expected schema
  - a clear mean shift is detected within a reasonable number of days
  - stable series do not produce only SHIFT states
  - V4.3 / V4.4 state machine respects hysteresis (no immediate flip-flop)
"""

import numpy as np
import pytest

from thunbit import (
    DemandStateDetector,
    StabilizedDemandDetector,
    StabilizedDemandDetectorV41,
    StabilizedDemandDetectorV42,
    StabilizedDemandDetectorV43,
    StabilizedDemandDetectorV44,
)

RNG = np.random.default_rng(0)
STABLE = RNG.normal(100, 10, 400).clip(0)
SHIFTED = np.concatenate(
    [
        RNG.normal(100, 10, 200).clip(0),
        RNG.normal(180, 12, 200).clip(0),
    ]
)
VARIANCE_SPIKE = np.concatenate(
    [
        RNG.normal(100, 5, 200).clip(0),
        RNG.normal(100, 50, 200).clip(0),
    ]
)


# ---------------------------------------------------------------------------
# Schema checks
# ---------------------------------------------------------------------------

EXPECTED_COLS_BASE = {
    "t", "date", "state", "raw_confidence", "confidence",
    "pss", "horizon", "action", "evidence",
}

EXPECTED_COLS_STAB = EXPECTED_COLS_BASE | {"drift_run", "shift_run"}

EXPECTED_COLS_V42 = EXPECTED_COLS_STAB | {
    "baseline_confidence", "normalized_confidence", "cooldown", "prev_state"
}


def test_base_output_schema():
    det = DemandStateDetector()
    result = det.detect_rolling(STABLE)
    assert len(result) > 0
    assert EXPECTED_COLS_BASE.issubset(set(result.columns))


def test_stabilized_v4_output_schema():
    det = StabilizedDemandDetector()
    result = det.detect_rolling_stabilized(STABLE)
    assert len(result) > 0
    assert EXPECTED_COLS_STAB.issubset(set(result.columns))


def test_stabilized_v41_output_schema():
    det = StabilizedDemandDetectorV41()
    result = det.detect_rolling_stabilized(STABLE)
    assert len(result) > 0
    assert "cooldown" in result.columns


def test_stabilized_v42_output_schema():
    det = StabilizedDemandDetectorV42()
    result = det.detect_rolling_stabilized(STABLE)
    assert len(result) > 0
    assert EXPECTED_COLS_V42.issubset(set(result.columns))


def test_stabilized_v43_output_schema():
    det = StabilizedDemandDetectorV43()
    result = det.detect_rolling_stabilized(STABLE)
    assert len(result) > 0
    # V4.3 includes all V4.2 columns
    assert EXPECTED_COLS_V42.issubset(set(result.columns))


def test_stabilized_v44_output_schema():
    det = StabilizedDemandDetectorV44()
    result = det.detect_rolling_stabilized(STABLE)
    assert len(result) > 0
    # V4.4 keeps V4.3/V4.2 normalized output columns
    assert EXPECTED_COLS_V42.issubset(set(result.columns))


# ---------------------------------------------------------------------------
# Valid state values
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("series", [STABLE, SHIFTED])
def test_base_valid_states(series):
    det = DemandStateDetector()
    result = det.detect_rolling(series)
    assert set(result["state"]).issubset({"STABLE", "DRIFT", "SHIFT"})


@pytest.mark.parametrize("series", [STABLE, SHIFTED])
def test_v43_valid_states(series):
    det = StabilizedDemandDetectorV43()
    result = det.detect_rolling_stabilized(series)
    assert set(result["state"]).issubset({"STABLE", "DRIFT", "SHIFT"})


@pytest.mark.parametrize("series", [STABLE, SHIFTED])
def test_v44_valid_states(series):
    det = StabilizedDemandDetectorV44()
    result = det.detect_rolling_stabilized(series)
    assert set(result["state"]).issubset({"STABLE", "DRIFT", "SHIFT"})


# ---------------------------------------------------------------------------
# Detection checks
# ---------------------------------------------------------------------------

def test_base_detects_mean_shift():
    """Baseline detector should raise an alert after a clear mean shift."""
    det = DemandStateDetector()
    result = det.detect_rolling(SHIFTED)
    post_break = result[result["t"] >= 220]
    assert post_break["state"].isin(["DRIFT", "SHIFT"]).any(), (
        "Expected DRIFT or SHIFT on post-shift portion of series"
    )


def test_v42_detects_mean_shift():
    """V4.2 detector should raise an alert after a clear mean shift."""
    det = StabilizedDemandDetectorV42()
    result = det.detect_rolling_stabilized(SHIFTED)
    post_break = result[result["t"] >= 230]
    assert post_break["state"].isin(["DRIFT", "SHIFT"]).any(), (
        "Expected DRIFT or SHIFT on post-shift portion of series"
    )


def test_v43_detects_mean_shift():
    """V4.3 detector should raise an alert after a clear mean shift."""
    det = StabilizedDemandDetectorV43()
    result = det.detect_rolling_stabilized(SHIFTED)
    post_break = result[result["t"] >= 240]
    assert post_break["state"].isin(["DRIFT", "SHIFT"]).any(), (
        "Expected DRIFT or SHIFT on post-shift portion of series"
    )


def test_v44_detects_mean_shift():
    """V4.4 detector should raise an alert after a clear mean shift."""
    det = StabilizedDemandDetectorV44()
    result = det.detect_rolling_stabilized(SHIFTED)
    post_break = result[result["t"] >= 245]
    assert post_break["state"].isin(["DRIFT", "SHIFT"]).any(), (
        "Expected DRIFT or SHIFT on post-shift portion of series"
    )


def test_base_detects_variance_spike():
    """Baseline detector should detect a large variance increase."""
    det = DemandStateDetector()
    result = det.detect_rolling(VARIANCE_SPIKE)
    post_break = result[result["t"] >= 220]
    assert post_break["state"].isin(["DRIFT", "SHIFT"]).any()


def test_stable_series_not_all_shift():
    """Stable series should not be labelled SHIFT for the entire run."""
    det = DemandStateDetector()
    result = det.detect_rolling(STABLE)
    shift_frac = (result["state"] == "SHIFT").mean()
    assert shift_frac < 0.5, f"SHIFT fraction {shift_frac:.2f} is unexpectedly high"


# ---------------------------------------------------------------------------
# Baseline normalization checks (V4.2 / V4.3)
# ---------------------------------------------------------------------------

def test_v42_baseline_confidence_nonneg():
    """V4.2 baseline_confidence should always be non-negative."""
    det = StabilizedDemandDetectorV42()
    result = det.detect_rolling_stabilized(STABLE)
    assert (result["baseline_confidence"] >= 0.0).all()


def test_v42_normalized_confidence_in_range():
    """V4.2 normalized_confidence should be clipped to [0, 1]."""
    det = StabilizedDemandDetectorV42()
    result = det.detect_rolling_stabilized(STABLE)
    assert result["normalized_confidence"].between(0.0, 1.0).all()


def test_v43_baseline_confidence_nonneg():
    """V4.3 baseline_confidence should always be non-negative."""
    det = StabilizedDemandDetectorV43()
    result = det.detect_rolling_stabilized(STABLE)
    assert (result["baseline_confidence"] >= 0.0).all()


def test_v43_normalized_confidence_in_range():
    """V4.3 normalized_confidence should be clipped to [0, 1]."""
    det = StabilizedDemandDetectorV43()
    result = det.detect_rolling_stabilized(STABLE)
    assert result["normalized_confidence"].between(0.0, 1.0).all()


def test_v44_baseline_confidence_nonneg():
    """V4.4 baseline_confidence should always be non-negative."""
    det = StabilizedDemandDetectorV44()
    result = det.detect_rolling_stabilized(STABLE)
    assert (result["baseline_confidence"] >= 0.0).all()


def test_v44_normalized_confidence_in_range():
    """V4.4 normalized_confidence should be clipped to [0, 1]."""
    det = StabilizedDemandDetectorV44()
    result = det.detect_rolling_stabilized(STABLE)
    assert result["normalized_confidence"].between(0.0, 1.0).all()


def test_v43_warmup_suppression():
    """V4.3 warmup suppression should prevent any alert in the first warmup_days rows."""
    det = StabilizedDemandDetectorV43(warmup_days=30)
    result = det.detect_rolling_stabilized(SHIFTED)
    warmup_rows = result.iloc[:30]
    # During warmup, state should remain STABLE (no new entries)
    assert (warmup_rows["state"] == "STABLE").all(), (
        "V4.3 should suppress new alert entries during warmup period"
    )


def test_v44_warmup_suppression():
    """V4.4 warmup suppression should prevent any alert in the first warmup_days rows."""
    det = StabilizedDemandDetectorV44(warmup_days=30)
    result = det.detect_rolling_stabilized(SHIFTED)
    warmup_rows = result.iloc[:30]
    assert (warmup_rows["state"] == "STABLE").all(), (
        "V4.4 should suppress new alert entries during warmup period"
    )


def test_v44_calibration_defaults():
    det = StabilizedDemandDetectorV44()
    assert det.drift_entry == 0.42
    assert det.drift_exit == 0.22
    assert det.shift_entry == 0.68
    assert det.shift_exit == 0.44
    assert det.drift_confirm_days == 3
    assert det.shift_confirm_days == 1


# ---------------------------------------------------------------------------
# Confidence range checks
# ---------------------------------------------------------------------------

def test_confidence_in_range():
    det = DemandStateDetector()
    result = det.detect_rolling(STABLE)
    assert result["raw_confidence"].between(0.0, 1.0).all()
    assert result["confidence"].between(0.0, 1.0).all()


def test_pss_in_range():
    det = DemandStateDetector()
    result = det.detect_rolling(STABLE)
    assert result["pss"].between(0.0, 100.0).all()


# ---------------------------------------------------------------------------
# Short series guard
# ---------------------------------------------------------------------------

def test_short_series_returns_empty():
    """Series too short to produce any output should return an empty DataFrame."""
    det = DemandStateDetector()
    short = np.ones(50)  # window_long + window_short = 111 by default
    result = det.detect_rolling(short)
    assert len(result) == 0


# ---------------------------------------------------------------------------
# Minimal hysteresis check for V4.3
# ---------------------------------------------------------------------------

def test_v43_no_single_day_state_flip():
    """State should not oscillate back to STABLE and DRIFT on consecutive days."""
    det = StabilizedDemandDetectorV43()
    result = det.detect_rolling_stabilized(STABLE)
    states = result["state"].tolist()
    # Count same-day back-and-forth transitions
    flips = sum(
        1
        for a, b, c in zip(states, states[1:], states[2:])
        if a == c and a != b
    )
    # Allow a small number; should not be pervasive
    assert flips < len(states) * 0.1, (
        f"Too many single-day state reversals ({flips} / {len(states)})"
    )
