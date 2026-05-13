"""
Shared state constants for THUNBIT detectors.
"""

STATE_ACTIONS = {
    "STABLE": "No change.",
    "DRIFT": "Review inventory parameters.",
    "SHIFT": "Reset demand model.",
}

# Default planning horizons (days) per state.
# These are heuristic starting points, not prescriptive recommendations.
STATE_HORIZONS = {
    "STABLE": 90,
    "DRIFT": 30,
    "SHIFT": 14,
}
