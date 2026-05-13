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
  stabilized.py     Stabilized variants: V4, V4.1, V4.3
  _states.py        State constants

examples/
  basic_usage.py    Runnable end-to-end example (synthetic data)

docs/
  methodology.md    How the detector works
  benchmarking.md   Simulation results and iteration history
  limitations.md    Known open problems

notebooks/          Benchmark notebooks (planned / in progress)
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
`confidence` score (0–1).  The stabilized variants layer a state machine
(hysteresis + smoothing + confirmation + cooldown) on top of this score to
reduce noisy state flickering.

See [docs/methodology.md](docs/methodology.md) for full details.

---

## Benchmark summary

> All results are from synthetic demand simulations across 10 random seeds.
> They are exploratory findings, not validated performance claims.

**Old baseline (no state machine) vs. V4 (first stabilized variant):**

| Metric | Old baseline | V4 stabilized |
|--------|:------------:|:-------------:|
| Stable – any_alert_rate | 1.00 | 1.00 |
| Stable – mean_alert_days_pct | 32.4% | 27.5% |
| Stable – mean_fp_clusters | 6.3 | 3.1 |
| Mean shift – detection_rate | 1.00 | 1.00 |
| Mean shift – mean_days_late | 1.2 | 3.1 |
| Gradual drift – mean_days_late | 10.1 | 17.2 |
| Intermittent – mean_days_late | 12.3 | 35.4 |

V4 roughly halves false-alert clusters but introduces detection delay, most
severely on intermittent demand.  Subsequent iterations (V4.1, V4.3) attempt
to recover some detection speed via a cooldown mechanism and relaxed
confirmation thresholds.

**V4.3** is the current best experimental operating point: it combines the
reduced-cluster behaviour of V4 with shorter confirmation windows and a longer
cooldown period.  Full quantitative comparison across all versions is ongoing.

---

## Current status

| Item | Status |
|------|--------|
| Core detector and state machine | ✅ implemented |
| V4.3 as recommended experimental detector | ✅ |
| Synthetic benchmark (old vs. V4) | ✅ complete |
| V4.1 / V4.3 full benchmark | 🔄 in progress |
| Stable-series false-alert calibration | ❌ open problem |
| Real-data validation | ❌ not started |
| Notebook cleanup and commit | 🔄 in progress |

---

## Known limitations

- Every synthetic stable series still triggers at least one false alert.
- All benchmarks are simulated; no real-SKU data has been tested.
- Detection delay on gradual-drift and intermittent demand is higher than the
  baseline at V4+ settings.
- Parameter calibration was manual; no automated tuning is included.

See [docs/limitations.md](docs/limitations.md) for the full list.

---

## Roadmap

- [ ] Commit and clean up benchmark notebooks
- [ ] Investigate score normalisation against a rolling quiet-period baseline
      (potential path to reducing stable-series false alerts)
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
