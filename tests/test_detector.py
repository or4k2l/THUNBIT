"""
Tests for the THUNBIT detectors.

These are lightweight sanity checks, not an exhaustive benchmark.
They verify that:
  - detectors return output with the expected schema
  - a clear mean shift is detected within a reasonable number of days
  - stable series do not produce only SHIFT states
  - V4.3 state machine respects hysteresis (no immediate flip-flop)
"""

import numpy as np
import pytest

from thunbit import (
    DemandStateDetector,
    StabilizedDemandDetector,
    StabilizedDemandDetectorV41,
    StabilizedDemandDetectorV43,
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


def test_stabilized_v43_output_schema():
    det = StabilizedDemandDetectorV43()
    result = det.detect_rolling_stabilized(STABLE)
    assert len(result) > 0
    assert EXPECTED_COLS_STAB.issubset(set(result.columns))


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


def test_v43_detects_mean_shift():
    """V4.3 detector should raise an alert after a clear mean shift."""
    det = StabilizedDemandDetectorV43()
    result = det.detect_rolling_stabilized(SHIFTED)
    post_break = result[result["t"] >= 240]
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
