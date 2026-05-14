"""
thunbit.stabilized
~~~~~~~~~~~~~~~~~~
Stabilized demand-state detector variants.

This module provides five progressively refined detectors that add a state
machine on top of the raw confidence score produced by ``DemandStateDetector``:

* ``StabilizedDemandDetector``   – V4: hysteresis + smoothing + confirmation
* ``StabilizedDemandDetectorV41`` – V4.1: adds cooldown, relaxed thresholds
* ``StabilizedDemandDetectorV42`` – V4.2: baseline-normalized scoring; major
  reduction in stable-series false alerts, but over-damped on real breaks
* ``StabilizedDemandDetectorV43`` – V4.3: first lower-quantile + warmup variant
* ``StabilizedDemandDetectorV44`` – V4.4 (V4.4b calibration): recommended
  experimental operating point; stricter state-machine calibration on V4.3's
  normalized-score design

All variants are **experimental**.  Stable-series false-alert rates remain an
active calibration problem.  The key unresolved design issue is score
calibration, not just state-transition logic.  See ``docs/benchmarking.md``
and ``docs/limitations.md`` for observed trade-offs.

Research prototype – not validated for production use.
"""

from __future__ import annotations

from collections import deque

import numpy as np
import pandas as pd

from .detector import DemandStateDetector
from ._states import STATE_ACTIONS


class StabilizedDemandDetector(DemandStateDetector):
    """V4 stabilized detector: adds a state machine on top of the base scorer.

    Key additions over the baseline ``DemandStateDetector``:

    * **Smoothing** – raw confidence is averaged over a short window before
      threshold comparisons, reducing single-day spikes.
    * **Hysteresis** – separate entry and exit thresholds prevent rapid
      state toggling near borderline confidence values.
    * **Confirmation** – a state change requires the confidence to remain
      above the entry threshold for a minimum number of consecutive days.

    Parameters
    ----------
    window_long, window_short : int
        Same as base class.
    drift_thresh, shift_thresh : float
        Baseline thresholds inherited from base class (informational).
    smoothing_window : int
        Number of consecutive confidence values to average.
    drift_entry, drift_exit : float
        Hysteresis band for the DRIFT state.
    shift_entry, shift_exit : float
        Hysteresis band for the SHIFT state.
    drift_confirm_days : int
        Consecutive days above ``drift_entry`` required to enter DRIFT.
    shift_confirm_days : int
        Consecutive days above ``shift_entry`` required to enter SHIFT.

    Notes
    -----
    The inter-cluster false-alert rate on stable synthetic series is still
    non-trivial at these default settings.  See V4.1 and V4.3 for reduced
    false-alert configurations.
    """

    def __init__(
        self,
        window_long: int = 90,
        window_short: int = 21,
        drift_thresh: float = 0.28,
        shift_thresh: float = 0.55,
        smoothing_window: int = 3,
        drift_entry: float = 0.32,
        drift_exit: float = 0.22,
        shift_entry: float = 0.60,
        shift_exit: float = 0.45,
        drift_confirm_days: int = 3,
        shift_confirm_days: int = 2,
    ) -> None:
        super().__init__(
            window_long=window_long,
            window_short=window_short,
            drift_thresh=drift_thresh,
            shift_thresh=shift_thresh,
        )
        self.smoothing_window = smoothing_window
        self.drift_entry = drift_entry
        self.drift_exit = drift_exit
        self.shift_entry = shift_entry
        self.shift_exit = shift_exit
        self.drift_confirm_days = drift_confirm_days
        self.shift_confirm_days = shift_confirm_days

    def detect_rolling_stabilized(
        self,
        series,
        dates=None,
        step: int = 1,
    ) -> pd.DataFrame:
        """Stabilized rolling detection with state machine.

        Parameters
        ----------
        series : array-like
            Full demand history.
        dates : array-like, optional
            Date labels for each observation.
        step : int
            Step size between evaluations.

        Returns
        -------
        pd.DataFrame
            One row per evaluated timestep, with columns: ``t``, ``date``,
            ``state``, ``raw_confidence``, ``confidence``, ``pss``,
            ``horizon``, ``action``, ``evidence``, ``drift_run``,
            ``shift_run``.
        """
        s = np.asarray(series, dtype=float)
        if dates is None:
            dates = np.arange(len(s))

        start = self.window_long + self.window_short
        rows = []

        conf_hist: deque = deque(maxlen=self.smoothing_window)
        current_state = "STABLE"
        drift_run = 0
        shift_run = 0

        for i in range(start, len(s) + 1, step):
            raw = self.detect_raw(s[:i])
            raw_conf = raw["raw_confidence"]
            conf_hist.append(raw_conf)
            smooth_conf = float(np.mean(conf_hist))

            # Update consecutive-day counters.
            if smooth_conf >= self.shift_entry:
                shift_run += 1
            else:
                shift_run = 0

            if smooth_conf >= self.drift_entry:
                drift_run += 1
            else:
                drift_run = 0

            # State machine transitions.
            if current_state == "STABLE":
                if shift_run >= self.shift_confirm_days:
                    current_state = "SHIFT"
                elif drift_run >= self.drift_confirm_days:
                    current_state = "DRIFT"

            elif current_state == "DRIFT":
                if shift_run >= self.shift_confirm_days:
                    current_state = "SHIFT"
                elif smooth_conf < self.drift_exit:
                    current_state = "STABLE"

            elif current_state == "SHIFT":
                if smooth_conf < self.shift_exit:
                    if smooth_conf >= self.drift_entry:
                        current_state = "DRIFT"
                    else:
                        current_state = "STABLE"

            rows.append(
                {
                    "t": i - 1,
                    "date": dates[i - 1],
                    "state": current_state,
                    "raw_confidence": round(raw_conf, 4),
                    "confidence": round(smooth_conf, 4),
                    "pss": raw["pss"],
                    "horizon": self._horizon(current_state, raw["pss"]),
                    "action": STATE_ACTIONS[current_state],
                    "evidence": raw["evidence"],
                    "drift_run": drift_run,
                    "shift_run": shift_run,
                }
            )

        return pd.DataFrame(rows)


class StabilizedDemandDetectorV41(StabilizedDemandDetector):
    """V4.1 detector: adds cooldown suppression, relaxed confirmation thresholds.

    Key changes from V4:

    * **Cooldown** – after returning to STABLE, re-escalation to DRIFT is
      suppressed for ``cooldown_days`` days.  This reduces repeated fragmented
      alert clusters on borderline series without raising the entry threshold.
    * **Relaxed confirm** – ``drift_confirm_days`` reduced from 3 → 2,
      ``shift_confirm_days`` from 2 → 1.  This partially recovers the
      detection delay that V4 introduced on fast-changing scenarios.
    * **Lower drift entry** – 0.32 → 0.30 (less aggressive suppression of
      gradual-drift detection).

    The trade-off: slightly fewer stable-series false-alert clusters than V4,
    but detection delay is still higher than the no-state-machine baseline on
    some scenarios (particularly intermittent demand).

    Parameters
    ----------
    cooldown_days : int
        Days of STABLE→DRIFT suppression after returning from an alert state.
    All other parameters : see ``StabilizedDemandDetector``.
    """

    def __init__(
        self,
        window_long: int = 90,
        window_short: int = 21,
        drift_thresh: float = 0.28,
        shift_thresh: float = 0.55,
        smoothing_window: int = 2,
        drift_entry: float = 0.30,
        drift_exit: float = 0.24,
        shift_entry: float = 0.58,
        shift_exit: float = 0.48,
        drift_confirm_days: int = 2,
        shift_confirm_days: int = 1,
        cooldown_days: int = 5,
    ) -> None:
        super().__init__(
            window_long=window_long,
            window_short=window_short,
            drift_thresh=drift_thresh,
            shift_thresh=shift_thresh,
            smoothing_window=smoothing_window,
            drift_entry=drift_entry,
            drift_exit=drift_exit,
            shift_entry=shift_entry,
            shift_exit=shift_exit,
            drift_confirm_days=drift_confirm_days,
            shift_confirm_days=shift_confirm_days,
        )
        self.cooldown_days = cooldown_days

    def detect_rolling_stabilized(
        self,
        series,
        dates=None,
        step: int = 1,
    ) -> pd.DataFrame:
        """V4.1 rolling detection with cooldown suppression.

        Returns
        -------
        pd.DataFrame
            Same schema as ``StabilizedDemandDetector.detect_rolling_stabilized``
            with the addition of a ``cooldown`` column showing the remaining
            suppression days at each timestep.
        """
        s = np.asarray(series, dtype=float)
        if dates is None:
            dates = np.arange(len(s))

        start = self.window_long + self.window_short
        rows = []

        conf_hist: deque = deque(maxlen=self.smoothing_window)
        current_state = "STABLE"
        drift_run = 0
        shift_run = 0
        cooldown = 0

        for i in range(start, len(s) + 1, step):
            raw = self.detect_raw(s[:i])
            raw_conf = raw["raw_confidence"]
            conf_hist.append(raw_conf)
            smooth_conf = float(np.mean(conf_hist))

            # Update consecutive-day counters.
            if smooth_conf >= self.shift_entry:
                shift_run += 1
            else:
                shift_run = 0

            if smooth_conf >= self.drift_entry:
                drift_run += 1
            else:
                drift_run = 0

            # State machine with cooldown.
            if current_state == "STABLE":
                if shift_run >= self.shift_confirm_days:
                    current_state = "SHIFT"
                    cooldown = 0
                elif cooldown > 0:
                    cooldown -= 1
                elif drift_run >= self.drift_confirm_days:
                    current_state = "DRIFT"

            elif current_state == "DRIFT":
                if shift_run >= self.shift_confirm_days:
                    current_state = "SHIFT"
                    cooldown = 0
                elif smooth_conf < self.drift_exit:
                    current_state = "STABLE"
                    cooldown = self.cooldown_days

            elif current_state == "SHIFT":
                if smooth_conf < self.shift_exit:
                    if smooth_conf >= self.drift_entry:
                        current_state = "DRIFT"
                    else:
                        current_state = "STABLE"
                        cooldown = self.cooldown_days

            rows.append(
                {
                    "t": i - 1,
                    "date": dates[i - 1],
                    "state": current_state,
                    "raw_confidence": round(raw_conf, 4),
                    "confidence": round(smooth_conf, 4),
                    "pss": raw["pss"],
                    "horizon": self._horizon(current_state, raw["pss"]),
                    "action": STATE_ACTIONS[current_state],
                    "evidence": raw["evidence"],
                    "drift_run": drift_run,
                    "shift_run": shift_run,
                    "cooldown": cooldown,
                }
            )

        return pd.DataFrame(rows)


class StabilizedDemandDetectorV42(StabilizedDemandDetectorV41):
    """V4.2 detector – baseline-normalized scoring (historical reference).

    V4.2 introduced a fundamentally different approach to score calibration:
    instead of comparing raw confidence against a fixed threshold, it measures
    confidence *above the SKU's own recent noise level*.  This yielded a major
    reduction in stable-series false-alert burden in benchmarks.

    Key concept:

    * A rolling baseline of recent raw-confidence values is maintained.
    * ``normalized_confidence = max(0, raw_conf - baseline) * excess_scale``
    * The state machine then operates on this normalized (excess) score.

    V4.2 benchmark findings (synthetic data, 10 seeds):

    * Stable ``any_alert_rate`` fell from 1.00 to 0.60.
    * Stable ``mean_alert_days_pct`` fell from ~32% to ~3%.
    * Stable ``mean_fp_clusters`` fell from 4.7 to 1.0.
    * However, mean detection delay on cycle-break and gradual-drift scenarios
      roughly tripled relative to V4.1.  Intermittent detection rate dropped
      to 0.5.

    V4.2 is kept here as a historical reference showing that score
    normalization is the right design direction.  **V4.4 is the recommended
    experimental operating point.**

    Parameters
    ----------
    baseline_window : int
        Length of the rolling window used to compute the confidence baseline.
    baseline_stat : {"median", "mean"}
        Statistic used to summarise the baseline window.
    excess_scale : float
        Multiplier applied to the excess-above-baseline signal before clipping
        to [0, 1].
    All other parameters : see ``StabilizedDemandDetectorV41``.

    Notes
    -----
    Output DataFrame has additional columns ``baseline_confidence``,
    ``normalized_confidence``, and ``prev_state`` compared with V4.1.
    """

    def __init__(
        self,
        window_long: int = 90,
        window_short: int = 21,
        drift_thresh: float = 0.28,
        shift_thresh: float = 0.55,
        smoothing_window: int = 2,
        baseline_window: int = 21,
        baseline_stat: str = "median",
        excess_scale: float = 2.0,
        drift_entry: float = 0.30,
        drift_exit: float = 0.24,
        shift_entry: float = 0.58,
        shift_exit: float = 0.48,
        drift_confirm_days: int = 2,
        shift_confirm_days: int = 1,
        cooldown_days: int = 5,
    ) -> None:
        super().__init__(
            window_long=window_long,
            window_short=window_short,
            drift_thresh=drift_thresh,
            shift_thresh=shift_thresh,
            smoothing_window=smoothing_window,
            drift_entry=drift_entry,
            drift_exit=drift_exit,
            shift_entry=shift_entry,
            shift_exit=shift_exit,
            drift_confirm_days=drift_confirm_days,
            shift_confirm_days=shift_confirm_days,
            cooldown_days=cooldown_days,
        )
        self.baseline_window = baseline_window
        self.baseline_stat = baseline_stat
        self.excess_scale = excess_scale

    def _baseline_value(self, hist) -> float:
        """Compute the baseline from recent raw-confidence history."""
        arr = np.asarray(hist, dtype=float)
        if len(arr) == 0:
            return 0.0
        if self.baseline_stat == "mean":
            return float(np.mean(arr))
        return float(np.median(arr))

    def detect_rolling_stabilized(
        self,
        series,
        dates=None,
        step: int = 1,
    ) -> pd.DataFrame:
        """V4.2 rolling detection with baseline-normalized confidence.

        Returns
        -------
        pd.DataFrame
            Columns: all V4.1 columns plus ``baseline_confidence``,
            ``normalized_confidence``, and ``prev_state``.
        """
        s = np.asarray(series, dtype=float)
        if dates is None:
            dates = np.arange(len(s))

        start = self.window_long + self.window_short
        rows = []

        raw_hist: deque = deque(maxlen=self.baseline_window)
        conf_hist: deque = deque(maxlen=self.smoothing_window)
        current_state = "STABLE"
        drift_run = 0
        shift_run = 0
        cooldown = 0

        for i in range(start, len(s) + 1, step):
            raw = self.detect_raw(s[:i])
            raw_conf = raw["raw_confidence"]

            # Baseline computed from history accumulated so far (before this step).
            baseline_conf = self._baseline_value(raw_hist)
            excess_conf = max(0.0, raw_conf - baseline_conf)
            normalized_conf = min(excess_conf * self.excess_scale, 1.0)

            conf_hist.append(normalized_conf)
            smooth_conf = float(np.mean(conf_hist))

            # Update consecutive-day counters.
            if smooth_conf >= self.shift_entry:
                shift_run += 1
            else:
                shift_run = 0

            if smooth_conf >= self.drift_entry:
                drift_run += 1
            else:
                drift_run = 0

            prev_state = current_state

            # State machine with cooldown.
            if current_state == "STABLE":
                if shift_run >= self.shift_confirm_days:
                    current_state = "SHIFT"
                    cooldown = 0
                elif cooldown > 0:
                    cooldown -= 1
                elif drift_run >= self.drift_confirm_days:
                    current_state = "DRIFT"

            elif current_state == "DRIFT":
                if shift_run >= self.shift_confirm_days:
                    current_state = "SHIFT"
                    cooldown = 0
                elif smooth_conf < self.drift_exit:
                    current_state = "STABLE"
                    cooldown = self.cooldown_days

            elif current_state == "SHIFT":
                if smooth_conf < self.shift_exit:
                    if smooth_conf >= self.drift_entry:
                        current_state = "DRIFT"
                    else:
                        current_state = "STABLE"
                        cooldown = self.cooldown_days

            rows.append(
                {
                    "t": i - 1,
                    "date": dates[i - 1],
                    "state": current_state,
                    "raw_confidence": round(raw_conf, 4),
                    "baseline_confidence": round(baseline_conf, 4),
                    "normalized_confidence": round(normalized_conf, 4),
                    "confidence": round(smooth_conf, 4),
                    "pss": raw["pss"],
                    "horizon": self._horizon(current_state, raw["pss"]),
                    "action": STATE_ACTIONS[current_state],
                    "evidence": raw["evidence"],
                    "drift_run": drift_run,
                    "shift_run": shift_run,
                    "cooldown": cooldown,
                    "prev_state": prev_state,
                }
            )

            # Update baseline history *after* scoring the current step.
            raw_hist.append(raw_conf)

        return pd.DataFrame(rows)


class StabilizedDemandDetectorV43(StabilizedDemandDetectorV42):
    """V4.3 detector – historical lower-quantile + warmup reference.

    V4.3 builds on V4.2's baseline-normalization concept and recovers much of
    the detection responsiveness that V4.2 sacrificed.  The two key changes:

    * **Lower-quantile baseline** – instead of the rolling median (50th
      percentile), V4.3 tracks the 25th percentile of recent raw-confidence
      values.  The lower quantile stays nearer the true noise floor, so genuine
      breaks produce a larger excess signal that is not quickly cancelled by a
      rising median baseline.
    * **Warmup suppression** – state changes are suppressed for the first
      ``warmup_days`` output rows, during which the baseline history is still
      filling up and produces unreliable estimates.

    Additional tuning relative to V4.2:

    * Longer ``baseline_window`` (28 vs. 21) for a slower, more stable baseline.
    * ``excess_scale`` remains 2.0; threshold recalibration is handled by
      raising the entry levels to account for the different normalized score
      range produced by the lower-quantile baseline.
    * Slightly more sensitive entry thresholds to recover break detection speed.
    * Longer ``cooldown_days`` (7 vs. 5).

    **Important caveats:**

    * V4.3 reduces stable-series false alerts meaningfully compared with V4.1,
      but does not eliminate them.  The stable false-alert calibration problem
      is **unsolved**.
    * Detection delay on gradual-drift and intermittent scenarios is still
      higher than the no-state-machine baseline.
    * All parameters were tuned on simulated data; behaviour on real SKU data
      is unknown.
    * V4.3 remains available for historical comparison and backward
      compatibility, but is no longer the recommended experimental default.

    Parameters
    ----------
    baseline_quantile : float
        Quantile (0–1) of the raw-confidence history used as the baseline.
        Default 0.25 (25th percentile).
    warmup_days : int
        Number of initial output rows during which state changes from STABLE
        are suppressed.  Prevents early false alerts while the baseline window
        fills up.
    All other parameters : see ``StabilizedDemandDetectorV42``, with updated
    defaults.
    """

    def __init__(
        self,
        window_long: int = 90,
        window_short: int = 21,
        drift_thresh: float = 0.28,
        shift_thresh: float = 0.55,
        smoothing_window: int = 2,
        baseline_window: int = 28,
        baseline_quantile: float = 0.25,
        excess_scale: float = 2.0,
        drift_entry: float = 0.38,
        drift_exit: float = 0.22,
        shift_entry: float = 0.65,
        shift_exit: float = 0.44,
        drift_confirm_days: int = 2,
        shift_confirm_days: int = 1,
        cooldown_days: int = 7,
        warmup_days: int = 28,
    ) -> None:
        super().__init__(
            window_long=window_long,
            window_short=window_short,
            drift_thresh=drift_thresh,
            shift_thresh=shift_thresh,
            smoothing_window=smoothing_window,
            baseline_window=baseline_window,
            baseline_stat="median",  # overridden by _baseline_value below
            excess_scale=excess_scale,
            drift_entry=drift_entry,
            drift_exit=drift_exit,
            shift_entry=shift_entry,
            shift_exit=shift_exit,
            drift_confirm_days=drift_confirm_days,
            shift_confirm_days=shift_confirm_days,
            cooldown_days=cooldown_days,
        )
        self.baseline_quantile = baseline_quantile
        self.warmup_days = warmup_days

    def _baseline_value(self, hist) -> float:
        """Compute the lower-quantile baseline from recent raw-confidence history."""
        arr = np.asarray(hist, dtype=float)
        if len(arr) == 0:
            return 0.0
        return float(np.quantile(arr, self.baseline_quantile))

    def detect_rolling_stabilized(
        self,
        series,
        dates=None,
        step: int = 1,
    ) -> pd.DataFrame:
        """V4.3 rolling detection: lower-quantile baseline + warmup suppression.

        Returns
        -------
        pd.DataFrame
            Same schema as ``StabilizedDemandDetectorV42.detect_rolling_stabilized``.
        """
        s = np.asarray(series, dtype=float)
        if dates is None:
            dates = np.arange(len(s))

        start = self.window_long + self.window_short
        rows = []

        raw_hist: deque = deque(maxlen=self.baseline_window)
        conf_hist: deque = deque(maxlen=self.smoothing_window)
        current_state = "STABLE"
        drift_run = 0
        shift_run = 0
        cooldown = 0
        output_row = 0  # counts output rows for warmup suppression

        for i in range(start, len(s) + 1, step):
            raw = self.detect_raw(s[:i])
            raw_conf = raw["raw_confidence"]

            baseline_conf = self._baseline_value(raw_hist)
            excess_conf = max(0.0, raw_conf - baseline_conf)
            normalized_conf = min(excess_conf * self.excess_scale, 1.0)

            conf_hist.append(normalized_conf)
            smooth_conf = float(np.mean(conf_hist))

            # Update consecutive-day counters.
            if smooth_conf >= self.shift_entry:
                shift_run += 1
            else:
                shift_run = 0

            if smooth_conf >= self.drift_entry:
                drift_run += 1
            else:
                drift_run = 0

            prev_state = current_state

            in_warmup = output_row < self.warmup_days

            if not in_warmup:
                # State machine with cooldown (same logic as V4.2).
                if current_state == "STABLE":
                    if shift_run >= self.shift_confirm_days:
                        current_state = "SHIFT"
                        cooldown = 0
                    elif cooldown > 0:
                        cooldown -= 1
                    elif drift_run >= self.drift_confirm_days:
                        current_state = "DRIFT"

                elif current_state == "DRIFT":
                    if shift_run >= self.shift_confirm_days:
                        current_state = "SHIFT"
                        cooldown = 0
                    elif smooth_conf < self.drift_exit:
                        current_state = "STABLE"
                        cooldown = self.cooldown_days

                elif current_state == "SHIFT":
                    if smooth_conf < self.shift_exit:
                        if smooth_conf >= self.drift_entry:
                            current_state = "DRIFT"
                        else:
                            current_state = "STABLE"
                            cooldown = self.cooldown_days
            else:
                # During warmup: allow exits from alert states but not new entries.
                if current_state == "DRIFT" and smooth_conf < self.drift_exit:
                    current_state = "STABLE"
                    cooldown = 0
                elif current_state == "SHIFT" and smooth_conf < self.shift_exit:
                    current_state = "STABLE"
                    cooldown = 0

            rows.append(
                {
                    "t": i - 1,
                    "date": dates[i - 1],
                    "state": current_state,
                    "raw_confidence": round(raw_conf, 4),
                    "baseline_confidence": round(baseline_conf, 4),
                    "normalized_confidence": round(normalized_conf, 4),
                    "confidence": round(smooth_conf, 4),
                    "pss": raw["pss"],
                    "horizon": self._horizon(current_state, raw["pss"]),
                    "action": STATE_ACTIONS[current_state],
                    "evidence": raw["evidence"],
                    "drift_run": drift_run,
                    "shift_run": shift_run,
                    "cooldown": cooldown,
                    "prev_state": prev_state,
                }
            )

            raw_hist.append(raw_conf)
            output_row += 1

        return pd.DataFrame(rows)


class StabilizedDemandDetectorV44(StabilizedDemandDetectorV43):
    """V4.4 detector (V4.4b calibration) – recommended experimental variant.

    V4.4 keeps V4.3's normalized-score design (lower-quantile baseline,
    warmup suppression, and longer cooldown) and applies a stricter
    state-machine calibration motivated by exploratory checks on sampled
    real M5 retail item/store daily demand series.

    Default calibration deltas vs V4.3:

    * ``drift_entry`` = 0.42 (was 0.38)
    * ``drift_confirm_days`` = 3 (was 2)
    * ``shift_entry`` = 0.68 (was 0.65)
    * ``shift_exit`` = 0.44 (unchanged from V4.3; restated for clarity)

    This M5 work is an external plausibility check only (not a labeled
    benchmark).  THUNBIT remains a research prototype; false-alert calibration
    is still an open problem and this configuration is not production-ready.
    """

    def __init__(
        self,
        window_long: int = 90,
        window_short: int = 21,
        drift_thresh: float = 0.28,
        shift_thresh: float = 0.55,
        smoothing_window: int = 2,
        baseline_window: int = 28,
        baseline_quantile: float = 0.25,
        excess_scale: float = 2.0,
        drift_entry: float = 0.42,
        drift_exit: float = 0.22,
        shift_entry: float = 0.68,
        shift_exit: float = 0.44,
        drift_confirm_days: int = 3,
        shift_confirm_days: int = 1,
        cooldown_days: int = 7,
        warmup_days: int = 28,
    ) -> None:
        super().__init__(
            window_long=window_long,
            window_short=window_short,
            drift_thresh=drift_thresh,
            shift_thresh=shift_thresh,
            smoothing_window=smoothing_window,
            baseline_window=baseline_window,
            baseline_quantile=baseline_quantile,
            excess_scale=excess_scale,
            drift_entry=drift_entry,
            drift_exit=drift_exit,
            shift_entry=shift_entry,
            shift_exit=shift_exit,
            drift_confirm_days=drift_confirm_days,
            shift_confirm_days=shift_confirm_days,
            cooldown_days=cooldown_days,
            warmup_days=warmup_days,
        )
