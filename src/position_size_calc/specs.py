"""Instrument specifications and preset files (JSON, or YAML if PyYAML is installed)."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, fields, replace
from importlib import resources
from pathlib import Path
from typing import Any

KINDS = ("forex", "cfd", "futures", "stock", "crypto")
UNIT_NAMES = {
    "forex": "lots",
    "cfd": "lots",
    "futures": "contracts",
    "stock": "shares",
    "crypto": "units",
}


class SpecError(ValueError):
    """An instrument spec or preset file is invalid."""


@dataclass(frozen=True)
class InstrumentSpec:
    """How price moves turn into money for one instrument.

    Money per 1.0 price move per lot, in ``quote_currency``, is
    ``tick_value / tick_size`` when ``tick_value`` is set, else ``contract_size``.
    """

    name: str
    kind: str
    quote_currency: str
    contract_size: float = 1.0
    tick_size: float = 0.01
    tick_value: float | None = None
    pip_size: float | None = None
    point_size: float | None = None
    lot_step: float = 0.01
    min_lot: float = 0.0
    max_lot: float | None = None
    base_currency: str | None = None
    description: str = ""

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise SpecError(
                f"{self.name}: kind must be one of {', '.join(KINDS)}, not {self.kind!r}"
            )
        for f in (
            "contract_size",
            "tick_size",
            "tick_value",
            "pip_size",
            "point_size",
            "lot_step",
            "min_lot",
            "max_lot",
        ):
            v = getattr(self, f)
            if v is not None and not math.isfinite(v):
                raise SpecError(f"{self.name}: {f} must be a finite number, got {v!r}")
        for f in ("contract_size", "tick_size", "lot_step"):
            if not getattr(self, f) > 0:
                raise SpecError(f"{self.name}: {f} must be positive")
        for f in ("tick_value", "pip_size", "point_size", "max_lot"):
            v = getattr(self, f)
            if v is not None and not v > 0:
                raise SpecError(f"{self.name}: {f} must be positive when set")
        if self.min_lot < 0:
            raise SpecError(f"{self.name}: min_lot cannot be negative")
        if self.max_lot is not None and self.max_lot < self.min_lot:
            raise SpecError(f"{self.name}: max_lot is below min_lot")
        if len(self.quote_currency) != 3:
            raise SpecError(f"{self.name}: quote_currency must be a 3-letter code")

    @property
    def value_per_price_unit(self) -> float:
        """Money (quote currency) per 1.0 price move for one lot/contract/unit."""
        if self.tick_value is not None:
            return self.tick_value / self.tick_size
        return self.contract_size

    @property
    def pip(self) -> float:
        """Pip size: explicit, else 0.01 for JPY-quoted forex and 0.0001 for other forex."""
        if self.pip_size is not None:
            return self.pip_size
        if self.kind == "forex":
            return 0.01 if self.quote_currency.upper() == "JPY" else 0.0001
        raise SpecError(
            f"{self.name}: pips are only defined for forex; use points or ticks, or set pip_size"
        )

    @property
    def point(self) -> float:
        return self.point_size if self.point_size is not None else self.tick_size

    @property
    def unit_name(self) -> str:
        return UNIT_NAMES[self.kind]

    def with_overrides(self, **changes: Any) -> InstrumentSpec:
        clean = {k: v for k, v in changes.items() if v is not None}
        return replace(self, **clean) if clean else self

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, "")}


_FIELDS = {f.name for f in fields(InstrumentSpec)}


def spec_from_dict(name: str, data: dict[str, Any]) -> InstrumentSpec:
    unknown = set(data) - _FIELDS
    if unknown:
        raise SpecError(f"{name}: unknown field(s) {', '.join(sorted(unknown))}")
    if "kind" not in data or "quote_currency" not in data:
        raise SpecError(f"{name}: 'kind' and 'quote_currency' are required")
    try:
        return InstrumentSpec(name=name, **{k: v for k, v in data.items() if k != "name"})
    except TypeError as exc:
        raise SpecError(f"{name}: {exc}") from exc


def _parse_text(text: str, suffix: str) -> Any:
    if suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as exc:
            raise SpecError(
                "YAML presets need PyYAML: pip install 'position-size-calc[yaml]', or use JSON"
            ) from exc
        return yaml.safe_load(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SpecError(f"invalid JSON: {exc}") from exc


def load_presets(path: str | Path | None = None) -> dict[str, InstrumentSpec]:
    """Load presets from ``path`` (JSON/YAML), or the bundled example presets."""
    if path is None:
        text = (
            resources.files(__package__)
            .joinpath("presets/instruments.json")
            .read_text(encoding="utf-8")
        )
        suffix = ".json"
    else:
        p = Path(path)
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as exc:
            raise SpecError(f"cannot read {p}: {exc.strerror or exc}") from exc
        suffix = p.suffix.lower()
    data = _parse_text(text, suffix)
    if not isinstance(data, dict) or not isinstance(data.get("instruments"), dict):
        raise SpecError("preset file must contain an 'instruments' mapping")
    return {
        name.upper(): spec_from_dict(name.upper(), d) for name, d in data["instruments"].items()
    }
