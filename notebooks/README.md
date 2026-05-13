# Notebooks

This directory is reserved for Jupyter / Colab notebooks used in the
development and benchmarking of THUNBIT.

## Contents (planned / in progress)

| Notebook | Description |
|----------|-------------|
| `01_benchmark_v4.ipynb` | Old vs V4 stabilized benchmark on synthetic scenarios |
| `02_benchmark_v41.ipynb` | V4.1 parameter sweep and cooldown evaluation |
| `03_benchmark_v43.ipynb` | V4.3 calibration and comparison summary |
| `04_cost_simulation.ipynb` | Business-cost model: when do alert savings outweigh false-alert costs? |

## Status

Notebooks are currently hosted externally (Google Colab).  They will be
cleaned up and committed here as development continues.

## Running notebooks

Install the package first (from the repository root):

```bash
pip install -e .
```

Then launch Jupyter:

```bash
jupyter notebook notebooks/
```
