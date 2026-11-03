"""Risk-based position sizing. See docs in README "How it calculates"."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from decimal import ROUND_FLOOR, Decimal

from .specs import InstrumentSpec

# Relative tolerance used only to stop floating-point noise (e.g. 0.3 / 0.1 =
# 2.9999999999999996) from costing a whole lot step. Actual risk never exceeds
# the cap by more than this fraction.
REL_TOL = 1e-9


class SizingError(ValueError):
    """Inputs that cannot produce a position size."""


@dataclass(frozen=True)
class PropLimits:
    """Remaining room under prop-firm style limits, in account currency.

    ``open_risk`` is money already at risk in other open positions; it is
    subtracted from both rooms.
    """

    daily_loss_left: float | None = None
    max_drawdown_left: float | None = None
    open_risk: float = 0.0


@dataclass
class SizeResult:
    instrument: str
    unit_name: str
    side: str
    entry: float
    stop: float
    stop_distance: float
    stop_pips: float | None
    stop_ticks: float
    quote_to_account: float | None
    loss_per_lot: float
    pip_value_per_lot: float | None
    target_risk: float
    risk_cap: float
    binding: list[str]
    raw_size: float
    size: float
    units: float
    actual_risk: float
    actual_risk_pct: float | None
    target: float | None = None
    reward: float | None = None
    reward_to_risk: float | None = None
    status: str = "ok"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _fmt_size(x: float) -> str:
    return f"{x:.8f}".rstrip("0").rstrip(".")


def _largest_size_within(cap: float, loss_per_lot: float, step: float) -> float:
    """Largest whole number of ``step`` whose loss stays within ``cap`` (1e-9 relative)."""
    d_step = Decimal(repr(step))
    n = int(
        (Decimal(repr(cap / loss_per_lot * (1 + REL_TOL))) / d_step).to_integral_value(
            rounding=ROUND_FLOOR
        )
    )
    # Float noise can leave n one step too high; step down on exact integers.
    while n > 0 and float(n * d_step) * loss_per_lot > cap * (1 + REL_TOL):
        n -= 1
    return float(n * d_step)


def floor_to_step(value: float, step: float) -> float:
    """Round ``value`` down to a multiple of ``step``, returned without float drift."""
    if value <= 0:
        return 0.0
    d_step = Decimal(repr(step))
    n = (Decimal(repr(value)) / d_step).to_integral_value(rounding=ROUND_FLOOR)
    return float(n * d_step)


def parse_rate(pair: str, rate: float, quote: str, account: str) -> float:
    """Turn a quoted FX rate into account-currency per 1 quote-currency unit.

    ``pair`` is six letters, e.g. ``USDJPY``. With account USD and quote JPY,
    ``USDJPY=150`` gives 1/150; ``JPYUSD=0.00667`` gives 0.00667.
    """
    p = pair.strip().upper().replace("/", "")
    q, a = quote.upper(), account.upper()
    if not rate > 0:
        raise SizingError("conversion rate must be positive")
    if p == a + q:
        return 1.0 / rate
    if p == q + a:
        return rate
    raise SizingError(f"rate {pair} does not convert {q} to {a}; give {a}{q} or {q}{a}")


def stop_from_distance(entry: float, side: str, *, price_distance: float) -> float:
    if not price_distance > 0:
        raise SizingError("stop distance must be positive")
    return entry - price_distance if side == "long" else entry + price_distance


def calculate(
    spec: InstrumentSpec,
    *,
    balance: float,
    entry: float,
    stop: float,
    account_currency: str = "USD",
    risk_pct: float | None = None,
    risk_amount: float | None = None,
    quote_to_account: float | None = None,
    commission_per_lot: float = 0.0,
    target: float | None = None,
    prop: PropLimits | None = None,
) -> SizeResult:
    """Largest size whose loss at ``stop`` stays within the risk budget.

    Money values are in the account currency. ``quote_to_account`` is account
    currency per 1 unit of the instrument's quote currency; it is not needed
    when they match, or for forex when the account currency is the pair's base
    currency (then the stop/target price itself converts exactly).
    ``commission_per_lot`` is a round-turn cost added to the loss per lot.
    """
    notes: list[str] = []
    account = account_currency.upper()
    if not balance > 0:
        raise SizingError("balance must be positive")
    if not entry > 0 or not stop > 0:
        raise SizingError("entry and stop must be positive prices")
    if entry == stop:
        raise SizingError("stop equals entry; there is no risk distance")
    if (risk_pct is None) == (risk_amount is None):
        raise SizingError("give exactly one of risk_pct or risk_amount")
    if risk_pct is not None and not 0 < risk_pct <= 100:
        raise SizingError("risk_pct must be in (0, 100]")
    if risk_amount is not None and not risk_amount > 0:
        raise SizingError("risk_amount must be positive")
    if commission_per_lot < 0:
        raise SizingError("commission_per_lot cannot be negative")
    side = "long" if stop < entry else "short"
    if target is not None:
        if not target > 0:
            raise SizingError("target must be a positive price")
        if (side == "long" and target <= entry) or (side == "short" and target >= entry):
            raise SizingError(
                f"target {target} is on the wrong side of entry for a {side} (stop {stop})"
            )

    distance = abs(entry - stop)
    quote = spec.quote_currency.upper()

    def convert_at(price: float) -> float:
        if quote_to_account is not None:
            return quote_to_account
        if quote == account:
            return 1.0
        if spec.kind == "forex" and spec.base_currency and spec.base_currency.upper() == account:
            return 1.0 / price
        raise SizingError(
            f"{spec.name} is quoted in {quote} but the account is in {account}: "
            f"give a rate, e.g. {quote}{account}=<price> or "
            f"{account}{quote}=<price>"
        )

    if quote_to_account is not None and not quote_to_account > 0:
        raise SizingError("quote_to_account must be positive")
    conv_stop = convert_at(stop)
    if quote_to_account is None and quote != account:
        notes.append(
            f"{quote} converted to {account} at the stop price, which is exact when "
            "the account currency is the pair's base currency."
        )
    loss_per_lot = distance * spec.value_per_price_unit * conv_stop + commission_per_lot

    target_risk = balance * risk_pct / 100 if risk_pct is not None else float(risk_amount or 0)
    caps: dict[str, float] = {"risk": target_risk}
    if prop is not None:
        if prop.open_risk < 0:
            raise SizingError("open_risk cannot be negative")
        if prop.daily_loss_left is not None:
            caps["daily_loss"] = prop.daily_loss_left - prop.open_risk
        if prop.max_drawdown_left is not None:
            caps["max_drawdown"] = prop.max_drawdown_left - prop.open_risk
    cap = min(caps.values())
    binding = [k for k, v in caps.items() if math.isclose(v, cap, rel_tol=REL_TOL)]

    status = "ok"
    if cap <= 0:
        raw = size = 0.0
        status = "no_room"
        notes.append("No room left under " + " / ".join(binding) + ", so the size is 0.")
    else:
        raw = cap / loss_per_lot
        size = _largest_size_within(cap, loss_per_lot, spec.lot_step)
        if spec.max_lot is not None and size > spec.max_lot:
            size = floor_to_step(spec.max_lot, spec.lot_step)
            status = "capped_max_lot"
            notes.append(f"Capped at the maximum of {spec.max_lot} {spec.unit_name}.")
        if size < spec.min_lot or size <= 0:
            min_risk = max(spec.min_lot, spec.lot_step) * loss_per_lot
            notes.append(
                f"The smallest tradable size ({_fmt_size(max(spec.min_lot, spec.lot_step))} "
                f"{spec.unit_name}) would risk {min_risk:,.2f} {account}, more than "
                f"the {cap:,.2f} allowed, so the size is 0."
            )
            size = 0.0
            status = "below_min_lot"

    actual = size * loss_per_lot
    reward = rr = None
    if target is not None:
        conv_t = convert_at(target)
        reward = size * abs(target - entry) * spec.value_per_price_unit * conv_t
        reward -= size * commission_per_lot
        rr = abs(target - entry) / distance

    pip_value = None
    if spec.kind == "forex":
        pip_value = spec.pip * spec.value_per_price_unit * convert_at(entry)
    return SizeResult(
        instrument=spec.name,
        unit_name=spec.unit_name,
        side=side,
        entry=entry,
        stop=stop,
        stop_distance=round(distance, 12),
        stop_pips=round(distance / spec.pip, 6) if spec.kind == "forex" else None,
        stop_ticks=round(distance / spec.tick_size, 6),
        quote_to_account=conv_stop if quote != account or quote_to_account is not None else None,
        loss_per_lot=loss_per_lot,
        pip_value_per_lot=pip_value,
        target_risk=target_risk,
        risk_cap=cap,
        binding=binding,
        raw_size=raw,
        size=size,
        units=size * spec.contract_size if spec.kind != "futures" else size,
        actual_risk=actual,
        actual_risk_pct=actual / balance * 100,
        target=target,
        reward=reward,
        reward_to_risk=rr,
        status=status,
        notes=notes,
    )
