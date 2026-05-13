# Methodology

This document describes how THUNBIT works at a technical level.

THUNBIT is a **research prototype**.  The methodology described here has been
tested on simulated demand series.  Behaviour on real-world SKU data is unknown
and should be validated carefully before drawing any operational conclusions.

---

## 1. Problem framing

Many inventory and forecasting workflows assume implicitly that demand
continues to behave like the historical pattern they were fit on.  When that
assumption breaks – due to a mean shift, a volatility change, or a disruption
to weekly seasonality – the downstream system continues operating on stale
assumptions until a human intervenes or a re-fit cycle runs.

THUNBIT attempts to flag when this assumption has stopped holding.  It does
**not** forecast demand.  It only signals: *something has changed* (or *nothing
has changed*).

---

## 2. States

| State  | Meaning                                                              |
|--------|----------------------------------------------------------------------|
| STABLE | No statistically meaningful evidence of a distributional change.     |
| DRIFT  | Moderate, sustained evidence of change; warranting increased review. |
| SHIFT  | Strong, sustained evidence of a structural break.                    |

The state is re-evaluated at each timestep as new observations arrive.

---

## 3. Evidence channels

The detector combines three independent evidence channels:

### 3.1 Distribution channel (KS statistic)

A two-sample Kolmogorov–Smirnov test is run between the **reference window**
(the most recent `window_long` observations before the current window) and the
**current window** (the most recent `window_short` observations).

The KS statistic (0–1) measures how different the two empirical distributions
are, regardless of the specific type of change.

### 3.2 Volatility channel (normalised variance ratio)

The absolute change in variance between the reference and current windows is
normalised by the maximum of the two variances.  This isolates variance-level
changes that the KS statistic may not emphasise strongly.

### 3.3 Weekly-pattern channel (ACF change)

The change in lag-7 autocorrelation between the reference and current window
is computed.  A large change indicates that the weekly demand cycle has
weakened, strengthened, or disappeared.

---

## 4. Confidence score

The three evidence values are combined into a single `raw_confidence` score:

```
conf = 0.4 × max(evidence) + 0.6 × mean(evidence)
```

The max term amplifies the strongest single signal; the mean term requires
broad agreement across channels.

A PSS (Pattern Stability Score) penalty adjusts the score upward when the
current demand is highly intermittent or erratic (low PSS), reflecting
heightened uncertainty.

---

## 5. PSS (Pattern Stability Score)

PSS is a heuristic 0–100 planability measure based on the coefficient of
variation of the current window:

```
PSS = 100 / (1 + CV)   where CV = std / mean
```

* PSS ≈ 50 for typical noisy demand (CV ≈ 1).
* PSS approaches 100 for very smooth, regular demand.
* PSS approaches 0 for highly erratic or intermittent demand.

PSS is used to set a heuristic planning horizon recommendation and to apply
a small confidence penalty on intermittent series.

---

## 6. State assignment: baseline vs. stabilized

### Baseline (DemandStateDetector)

The raw confidence score is compared directly to two fixed thresholds:

```
conf ≥ shift_thresh  →  SHIFT
conf ≥ drift_thresh  →  DRIFT
otherwise            →  STABLE
```

This is the simplest rule and the comparison baseline.  It is deliberately
not smoothed or hysteresised, which makes it noisy but fast to respond.

### Stabilized (V4, V4.1, V4.3)

The stabilized variants layer a state machine on top of the confidence score:

1. **Smoothing** – raw confidence is averaged over a short rolling window
   to reduce single-day spikes.
2. **Hysteresis** – entry and exit thresholds differ, preventing rapid
   toggling near the boundary.
3. **Confirmation** – a state transition requires the smoothed confidence
   to remain above the entry threshold for a minimum number of consecutive
   days.
4. **Cooldown** (V4.1+) – after returning from an alert state to STABLE,
   re-escalation to DRIFT is suppressed for a fixed number of days.  This
   reduces fragmented repeated alert clusters.

---

## 7. Parameter definitions

| Parameter             | Default (V4.3) | Description                                          |
|-----------------------|:--------------:|------------------------------------------------------|
| `window_long`         | 90             | Length of the reference window (days)                |
| `window_short`        | 21             | Length of the current window (days)                  |
| `smoothing_window`    | 2              | Confidence averaging window                          |
| `drift_entry`         | 0.32           | Smoothed confidence required to enter DRIFT          |
| `drift_exit`          | 0.22           | Smoothed confidence below which DRIFT exits          |
| `shift_entry`         | 0.58           | Smoothed confidence required to enter SHIFT          |
| `shift_exit`          | 0.46           | Smoothed confidence below which SHIFT exits          |
| `drift_confirm_days`  | 2              | Consecutive days above drift_entry to enter DRIFT    |
| `shift_confirm_days`  | 1              | Consecutive days above shift_entry to enter SHIFT    |
| `cooldown_days`       | 7              | Suppression days after returning to STABLE           |

---

## 8. What THUNBIT does not do

* It does not model seasonality or trend explicitly.
* It does not produce demand forecasts.
* It does not output a probability distribution over states.
* It does not adapt its parameters online.
* It has not been benchmarked on real SKU data.
