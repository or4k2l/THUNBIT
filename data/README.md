# Data

This directory is reserved for data files used in benchmarking or
example notebooks.

## Current status

All benchmark results in this repository were generated from **synthetic
demand series** produced programmatically.  No external data files are
committed here.

## Generating synthetic data

The benchmark simulations use a simple scenario generator.  See
`docs/benchmarking.md` for a description of the simulated scenarios and
parameters.

To reproduce the benchmark series, run the notebooks in `notebooks/` or
adapt the scenario generation code from the benchmarking notebook.

## Real data

If you wish to test THUNBIT on your own demand data, provide a
one-dimensional NumPy array or list of daily demand observations:

```python
import numpy as np
from thunbit import StabilizedDemandDetectorV44

demand = np.array([...])   # your daily demand series
det = StabilizedDemandDetectorV44()
result = det.detect_rolling_stabilized(demand)
print(result[["t", "state", "confidence"]].tail(10))
```

See `examples/basic_usage.py` for a full worked example.
