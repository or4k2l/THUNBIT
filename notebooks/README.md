# Notebooks

This directory contains Jupyter notebooks for exploring and benchmarking the
THUNBIT demand-regime instability detector.

## Contents

| Notebook | Description |
|----------|-------------|
| `01_detector_walkthrough.ipynb` | Imports the package, generates synthetic demand series, and runs all four detector variants (`DemandStateDetector`, `StabilizedDemandDetector`, `StabilizedDemandDetectorV41`, `StabilizedDemandDetectorV42`, `StabilizedDemandDetectorV43`).  Includes a side-by-side false-alert summary and an optional confidence plot. |
| `02_benchmark_iterations.ipynb` | Compact reproducible benchmark across four synthetic scenarios (stable, mean-shift, variance-spike, gradual-drift) comparing Baseline / V4.1 / V4.2 / V4.3.  Includes summary tables and the qualitative iteration story. |
| `03_cost_simulation.ipynb` | Illustrative cost framing: review cost vs missed-detection stockout cost, sensitivity to the cost ratio, and explicit caveats about what the model does and does not show. |

## Notes on these notebooks

These notebooks are **cleaned-up, self-contained reproductions** of the
benchmark and exploration work originally done in Google Colab during
development.  They are not direct exports of those Colab sessions.

- All demand series are generated synthetically inside each notebook.
  No external data files are required.
- Notebooks are committed with **cleared outputs**.  Run the cells to
  reproduce the outputs.
- The benchmark notebook (`02`) uses 5 seeds by default for speed.  The
  reference tables in `docs/benchmarking.md` used 10 seeds; minor numerical
  differences are expected.
- Plot cells require `matplotlib` (not a core dependency).  If not installed,
  they skip gracefully.

## Running notebooks

Install the package first (from the repository root):

```bash
pip install -e ".[dev]"      # installs package + jupyter
pip install matplotlib       # optional, for plot cells
```

Then launch Jupyter:

```bash
jupyter notebook notebooks/
```

Or run a single notebook non-interactively:

```bash
jupyter nbconvert --to notebook --execute notebooks/01_detector_walkthrough.ipynb
```

See `docs/reproducibility.md` for full reproducibility guidance.
