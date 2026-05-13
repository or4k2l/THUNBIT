"""
thunbit.stabilized
~~~~~~~~~~~~~~~~~~
Stabilized demand-state detector variants.

This module provides three progressively refined detectors that add a state
machine on top of the raw confidence score produced by ``DemandStateDetector``:

* ``StabilizedDemandDetector``   – V4: hysteresis + smoothing + confirmation
* ``StabilizedDemandDetectorV41`` – V4.1: adds cooldown, relaxed thresholds
* ``StabilizedDemandDetectorV43`` – V4.3: current best experimental operating
  point; longer cooldown, slightly more conservative drift entry

All three are **experimental**.  Stable-series false-alert rates remain an
active calibration problem.  See ``docs/benchmarking.md`` and
``docs/limitations.md`` for observed trade-offs.

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


class StabilizedDemandDetectorV43(StabilizedDemandDetectorV41):
    """V4.3 detector – current best experimental operating point.

    V4.3 is the result of iterative calibration across synthetic benchmark
    scenarios (see ``docs/benchmarking.md``).  Relative to V4.1 it uses:

    * Slightly higher ``drift_entry`` (V4.3 default: 0.32 vs. V4.1: 0.30)
      to further reduce false alert clusters on stable series.
    * Longer ``cooldown_days`` (V4.3 default: 7 vs. V4.1: 5) to suppress
      fragmented re-alerts after a quiet period.
    * Tighter ``drift_exit`` (V4.3 default: 0.22 vs. V4.1: 0.24) to keep
      DRIFT states from persisting too long on marginal evidence.

    **Important caveats:**

    * Even V4.3 produces false alerts on every synthetic stable series tested.
      Alert-rate reduction (vs. V4) is meaningful but the problem is unsolved.
    * Detection delay on intermittent and gradual-drift scenarios is higher
      than the no-state-machine baseline.
    * These parameters were tuned on simulated data; behaviour on real SKU
      data is unknown.
    * V4.3 should be treated as the current best experimental tradeoff, not a
      finalised or production-ready configuration.

    Parameters
    ----------
    All parameters have new defaults reflecting the V4.3 calibration.
    They can still be overridden for experimentation.
    """

    def __init__(
        self,
        window_long: int = 90,
        window_short: int = 21,
        drift_thresh: float = 0.28,
        shift_thresh: float = 0.55,
        smoothing_window: int = 2,
        drift_entry: float = 0.32,
        drift_exit: float = 0.22,
        shift_entry: float = 0.58,
        shift_exit: float = 0.46,
        drift_confirm_days: int = 2,
        shift_confirm_days: int = 1,
        cooldown_days: int = 7,
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
