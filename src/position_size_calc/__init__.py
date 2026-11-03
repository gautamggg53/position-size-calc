"""Risk-based position sizing for forex, CFDs, futures, stocks and crypto, with a prop-firm cap."""

from .sizing import (
    PropLimits,
    SizeResult,
    SizingError,
    calculate,
    floor_to_step,
    parse_rate,
    stop_from_distance,
)
from .specs import InstrumentSpec, SpecError, load_presets, spec_from_dict

__all__ = [
    "InstrumentSpec",
    "PropLimits",
    "SizeResult",
    "SizingError",
    "SpecError",
    "calculate",
    "floor_to_step",
    "load_presets",
    "parse_rate",
    "spec_from_dict",
    "stop_from_distance",
]
__version__ = "0.1.0"
