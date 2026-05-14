# THUNBIT

> **Research prototype.**  THUNBIT is an experimental detector for demand-regime
> instability in daily SKU-level demand series.  It is not a forecasting model,
> not production-ready, and has not been validated on real-world data.

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
from thunbit import StabilizedDemandDetectorV43

# Your daily demand series.
# window_long + window_short = 111 observations are consumed before the first
# output row is produced; provide more data for meaningful detection results.
demand = np.array([...])

det = StabilizedDemandDetectorV43()
result = det.detect_rolling_stabilized(demand)
print(result[["t", "state", "confidence", "action"]].tail(10))
```

---

## Project layout

```
thunbit/            Python package
  detector.py       Baseline DemandStateDetector (no state machine)
  stabilized.py     Stabilized variants: V4, V4.1, V4.2, V4.3
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

**V4.2 and V4.3** go further by normalizing the raw score against a rolling
baseline of the SKU's own recent confidence values, producing a
*relative-to-own-noise* signal.  Benchmarks showed this is the key mechanism
for reducing false alerts on stable series.  V4.3 uses a 25th-percentile
(lower-quantile) baseline over a longer window, plus warmup suppression, to
recover break detection responsiveness lost in V4.2.

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
| V4.3 (current) | Lower-quantile baseline + warmup | ~11% | Best current tradeoff |

**V4.1 vs V4.2 – stable-series false alerts:**

| Metric | Old baseline | V4.1 | V4.2 |
|--------|:------------:|:----:|:----:|
| `any_alert_rate` | 1.00 | 1.00 | **0.60** |
| `mean_alert_days_pct` | 32.4% | 32.0% | **3.2%** |
| `mean_fp_clusters` | 6.3 | 4.7 | **1.0** |

V4.2 confirmed that **baseline-normalized scoring is the right design direction**
for reducing false-alert burden.  However, it roughly tripled detection delay on
cycle-break, gradual-drift, and intermittent scenarios.

**V4.3** recovered much of that lost responsiveness by using a lower-quantile
(25th-percentile) rolling baseline and warmup suppression.  It is the current
best experimental operating point.  **V4.3 does not solve the stable-series
false-alert problem.**  Every stable seed still receives some alerts.  Score
calibration remains an active open problem.

See [docs/benchmarking.md](docs/benchmarking.md) for the full iteration history
and quantitative tables.

---

## Current status

| Item | Status |
|------|--------|
| Core detector and state machine | ✅ implemented |
| V4.3 as recommended experimental detector | ✅ baseline-normalized variant |
| Synthetic benchmark (old vs. V4 vs. V4.1) | ✅ complete |
| V4.2 score-normalization benchmark | ✅ complete |
| V4.3 qualitative assessment | ✅ complete |
| Benchmark and walkthrough notebooks | ✅ committed (`notebooks/`) |
| Reproducibility documentation | ✅ see `docs/reproducibility.md` |
| Stable-series false-alert calibration | ❌ open problem (improved but unsolved) |
| Real-data validation | ❌ not started |
| Automated parameter tuning | ❌ not started |

---

## Known limitations

- Stable-series false alerts are reduced by V4.2/V4.3 but **not eliminated**.
  Score calibration remains the central open challenge.
- All benchmarks are simulated; no real-SKU data has been tested.
- Detection delay on gradual-drift and intermittent demand is higher than the
  baseline at V4+ settings.
- Parameter calibration was manual; no automated tuning is included.

See [docs/limitations.md](docs/limitations.md) for the full list.

---

## Roadmap

- [ ] Quantitative V4.3 benchmark across all six scenarios and 10 seeds
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
