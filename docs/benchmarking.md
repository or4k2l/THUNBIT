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

V4.1 partially recovered detection speed relative to V4.  It improved the
operational tradeoff on break scenarios, reducing cluster counts while
avoiding some of the worst delays that V4 introduced.

| Scenario        | Detection rate | Mean days late | Mean FP clusters |
|-----------------|:--------------:|:--------------:|:----------------:|
| cycle_break     | 1.00           | 11.4           | 2.4              |
| gradual_drift   | 1.00           | 12.0           | 2.4              |
| intermittent    | 0.90           | 14.3           | 1.3              |
| mean_shift      | 1.00           | 2.7            | 2.4              |
| variance_spike  | 1.00           | 1.3            | 2.4              |

On the stable scenario:
* `any_alert_rate` = 1.00 (still fires on every seed)
* `mean_alert_days_pct` = 32.0%
* `mean_fp_clusters` = 4.7

**Assessment:** V4.1 improved the operational tradeoff versus V4 by recovering
some detection speed.  However, stable-series alert burden remained essentially
unchanged from the baseline.  This indicated that the core problem is not in
the state-transition logic but in the **raw confidence score itself**, which
carries a systematic positive bias on stationary series.

---

### V4.2 – score normalization breakthrough (over-damped)

V4.2 introduced a fundamentally different approach: instead of filtering noisy
transitions with a state machine, it attacked the score directly.  The raw
confidence score is measured *above the SKU's own recent baseline*:

```
excess_confidence = max(0, raw_conf - rolling_median(raw_conf)) * excess_scale
```

This converts an absolute score into a relative-to-own-noise signal, which
is conceptually much better suited to the problem.

**V4.2 stable-series results** (10 seeds, synthetic data):

| Metric                | Old baseline | V4.1   | V4.2   |
|-----------------------|:------------:|:------:|:------:|
| `any_alert_rate`      | 1.00         | 1.00   | **0.60** |
| `mean_alert_days_pct` | 32.4%        | 32.0%  | **3.2%** |
| `mean_fp_clusters`    | 6.3          | 4.7    | **1.0**  |

V4.2 drastically reduced stable-series alert burden, confirming that
**baseline-normalized scoring is the right design direction**.

**V4.2 break-scenario results** (10 seeds, synthetic data):

| Scenario        | Detection rate | Mean days late | Mean FP clusters |
|-----------------|:--------------:|:--------------:|:----------------:|
| cycle_break     | 0.90           | 33.7           | 0.4              |
| gradual_drift   | 1.00           | 37.5           | 0.4              |
| intermittent    | 0.50           | 45.6           | 0.6              |
| mean_shift      | 1.00           | 4.0            | 0.4              |
| variance_spike  | 1.00           | 2.0            | 0.4              |

**Assessment:** V4.2 demonstrated the breakthrough that score normalization
dramatically reduces stable-series false alerts.  However, it imposed too much
delay on cycle-break, gradual-drift, and intermittent scenarios – roughly
tripling detection lag compared with V4.1.  Intermittent detection rate dropped
to 0.50.  V4.2 is therefore kept as a historical reference, not the recommended
operating point.

---

### V4.3 – lower-quantile + warmup improvement step

V4.3 builds on V4.2's score-normalization concept and recovers much of the
detection responsiveness that V4.2 sacrificed.  Key changes from V4.2:

* **Lower-quantile baseline** – the rolling 25th-percentile of recent raw
  confidence replaces the rolling median.  The lower quantile stays nearer
  the true noise floor and adapts more slowly when a genuine break raises
  the score, so break signals are less likely to be cancelled by a rising
  baseline.
* **Longer baseline window** – 28 days (vs. 21 in V4.2) for a slower,
  more stable baseline estimate.
* **Warmup suppression** – state changes from STABLE are suppressed for the
  first 28 output rows, preventing early false alerts while the baseline
  window fills up.
* **Tuned thresholds** – entry thresholds recalibrated against the higher
  typical normalized scores produced by the lower-quantile baseline.
* **Longer cooldown** – 7 days (vs. 5 in V4.2) after returning to STABLE.

**Qualitative assessment** (synthetic data):

* V4.3 reduced stable-series alert burden meaningfully compared with V4.1,
  though not to the level of V4.2.
* V4.3 recovered a large portion of the detection responsiveness lost in
  V4.2: break detection delays on gradual-drift, cycle-break, and
  intermittent scenarios are substantially shorter than V4.2's.
* V4.3 was the first strong compromise between stable-series false-alert
  control and break detection speed.

**V4.3 is not production-ready.**  Stable-series false alerts remain an open
calibration problem.  Score normalization is now confirmed as the right
direction, but the precise quantile, window length, and threshold settings
have not been validated beyond these synthetic experiments.

---

### V4.4 (V4.4b calibration) – current recommended conservative experimental operating point

V4.4 keeps V4.3's normalized-score structure (25th-percentile baseline,
28-day baseline window, warmup suppression, cooldown) and changes only the
state-machine calibration:

* `drift_entry`: `0.38 → 0.42`
* `drift_confirm_days`: `2 → 3`
* `shift_entry`: `0.65 → 0.68`
* `shift_confirm_days`: `1 → 1` (unchanged)

The V4.4b calibration was selected from exploratory follow-up checks on sampled
real M5 retail item/store daily demand series.  In that exploratory setting, it
reduced alert burden relative to V4.3 while retaining a similar qualitative
plausibility profile.

This is an external plausibility check only.  It is **not** a formal labeled
benchmark and does **not** establish production readiness or real-world
validation.  The false-alert calibration problem remains open.

#### Synthetic benchmark: V4.3 vs V4.4

A direct synthetic benchmark comparison between V4.3 and V4.4 was completed
across all six scenarios and 10 random seeds.  The results show that V4.4 is
a **more conservative operating point**, not a detector that is simply or
universally better than V4.3.

**Stable-series (no break):**

| Metric | V4.3 | V4.4 |
|--------|:----:|:----:|
| `any_alert_rate` | 1.00 | 1.00 |
| `mean_alert_days_pct` | 10.6% | **7.8%** |
| `mean_fp_clusters` | 3.6 | **2.4** |

V4.4 reduces stable-series alert burden and false-positive clustering
relative to V4.3.

**Break-scenario summary (all break scenarios, 10 seeds each):**

| Metric | V4.3 | V4.4 |
|--------|:----:|:----:|
| `break_detection_rate` | **0.98** | 0.92 |
| `break_mean_days_late` | **14.8** | 21.0 |
| `break_mean_alert_days_pct` | 12.2% | **8.6%** |
| `break_mean_fp_clusters` | 3.18 | **1.98** |

V4.4 also reduces break-period alert burden and false-positive clustering,
but it reduces detection sensitivity and increases mean detection delay.

**Scenario-specific break results:**

| Scenario | Detector | Detection rate | Mean days late | Mean FP clusters |
|----------|----------|:--------------:|:--------------:|:----------------:|
| `mean_shift` | V4.3 | 1.00 | **3.7** | 3.1 |
| `mean_shift` | V4.4 | 1.00 | 9.9 | **2.1** |
| `variance_spike` | V4.3 | 1.00 | **6.5** | 3.5 |
| `variance_spike` | V4.4 | 1.00 | 7.5 | **2.2** |
| `gradual_drift` | V4.3 | **1.00** | **43.5** | 3.1 |
| `gradual_drift` | V4.4 | 0.90 | 46.7 | **2.0** |
| `cycle_break` | V4.3 | **0.90** | **17.8** | 2.5 |
| `cycle_break` | V4.4 | 0.70 | 47.3 | **1.4** |
| `intermittent` | V4.3 | 1.00 | **3.0** | 3.7 |
| `intermittent` | V4.4 | 1.00 | 4.1 | **2.2** |

The most important qualitative result: V4.4 is quieter than V4.3, but this
is paid for by slower and occasionally weaker synthetic break detection,
**especially on `cycle_break`** (detection rate drops from 0.90 to 0.70;
mean days late rises from 17.8 to 47.3).

Relative to V4.3, V4.4 reduces stable-series alert burden and false-positive
clustering, but this comes with slower and occasionally weaker break detection
on synthetic scenarios, especially for cycle-break cases.

V4.4 can remain the recommended experimental operating point for applications
where a quieter / more conservative alerting posture is preferred.  The
exploratory sampled-M5 plausibility checks provide an additional external
motivation for this quieter calibration.  However, V4.3 remains the more
responsive historical comparison point and should be considered when faster
synthetic break detection is the priority.

---

## 3. Observed trade-off summary

The core tension in this design is:

> More suppression → fewer stable-series false clusters → more delay on real breaks.

V4.2 showed that moving from state-machine filtering to score normalization
is the right approach.  V4.3 demonstrated that the lower-quantile baseline
provides a better operating point than the median baseline.  V4.4 (V4.4b)
adds stricter state-machine calibration that further reduces alert burden at
the cost of detection responsiveness — most notably on cycle-break scenarios.
Still, no configuration tested so far achieves both low stable-series false
alerts and fast break detection simultaneously.

This is consistent with the inherent difficulty of the problem: in the
absence of ground-truth labels on real data, distinguishing noise from a
genuine early regime change is fundamentally ambiguous.

**Key learning:** score calibration – not state-transition logic – is the
central design challenge.

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
* Automated parameter tuning or cross-validation
