"""
basic_usage.py
~~~~~~~~~~~~~~
Minimal runnable example showing how to use THUNBIT detectors on synthetic
demand series.

Run with:
    python examples/basic_usage.py

No external data required – all demand series are generated here.
"""

import numpy as np
import pandas as pd

from thunbit import (
    DemandStateDetector,
    StabilizedDemandDetectorV43,
)


# ---------------------------------------------------------------------------
# 1. Generate two simple synthetic demand series
# ---------------------------------------------------------------------------

rng = np.random.default_rng(42)
N = 400

# Stable series: constant mean, constant noise
stable_series = rng.normal(loc=100.0, scale=10.0, size=N).clip(0)

# Shifted series: demand roughly doubles at day 200
pre_shift = rng.normal(loc=100.0, scale=10.0, size=200).clip(0)
post_shift = rng.normal(loc=180.0, scale=12.0, size=200).clip(0)
shifted_series = np.concatenate([pre_shift, post_shift])


# ---------------------------------------------------------------------------
# 2. Baseline detector (no state machine)
# ---------------------------------------------------------------------------

print("=" * 60)
print("Baseline DemandStateDetector on stable series")
print("=" * 60)

det_base = DemandStateDetector()
result_stable_base = det_base.detect_rolling(stable_series)

state_counts = result_stable_base["state"].value_counts()
print(state_counts.to_string())
print(
    f"\nMean confidence: {result_stable_base['confidence'].mean():.4f}"
    f"  (higher → more instability evidence)"
)


# ---------------------------------------------------------------------------
# 3. V4.3 detector on the mean-shift series
#    V4.3 is the current recommended experimental detector.
#    It uses a lower-quantile rolling baseline to normalize the raw
#    confidence score, reducing false alerts on stable series while
#    preserving break detection responsiveness.
# ---------------------------------------------------------------------------

print()
print("=" * 60)
print("V4.3 detector on mean-shift series (shift at day 200)")
print("=" * 60)

det_v43 = StabilizedDemandDetectorV43()
result_shift_v43 = det_v43.detect_rolling_stabilized(shifted_series)

state_counts_shift = result_shift_v43["state"].value_counts()
print(state_counts_shift.to_string())

# Find first sustained DRIFT or SHIFT after the break
post_break = result_shift_v43[result_shift_v43["t"] >= 200]
alert_days = post_break[post_break["state"].isin(["DRIFT", "SHIFT"])]
if len(alert_days) > 0:
    first_alert = alert_days.iloc[0]
    print(
        f"\nFirst post-break alert: day {first_alert['t']}"
        f"  state={first_alert['state']}"
        f"  confidence={first_alert['confidence']:.4f}"
        f"  (raw={first_alert['raw_confidence']:.4f}"
        f"  baseline={first_alert['baseline_confidence']:.4f}"
        f"  normalized={first_alert['normalized_confidence']:.4f})"
    )
else:
    print("\nNo post-break alert detected.")


# ---------------------------------------------------------------------------
# 4. Show last few rows of the rolling output
# ---------------------------------------------------------------------------

print()
print("=" * 60)
print("Last 5 rows of V4.3 output (mean-shift series)")
print("=" * 60)

display_cols = [
    "t", "state", "raw_confidence", "baseline_confidence",
    "normalized_confidence", "confidence", "pss", "action",
]
print(result_shift_v43[display_cols].tail().to_string(index=False))

print()
print("Done.  See docs/ for methodology and benchmarking details.")
