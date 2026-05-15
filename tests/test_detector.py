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
import pandas as pd
import pytest

from thunbit import (
    DemandStateDetector,
    STATE_ACTIONS,
    STATE_HORIZONS,
    StabilizedDemandDetector,
    StabilizedDemandDetectorV41,
    StabilizedDemandDetectorV42,
    StabilizedDemandDetectorV43,
    StabilizedDemandDetectorV44,
    StabilizedDemandDetectorV45,
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


def test_stabilized_v45_output_schema():
    det = StabilizedDemandDetectorV45()
    result = det.detect_rolling_stabilized(STABLE)
    assert len(result) > 0
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


@pytest.mark.parametrize("series", [STABLE, SHIFTED])
def test_v45_valid_states(series):
    det = StabilizedDemandDetectorV45()
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


def test_v45_refinement_defaults():
    det = StabilizedDemandDetectorV45()
    assert det.suppress_max_len == 3
    assert det.suppress_max_mean_conf == 0.52
    assert det.suppress_min_prev_gap == 14
    assert det.suppress_min_next_gap == 14
    assert det.merge_enabled is False


def _v45_fixture_output(states, confidences):
    t_vals = np.arange(len(states))
    return {
        "t": t_vals,
        "date": t_vals,
        "state": states,
        "raw_confidence": confidences,
        "baseline_confidence": np.zeros(len(states)),
        "normalized_confidence": confidences,
        "confidence": confidences,
        "pss": np.full(len(states), 50.0),
        "horizon": [STATE_HORIZONS[s] for s in states],
        "action": [STATE_ACTIONS[s] for s in states],
        "evidence": ["{}"] * len(states),
        "drift_run": np.zeros(len(states), dtype=int),
        "shift_run": np.zeros(len(states), dtype=int),
        "cooldown": np.zeros(len(states), dtype=int),
        "prev_state": ["STABLE"] + states[:-1],
    }


def test_v45_suppresses_short_low_conf_isolated_episode():
    det = StabilizedDemandDetectorV45()
    states = ["STABLE"] * 5 + ["DRIFT"] * 3 + ["STABLE"] * 20
    confs = [0.1] * 5 + [0.48, 0.50, 0.52] + [0.1] * 20
    df = det._apply_adaptive_episode_gating(pd.DataFrame(_v45_fixture_output(states, confs)))
    assert (df.iloc[5:8]["state"] == "STABLE").all()
    assert (df.iloc[5:8]["action"] == STATE_ACTIONS["STABLE"]).all()
    assert (df.iloc[5:8]["horizon"] == 50.0).all()
    assert np.allclose(df.iloc[5:8]["confidence"].to_numpy(), np.array([0.48, 0.50, 0.52]))


def test_v45_keeps_longer_episode():
    det = StabilizedDemandDetectorV45()
    states = ["STABLE"] * 4 + ["DRIFT"] * 4 + ["STABLE"] * 20
    confs = [0.1] * 4 + [0.40, 0.41, 0.42, 0.43] + [0.1] * 20
    df = det._apply_adaptive_episode_gating(pd.DataFrame(_v45_fixture_output(states, confs)))
    assert (df.iloc[4:8]["state"] == "DRIFT").all()


def test_v45_keeps_episode_when_next_gap_is_below_threshold():
    det = StabilizedDemandDetectorV45()
    states = (
        ["STABLE"] * 2
        + ["DRIFT"] * 2
        + ["STABLE"] * 10
        + ["DRIFT"] * 2
        + ["STABLE"] * 15
    )
    confs = [0.1] * 2 + [0.45, 0.46] + [0.1] * 10 + [0.44, 0.45] + [0.1] * 15
    df = det._apply_adaptive_episode_gating(pd.DataFrame(_v45_fixture_output(states, confs)))
    assert (df.iloc[2:4]["state"] == "DRIFT").all()


def test_v45_preserves_v44_output_columns():
    v44 = StabilizedDemandDetectorV44().detect_rolling_stabilized(STABLE)
    v45 = StabilizedDemandDetectorV45().detect_rolling_stabilized(STABLE)
    assert list(v45.columns) == list(v44.columns)


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
