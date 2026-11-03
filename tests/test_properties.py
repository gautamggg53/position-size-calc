"""Property-based tests for the sizing invariants."""

import math

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from position_size_calc import InstrumentSpec, PropLimits, calculate, floor_to_step
from position_size_calc.sizing import REL_TOL

steps = st.sampled_from([1.0, 0.1, 0.01, 0.001, 0.0001, 0.00001, 0.5, 0.25])
money = st.floats(min_value=1, max_value=1e7, allow_nan=False, allow_infinity=False)
prices = st.floats(min_value=0.01, max_value=1e6, allow_nan=False, allow_infinity=False)


@st.composite
def specs(draw):
    kind = draw(st.sampled_from(["forex", "cfd", "futures", "stock", "crypto"]))
    step = draw(steps)
    use_tick_value = draw(st.booleans())
    return InstrumentSpec(
        name="T",
        kind=kind,
        quote_currency="USD",
        contract_size=draw(st.sampled_from([1.0, 10.0, 100.0, 5000.0, 100000.0])),
        tick_size=draw(st.sampled_from([0.00001, 0.001, 0.01, 0.25, 1.0])),
        tick_value=draw(st.floats(0.01, 100)) if use_tick_value else None,
        lot_step=step,
        min_lot=draw(st.sampled_from([0.0, step, step * 10])),
        max_lot=draw(st.one_of(st.none(), st.floats(min_value=step * 10, max_value=1e4))),
    )


def _trade(draw_entry, frac):
    entry = draw_entry
    stop = entry * (1 - frac)
    assume(stop > 0 and stop != entry)
    return entry, stop


@settings(max_examples=400, deadline=None)
@given(
    spec=specs(),
    balance=money,
    risk_pct=st.floats(0.01, 10),
    entry=prices,
    frac=st.floats(0.0005, 0.5),
    short=st.booleans(),
    commission=st.floats(0, 20),
)
def test_risk_never_exceeds_budget(spec, balance, risk_pct, entry, frac, short, commission):
    stop = entry * (1 + frac) if short else entry * (1 - frac)
    assume(stop > 0 and abs(stop - entry) > 1e-9)
    r = calculate(
        spec,
        balance=balance,
        risk_pct=risk_pct,
        entry=entry,
        stop=stop,
        commission_per_lot=commission,
    )
    budget = balance * risk_pct / 100
    assert r.actual_risk <= budget * (1 + REL_TOL) + 1e-9
    assert r.size >= 0
    # Size is a whole number of lot steps.
    steps_n = r.size / spec.lot_step
    assert math.isclose(steps_n, round(steps_n), abs_tol=1e-6)
    # Limits are respected.
    if r.size > 0:
        assert r.size >= spec.min_lot - 1e-12
    if spec.max_lot is not None:
        assert r.size <= spec.max_lot + 1e-12
    # Rounded DOWN: one more step would breach the budget, unless a cap applied.
    if r.status == "ok":
        assert (r.size + spec.lot_step) * r.loss_per_lot > budget * (1 - 1e-9)


@settings(max_examples=400, deadline=None)
@given(
    spec=specs(),
    balance=money,
    risk_amount=money,
    entry=prices,
    frac=st.floats(0.0005, 0.5),
    daily=st.one_of(st.none(), st.floats(-100, 1e6)),
    dd=st.one_of(st.none(), st.floats(-100, 1e6)),
    open_risk=st.floats(0, 1e4),
)
def test_prop_cap_never_exceeded(spec, balance, risk_amount, entry, frac, daily, dd, open_risk):
    stop = entry * (1 - frac)
    assume(stop > 0)
    prop = PropLimits(daily_loss_left=daily, max_drawdown_left=dd, open_risk=open_risk)
    r = calculate(spec, balance=balance, risk_amount=risk_amount, entry=entry, stop=stop, prop=prop)
    limits = {"risk": risk_amount}
    if daily is not None:
        limits["daily_loss"] = daily - open_risk
    if dd is not None:
        limits["max_drawdown"] = dd - open_risk
    cap = min(limits.values())
    assert r.risk_cap == cap
    # A stop-out (plus risk already open) never breaches any limit.
    for limit in limits.values():
        assert r.actual_risk <= max(limit, 0) * (1 + REL_TOL) + 1e-9
    if daily is not None and r.size > 0:
        assert r.actual_risk + open_risk <= daily * (1 + REL_TOL) + 1e-9
    if dd is not None and r.size > 0:
        assert r.actual_risk + open_risk <= dd * (1 + REL_TOL) + 1e-9
    # The reported binding limit really is the smallest.
    assert all(limits[b] == cap or math.isclose(limits[b], cap, rel_tol=1e-9) for b in r.binding)
    if cap <= 0:
        assert r.size == 0 and r.status == "no_room"


@settings(max_examples=300, deadline=None)
@given(value=st.floats(0, 1e6), step=steps)
def test_floor_to_step(value, step):
    out = floor_to_step(value, step)
    assert out <= value + 1e-12
    assert value - out < step + 1e-9
    n = out / step
    assert math.isclose(n, round(n), abs_tol=1e-6)


@settings(max_examples=200, deadline=None)
@given(
    spec=specs(),
    balance=money,
    entry=prices,
    frac=st.floats(0.0005, 0.5),
    r1=st.floats(0.1, 5),
    r2=st.floats(0.1, 5),
)
def test_more_risk_never_gives_smaller_size(spec, balance, entry, frac, r1, r2):
    stop = entry * (1 - frac)
    assume(stop > 0)
    lo, hi = sorted([r1, r2])
    a = calculate(spec, balance=balance, risk_pct=lo, entry=entry, stop=stop)
    b = calculate(spec, balance=balance, risk_pct=hi, entry=entry, stop=stop)
    assert b.size >= a.size


@settings(max_examples=200, deadline=None)
@given(entry=st.floats(50, 300), frac=st.floats(0.0005, 0.05), rate=st.floats(50, 300))
def test_jpy_conversion_matches_manual(entry, frac, rate):
    spec = InstrumentSpec(
        name="USDJPY", kind="forex", quote_currency="JPY", base_currency="USD", contract_size=100000
    )
    stop = entry * (1 - frac)
    r = calculate(
        spec, balance=10_000, risk_pct=1, entry=entry, stop=stop, quote_to_account=1 / rate
    )
    assert math.isclose(r.loss_per_lot, (entry - stop) * 100000 / rate, rel_tol=1e-9)
