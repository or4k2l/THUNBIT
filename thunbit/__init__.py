"""
THUNBIT – demand-regime instability detector.

This is a research prototype. See README for caveats and limitations.

Exports
-------
DemandStateDetector          : baseline detector (no state machine)
StabilizedDemandDetector     : V4 – adds hysteresis, smoothing, confirmation
StabilizedDemandDetectorV41  : V4.1 – adds cooldown, relaxed thresholds
StabilizedDemandDetectorV42  : V4.2 – baseline-normalized scoring (historical reference)
StabilizedDemandDetectorV43  : V4.3 – historical lower-quantile + warmup reference
StabilizedDemandDetectorV44  : V4.4 (V4.4b calibration) – recommended experimental operating point
STATE_ACTIONS                : state → recommended action mapping
STATE_HORIZONS               : state → default planning horizon mapping
"""

from .detector import DemandStateDetector
from .stabilized import (
    StabilizedDemandDetector,
    StabilizedDemandDetectorV41,
    StabilizedDemandDetectorV42,
    StabilizedDemandDetectorV43,
    StabilizedDemandDetectorV44,
)
from ._states import STATE_ACTIONS, STATE_HORIZONS

__all__ = [
    "DemandStateDetector",
    "StabilizedDemandDetector",
    "StabilizedDemandDetectorV41",
    "StabilizedDemandDetectorV42",
    "StabilizedDemandDetectorV43",
    "StabilizedDemandDetectorV44",
    "STATE_ACTIONS",
    "STATE_HORIZONS",
]

__version__ = "0.1.0"
