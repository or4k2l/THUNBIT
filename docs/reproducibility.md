# Reproducibility Guide

> **Research prototype.**  This document describes what is and is not
> reproducible from this repository alone.  Framing is intentionally honest
> about limitations.

---

## 1. Dependencies

Core runtime dependencies (see `requirements.txt` and `pyproject.toml`):

```bash
pip install numpy>=1.22 pandas>=1.4 scipy>=1.8
```

Install the package in editable mode from the repository root:

```bash
pip install -e .
```

For running notebooks:

```bash
pip install -e ".[dev]"   # installs pytest + jupyter
pip install matplotlib    # optional, required for plot cells
```

Tested on Python 3.9–3.11.  No compiled extensions; any OS supported by the
dependencies should work.

---

## 2. Running the package example

```bash
python examples/basic_usage.py
```

This runs `DemandStateDetector` and `StabilizedDemandDetectorV43` on two
short synthetic demand series and prints a summary.  No external data or
environment setup required.

Expected output:

```
Baseline DemandStateDetector on stable series
...
V4.3 detector on mean-shift series (shift at day 200)
...
Done.  See docs/ for methodology and benchmarking details.
```

---

## 3. Running the tests

```bash
python -m pytest tests/ -q
```

The test suite covers:

- output DataFrame schema for all detector variants
- valid state values and score ranges
- mean-shift detection
- variance-spike detection
- hysteresis and state-machine behaviour
- baseline/normalized confidence ranges for V4.2 and V4.3
- warmup suppression for V4.3

All tests use synthetic data generated with `numpy.random.default_rng(42)`.
No external data or network access is required.

---

## 4. Opening and running the notebooks

Install dependencies first (see Section 1 above), then:

```bash
jupyter notebook notebooks/
```

Or open individual notebooks directly:

```
notebooks/01_detector_walkthrough.ipynb   – detector imports and walkthrough
notebooks/02_benchmark_iterations.ipynb  – reproducible benchmark flow
notebooks/03_cost_simulation.ipynb       – illustrative cost framing
```

### Notebook expectations

- All notebooks generate their own synthetic data — no external files needed.
- The first time you open them, cells will have no output.  Run all cells
  in order (`Cell → Run All` or `Kernel → Restart & Run All`).
- Plot cells require `matplotlib`.  If not installed, they print a message
  and skip gracefully.
- Notebook outputs are not committed to the repository (outputs are cleared
  before commit to keep diffs clean).  Running the notebooks reproduces them.

---

## 5. What is and is not reproducible from this repository

### Fully reproducible from this repo

| Item | How |
|------|-----|
| Detector behaviour on any given synthetic series | `pip install -e .` and run any detector class |
| Package example output | `python examples/basic_usage.py` |
| Unit test suite | `python -m pytest tests/ -q` |
| Notebook outputs (01, 02, 03) | Run cells in order with the package installed |
| Benchmark figures produced by the notebooks | Run `02_benchmark_iterations.ipynb` |
| Cost simulation figures | Run `03_cost_simulation.ipynb` |

### Partially reproducible (approximate, not exact)

| Item | Why only approximate |
|------|---------------------|
| Reference benchmark tables in `docs/benchmarking.md` | Those used 10 seeds; notebooks use 5 by default.  Numbers will be close but not identical.  Change `N_SEEDS = 10` in notebook 02 to reproduce the 10-seed reference more closely. |
| V4.3 parameter calibration narrative | Parameters were tuned manually in Google Colab during development.  The Colab sessions are no longer available.  Repo defaults are the best available transcription of those sessions. |

### Not reproducible from this repo

| Item | Why |
|------|-----|
| Original Colab exploration notebooks | Those were interactive development sessions and were not systematically saved or committed.  The notebooks in `notebooks/` are cleaned-up reproductions based on the current package and documented benchmark logic. |
| Results on real SKU demand data | No real data was collected or used.  All results are synthetic. |
| Automated parameter search | No automated tuning was implemented; all thresholds were set manually. |

---

## 6. What was explored in Colab vs what is now in the repo

THUNBIT was developed iteratively in Google Colab.  The main Colab work
included:

- Initial detector prototyping (raw KS + variance + ACF combination)
- State-machine experiments (V4, V4.1)
- Score normalisation experiments (V4.2 median baseline)
- Lower-quantile baseline experiments (V4.3)
- Manual parameter sweeps and qualitative assessment

The Colab notebooks were not systematically version-controlled and are no
longer available as canonical artefacts.

What has been migrated into this repository:

- The finalised detector code for all variants (in `thunbit/`)
- The benchmark results as documented tables (in `docs/benchmarking.md`)
- The methodology and design rationale (in `docs/methodology.md`)
- Cleaned-up, runnable reproductions of the key benchmark flows (in
  `notebooks/02_benchmark_iterations.ipynb`)
- A representative cost-simulation framing (in `notebooks/03_cost_simulation.ipynb`)

The notebooks in `notebooks/` are **not** direct exports of the original Colab
sessions.  They are new, self-contained notebooks written to reproduce the
documented findings using the current package.  Minor numerical differences
from the Colab work are expected and are noted where relevant.

---

## 7. Simulation basis and exploratory status

All benchmark results — including those in `docs/benchmarking.md` and
reproduced in the notebooks — are based entirely on **synthetic demand
simulations**.

- No real SKU demand data was used at any stage.
- Simulation parameters (mean, variance, break magnitude, series length) were
  chosen to be plausible but not calibrated to any real business dataset.
- All findings are exploratory.  They motivated the design choices described
  in the documentation, but they do not constitute validated performance claims.

Results may differ on real demand data, which typically has trend, seasonality,
promotions, intermittency, and other structure not captured in the simulations.

---

## 8. Known reproducibility limitations

- Stable-series false-alert rates depend on the specific random seeds used.
  The reference tables in `docs/benchmarking.md` used 10 seeds.  Results
  across any small seed set will show seed-to-seed variation.
- Detection delay numbers depend on the `min_run=3` sustained-alert threshold
  used to define "detected".  Different definitions produce different numbers.
- V4.3 parameters were set manually.  No automated cross-validation or
  parameter optimisation was done.  The reported parameter values may not be
  globally optimal even for the simulated scenarios used.

---

## 9. How to report issues

If you find that the notebooks do not run cleanly, results differ materially
from the documented tables, or the package behaves unexpectedly, please open
an issue in the repository.

Please include:
- Python version (`python --version`)
- Package versions (`pip show numpy pandas scipy`)
- The exact error or unexpected output
