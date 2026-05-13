"""
thunbit.detector
~~~~~~~~~~~~~~~~
Baseline demand-regime instability detector.

The DemandStateDetector combines three evidence channels into a single
confidence score and maps it to an operational state: STABLE / DRIFT / SHIFT.

This is intentionally the simplest working version – no state machine, no
hysteresis.  It serves as the comparison baseline for the stabilized variants.

Research prototype – not validated for production use.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

from ._states import STATE_ACTIONS


class DemandStateDetector:
    """Baseline demand-state detector.

    Combines three statistical evidence channels:

    * **distribution** – two-sample KS statistic between the reference window
      and the current window.  Measures overall distributional shift.
    * **volatility** – normalised absolute change in variance between windows.
      Measures scale instability.
    * **cycle_7d** – change in lag-7 autocorrelation between windows.
      Measures weekly-pattern instability.

    The combined confidence score is a weighted average of the maximum and mean
    evidence values.  A simple threshold rule maps the score to a state.

    Parameters
    ----------
    window_long : int
        Length of the historical reference window (days).
    window_short : int
        Length of the recent observation window (days).
    drift_thresh : float
        Confidence threshold for declaring DRIFT.
    shift_thresh : float
        Confidence threshold for declaring SHIFT.

    Notes
    -----
    * Requires ``window_long + window_short`` observations before producing
      a meaningful result.
    * The detector has no state machine: each timestep is classified
      independently.  This can cause noisy, flickering state transitions on
      borderline series.  See ``StabilizedDemandDetector`` for a version that
      addresses this.
    """

    def __init__(
        self,
        window_long: int = 90,
        window_short: int = 21,
        drift_thresh: float = 0.28,
        shift_thresh: float = 0.55,
    ) -> None:
        self.window_long = window_long
        self.window_short = window_short
        self.drift_thresh = drift_thresh
        self.shift_thresh = shift_thresh

    # ------------------------------------------------------------------
    # Evidence primitives
    # ------------------------------------------------------------------

    def _ks_evidence(self, ref: np.ndarray, cur: np.ndarray) -> float:
        """KS statistic between reference and current window (0–1)."""
        if len(ref) < 3 or len(cur) < 3:
            return 0.0
        stat, _ = ks_2samp(ref, cur)
        return float(stat)

    def _variance_evidence(self, ref: np.ndarray, cur: np.ndarray) -> float:
        """Normalised absolute variance change between windows (0–1)."""
        var_ref = float(np.var(ref))
        var_cur = float(np.var(cur))
        if var_ref <= 0 and var_cur <= 0:
            return 0.0
        denom = max(var_ref, var_cur, 1e-8)
        return float(min(abs(var_cur - var_ref) / denom, 1.0))

    def _acf_evidence(
        self, ref: np.ndarray, cur: np.ndarray, scale: int = 7
    ) -> float:
        """Absolute change in lag-*scale* autocorrelation between windows (0–1)."""

        def _acf_at_lag(x: np.ndarray, lag: int) -> float:
            if len(x) <= lag:
                return 0.0
            c = np.corrcoef(x[:-lag], x[lag:])[0, 1]
            return 0.0 if np.isnan(c) else float(c)

        acf_ref = _acf_at_lag(ref, scale)
        acf_cur = _acf_at_lag(cur, scale)
        return float(min(abs(acf_cur - acf_ref), 1.0))

    # ------------------------------------------------------------------
    # Derived scores
    # ------------------------------------------------------------------

    def _pss(self, series: np.ndarray) -> float:
        """Pattern Stability Score – heuristic planability measure (0–100).

        Based on the coefficient of variation of recent demand.  A CV near 1
        (typical for noisy demand) maps to PSS ≈ 50.  Very smooth series score
        higher; intermittent or erratic series score lower.
        """
        if len(series) < 2:
            return 50.0
        mean_val = float(np.mean(np.abs(series)))
        if mean_val < 1e-8:
            return 0.0
        cv = float(np.std(series)) / mean_val
        pss = 100.0 / (1.0 + cv)
        return float(min(100.0, max(0.0, round(pss, 2))))

    def _horizon(self, state: str, pss: float) -> float:
        """Heuristic planning horizon (days) implied by the current state.

        Returns the PSS value directly for STABLE (typical ≈ 50 days), and
        progressively shorter horizons for DRIFT and SHIFT.
        """
        if state == "STABLE":
            return float(pss)
        elif state == "DRIFT":
            return round(float(pss * 0.5), 1)
        else:  # SHIFT
            return round(float(pss * 0.25), 1)

    # ------------------------------------------------------------------
    # Core detection
    # ------------------------------------------------------------------

    def detect_raw(self, series: np.ndarray) -> dict:
        """Compute a single-point confidence score from the tail of *series*.

        Parameters
        ----------
        series : array-like
            Full demand history up to and including the current timestep.

        Returns
        -------
        dict with keys ``raw_confidence``, ``pss``, ``evidence``.
        """
        s = np.asarray(series, dtype=float)

        if len(s) < self.window_long + self.window_short:
            return {"raw_confidence": 0.0, "pss": 50.0, "evidence": {}}

        s_ref = s[-(self.window_long + self.window_short) : -self.window_short]
        s_cur = s[-self.window_short :]

        evidence = {
            "distribution": self._ks_evidence(s_ref, s_cur),
            "volatility": self._variance_evidence(s_ref, s_cur),
            "cycle_7d": self._acf_evidence(s_ref, s_cur, scale=7),
        }

        vals = list(evidence.values())
        max_ev = max(vals)
        mean_ev = float(np.mean(vals))
        raw_conf = 0.4 * max_ev + 0.6 * mean_ev

        pss = self._pss(s_cur)
        # Low PSS (intermittent / erratic demand) slightly inflates the score.
        pss_penalty = max(0.0, (50.0 - pss) / 100.0)
        raw_conf = float(min(raw_conf + pss_penalty * 0.4, 1.0))

        return {
            "raw_confidence": float(raw_conf),
            "pss": pss,
            "evidence": {k: round(v, 4) for k, v in evidence.items()},
        }

    def detect_rolling(
        self,
        series: np.ndarray,
        dates=None,
        step: int = 1,
    ) -> pd.DataFrame:
        """Run the detector across an expanding window over *series*.

        Parameters
        ----------
        series : array-like
            Full demand history.
        dates : array-like, optional
            Date labels for each observation.  Defaults to integer indices.
        step : int
            Step size between evaluations.

        Returns
        -------
        pd.DataFrame
            One row per evaluated timestep with columns: ``t``, ``date``,
            ``state``, ``raw_confidence``, ``confidence``, ``pss``,
            ``horizon``, ``action``, ``evidence``.
        """
        s = np.asarray(series, dtype=float)
        if dates is None:
            dates = np.arange(len(s))

        start = self.window_long + self.window_short
        rows = []

        for i in range(start, len(s) + 1, step):
            raw = self.detect_raw(s[:i])
            conf = raw["raw_confidence"]

            if conf >= self.shift_thresh:
                state = "SHIFT"
            elif conf >= self.drift_thresh:
                state = "DRIFT"
            else:
                state = "STABLE"

            rows.append(
                {
                    "t": i - 1,
                    "date": dates[i - 1],
                    "state": state,
                    "raw_confidence": round(conf, 4),
                    "confidence": round(conf, 4),
                    "pss": raw["pss"],
                    "horizon": self._horizon(state, raw["pss"]),
                    "action": STATE_ACTIONS[state],
                    "evidence": raw["evidence"],
                }
            )

        return pd.DataFrame(rows)
