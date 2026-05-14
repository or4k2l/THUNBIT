# THUNBIT

> **Research prototype.**  THUNBIT is an experimental detector for demand-regime
> instability in daily SKU-level demand series.  It is not a forecasting model,
> not production-ready, and has not been formally validated on real-world data.

THUNBIT is a research prototype for detecting when daily demand has stopped
behaving like the pattern an inventory or forecasting workflow implicitly relies
on.  It combines three statistical evidence channels into a single confidence
score and maps it to an operational state signal:

| State  | Meaning |
|--------|---------|
| **STABLE** | No meaningful evidence of distributional change. |
| **DRIFT**  | Sustained moderate evidence of change; review recommended. |
| **SHIFT**  | Sustained strong evidence of a structural break. |

---

## What THUNBIT is

- A **demand-regime change indicator** that tells you *something has changed*
  (or *nothing has changed*).
- A **research tool** for exploring detection trade-offs across simulated
  demand scenarios.
- A **Python package** you can import and run on a demand array in a few lines
  of code.

## What THUNBIT is not

- A **forecasting model**.  It produces no demand forecasts, safety-stock
  levels, or reorder-point recommendations.
- A **validated production system**.  All benchmark results are from synthetic
  data; real-SKU behaviour is unknown.
- A **solved problem**.  False alerts on stable series are a known open
  limitation (see [docs/limitations.md](docs/limitations.md)).

---

## Quick start

```bash
pip install -e .          # install from repo root
python examples/basic_usage.py
```

Or open the walkthrough notebook:

```bash
pip install -e ".[dev]"   # includes jupyter
jupyter notebook notebooks/01_detector_walkthrough.ipynb
```

Or directly in Python:

```python
import numpy as np
from thunbit import StabilizedDemandDetectorV44

# Your daily demand series.
# window_long + window_short = 111 observations are consumed before the first
# output row is produced; provide more data for meaningful detection results.
demand = np.array([...])

det = StabilizedDemandDetectorV44()
result = det.detect_rolling_stabilized(demand)
print(result[["t", "state", "confidence", "action"]].tail(10))
```

---

## Project layout

```
thunbit/            Python package
  detector.py       Baseline DemandStateDetector (no state machine)
  stabilized.py     Stabilized variants: V4, V4.1, V4.2, V4.3, V4.4
  _states.py        State constants

examples/
  basic_usage.py    Runnable end-to-end example (synthetic data)

notebooks/
  01_detector_walkthrough.ipynb    Import, run, and inspect all detector variants
  02_benchmark_iterations.ipynb   Reproducible benchmark across synthetic scenarios
  03_cost_simulation.ipynb        Illustrative cost framing (directional only)

docs/
  methodology.md      How the detector works
  benchmarking.md     Simulation results and iteration history
  limitations.md      Known open problems
  reproducibility.md  How to install, run, and reproduce results

data/               Placeholder for data files (currently synthetic only)
tests/              Lightweight unit tests
```

---

## Methodology overview

Three statistical evidence channels are combined:

1. **Distribution change** – two-sample KS statistic between a long reference
   window and a short current window.
2. **Volatility change** – normalised absolute variance change between windows.
3. **Weekly-pattern instability** – change in lag-7 autocorrelation between
   windows.

A weighted combination of the maximum and mean evidence values forms a
`raw_confidence` score (0–1).  The stabilized variants layer a state machine
(hysteresis + smoothing + confirmation + cooldown) on top of this score to
reduce noisy state flickering.

**V4.2, V4.3, and V4.4** go further by normalizing the raw score against a rolling
baseline of the SKU's own recent confidence values, producing a
*relative-to-own-noise* signal.  Benchmarks showed this is the key mechanism
for reducing false alerts on stable series.  V4.3 introduced the 25th-percentile
(lower-quantile) baseline over a longer window plus warmup suppression.
V4.4 (the V4.4b calibration) keeps that normalized-score design and applies a
stricter state-machine calibration.

See [docs/methodology.md](docs/methodology.md) for full details.

---

## Benchmark summary

> All results are from synthetic demand simulations across 10 random seeds.
> They are exploratory findings, not validated performance claims.

**Iteration path:**

| Version | Key change | Stable `mean_alert_days_pct` | Notes |
|---------|-----------|:---------------------------:|-------|
| Old baseline | No state machine | 32.4% | Fast but noisy |
| V4 | Hysteresis + smoothing + confirmation | 27.5% | Adds detection delay |
| V4.1 | Cooldown, relaxed thresholds | 32.0% | Recovers some speed vs V4 |
| V4.2 | Baseline-normalized scoring (median) | **3.2%** | Major improvement; over-damped on breaks |
| V4.3 | Lower-quantile baseline + warmup | ~10.6% | Historical comparison point; more responsive |
| V4.4 (current, V4.4b calibration) | V4.3 normalized score + stricter state calibration | **~7.8%** | Current recommended conservative experimental operating point |

**V4.1 vs V4.2 – stable-series false alerts:**

| Metric | Old baseline | V4.1 | V4.2 |
|--------|:------------:|:----:|:----:|
| `any_alert_rate` | 1.00 | 1.00 | **0.60** |
| `mean_alert_days_pct` | 32.4% | 32.0% | **3.2%** |
| `mean_fp_clusters` | 6.3 | 4.7 | **1.0** |

V4.2 confirmed that **baseline-normalized scoring is the right design direction**
for reducing false-alert burden.  However, it roughly tripled detection delay on
cycle-break, gradual-drift, and intermittent scenarios.

**V4.4** is now the recommended experimental operating point for a **quieter /
more conservative alerting posture**.  It keeps V4.3's lower-quantile
normalized-score design and uses stricter state-machine calibration (V4.4b):
`drift_entry=0.42`, `drift_confirm_days=3`, `shift_entry=0.68`,
`shift_confirm_days=1`.

A completed synthetic benchmark comparison (all six scenarios, 10 seeds each)
shows that V4.4 is a more conservative operating point, not a universally
superior detector:

- V4.4 reduces stable-series alert burden (~7.8% alert days vs ~10.6% for V4.3)
  and false-positive clustering (mean 2.4 FP clusters vs 3.6).
- V4.4 also reduces break-detection sensitivity and increases mean detection
  delay across synthetic scenarios, especially for `cycle_break` (detection
  rate 0.70 vs 0.90; mean days late 47.3 vs 17.8).

V4.3 remains the more responsive historical comparison point and should be
preferred when faster synthetic break detection is the priority.

The V4.4b choice was motivated by exploratory checks on sampled real M5 retail
item/store daily demand series, where alert burden dropped relative to V4.3
with a similar qualitative plausibility profile.  Exploratory M5 plausibility
checks support the preference for a quieter operating point but do not override
the synthetic tradeoff story.  This is an external plausibility check only,
**not** a labeled benchmark or production validation.
False-alert calibration remains an active open problem.

See [docs/benchmarking.md](docs/benchmarking.md) for the full iteration history
and quantitative tables.

---

## Current status

| Item | Status |
|------|--------|
| Core detector and state machine | ✅ implemented |
| V4.4 as recommended experimental detector | ✅ V4.4b calibration on V4.3 normalized-score design |
| Synthetic benchmark (old vs. V4 vs. V4.1) | ✅ complete |
| V4.2 score-normalization benchmark | ✅ complete |
| V4.3 + V4.4 synthetic benchmark (direct comparison) | ✅ complete — see `docs/benchmarking.md` |
| Benchmark and walkthrough notebooks | ✅ committed (`notebooks/`) |
| Reproducibility documentation | ✅ see `docs/reproducibility.md` |
| Stable-series false-alert calibration | ❌ open problem (improved but unsolved) |
| Real-data checks | ⚠️ exploratory sampled-M5 plausibility checks only (no formal validation) |
| Automated parameter tuning | ❌ not started |

---

## Known limitations

- Stable-series false alerts are reduced by V4.2/V4.3/V4.4 but **not eliminated**.
  Score calibration remains the central open challenge.
- Synthetic benchmarking remains the quantitative core; sampled M5 checks are
  exploratory plausibility work only (not formal validation).
- Detection delay on gradual-drift and intermittent demand is higher than the
  baseline at V4+ settings.
- Parameter calibration was manual; no automated tuning is included.

See [docs/limitations.md](docs/limitations.md) for the full list.

---

## Roadmap

- [x] ~~Quantitative V4.4 benchmark across all six scenarios and 10 seeds~~ (complete — see `docs/benchmarking.md`)
- [ ] Investigate lower-quantile baseline parameter sensitivity
      (quantile level, window length, excess scale)
- [ ] Automated parameter sweep over stable / drift / shift trade-off space
- [ ] Test on anonymised real SKU demand data
- [ ] Document business-cost simulation methodology

---

## Requirements

- Python ≥ 3.9
- numpy ≥ 1.22
- pandas ≥ 1.4
- scipy ≥ 1.8

---

## License

Apache 2.0 – see [LICENSE](LICENSE).
