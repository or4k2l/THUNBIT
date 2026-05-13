# Benchmarking

This document summarises the simulation-based benchmarking work carried out
during THUNBIT development.

All results are from **synthetic demand series**.  They should be treated as
exploratory findings that motivated the design of each detector variant, not
as validated performance guarantees.

---

## 1. Benchmark setup

### Scenarios

Six scenario types were simulated, each across 10 random seeds:

| Scenario         | Description                                                      |
|------------------|------------------------------------------------------------------|
| `stable`         | Stationary AR(1)-like demand; no injected break                  |
| `mean_shift`     | Demand mean increases by 40% at a fixed break day                |
| `gradual_drift`  | Demand mean decays by 25% gradually over ~60 days                |
| `variance_spike` | Demand variance multiplied by 7× at a fixed break day            |
| `cycle_break`    | Weekly seasonality amplitude collapses to zero at a break day    |
| `intermittent`   | ~35% of daily observations are zero; break at a fixed day        |

### Metrics

For the **stable** scenario (no break):
* `any_alert_rate` – fraction of seeds on which the detector ever fires
* `mean_alert_days_pct` – mean percentage of days spent in a non-STABLE state
* `mean_fp_clusters` – mean number of distinct false-alert clusters

For **break** scenarios:
* `detection_rate` – fraction of seeds where the break was eventually detected
* `mean_days_late` – mean days between break day and first sustained alert
* `mean_fp_clusters` – mean false-alert clusters before the break

Sustained detection: requires the detector to stay in DRIFT or SHIFT for at
least 3 consecutive days.

---

## 2. Iteration history

### Old (baseline, no state machine)

The original `DemandStateDetector` uses direct threshold comparison with no
smoothing or state machine.  It is fast to respond but produces a high rate
of fragmented alert clusters on stable series.

| Scenario        | Detection rate | Mean days late | Mean FP clusters |
|-----------------|:--------------:|:--------------:|:----------------:|
| cycle_break     | 1.00           | 10.3           | 3.0              |
| gradual_drift   | 1.00           | 10.1           | 3.0              |
| intermittent    | 0.90           | 12.3           | 2.0              |
| mean_shift      | 1.00           | 1.2            | 3.0              |
| variance_spike  | 1.00           | 0.5            | 3.0              |

On the stable scenario (no break):
* `any_alert_rate` = 1.00 (alerts fired on every seed)
* `mean_alert_days_pct` = 32.4%
* `mean_fp_clusters` = 6.3

---

### V4 (first stabilized variant)

V4 added a state machine with hysteresis, smoothing, and confirmation.  This
roughly halved the number of false-alert clusters on stable series, but
introduced meaningful detection delay on gradual-drift and intermittent
scenarios.

| Scenario        | Detection rate | Mean days late | Mean FP clusters |
|-----------------|:--------------:|:--------------:|:----------------:|
| cycle_break     | 1.00           | 12.6           | 1.7              |
| gradual_drift   | 1.00           | 17.2           | 1.7              |
| intermittent    | 0.90           | 35.4           | 1.1              |
| mean_shift      | 1.00           | 3.1            | 1.7              |
| variance_spike  | 1.00           | 2.0            | 1.7              |

On the stable scenario:
* `any_alert_rate` = 1.00 (still fires on every seed)
* `mean_alert_days_pct` = 27.5%
* `mean_fp_clusters` = 3.1

**Assessment:** V4 reduces noise but is over-damped.  The stable false-alert
problem is not solved; and the delay cost on gradual-drift and intermittent
demand is considered too high for the noise reduction achieved.

---

### V4.1

V4.1 relaxed the confirmation thresholds and added a cooldown mechanism to
suppress fragmented re-alert clusters after a state returns to STABLE.  Key
parameter changes from V4:

* `drift_confirm_days`: 3 → 2
* `shift_confirm_days`: 2 → 1
* `drift_entry`: 0.32 → 0.30
* `smoothing_window`: 3 → 2
* Added `cooldown_days = 5`

V4.1 was intended to recover some of the detection speed lost in V4 while
maintaining lower cluster counts.  Full benchmark results for V4.1 were not
completed in the initial iteration.

---

### V4.3 – current best experimental operating point

V4.3 is the result of further manual calibration of V4.1 parameters.
It raises `drift_entry` back to 0.32 (to control stable-series alerts more
firmly), tightens `drift_exit` to 0.22, and extends `cooldown_days` to 7.

V4.3 represents the **current best compromise** seen so far between:
* reducing stable-series false-alert clusters
* maintaining acceptable detection delay

**V4.3 does not solve the stable-series false-alert problem.**  Every stable
seed still receives some alerts.  False-alert calibration remains an open
research problem for this prototype.

---

## 3. Observed trade-off summary

The core tension in this design is:

> More suppression → fewer stable-series false clusters → more delay on real breaks.

No configuration tested so far achieves both zero stable-series false alerts
and fast detection.  This is consistent with the inherent difficulty of the
problem: in the absence of ground-truth labels on real data, distinguishing
noise from a genuine early regime change is fundamentally ambiguous.

---

## 4. Business-cost context

A preliminary cost simulation suggested that alert value (net of cost of
unnecessary review) becomes positive when stockout costs materially exceed
overstock costs.  This result was directional only and depends heavily on
assumptions about review cost and demand volatility.  It should not be
interpreted as a demonstration of production value.

---

## 5. What was not benchmarked

* Real-world SKU data
* Demand series with strong trend or multiple seasonalities
* Very short series (< 200 days)
* Multi-item or hierarchical demand
* Sensitivity to the specific simulation parameters chosen
