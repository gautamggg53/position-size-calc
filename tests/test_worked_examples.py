"""Worked examples. Each expected value is derived by hand in the comment above it."""

import pytest

from position_size_calc import (
    InstrumentSpec,
    PropLimits,
    SizingError,
    calculate,
    floor_to_step,
    load_presets,
    parse_rate,
    stop_from_distance,
)

P = load_presets()


def test_eurusd_usd_account():
    # 50 pips = 0.0050; 1 lot = 100,000 EUR -> 0.0050 * 100,000 = 500 USD per lot.
    # Budget 1% of 10,000 = 100 -> 100 / 500 = 0.20 lots, risk exactly 100.
    r = calculate(P["EURUSD"], balance=10_000, risk_pct=1, entry=1.0850, stop=1.0800)
    assert r.side == "long"
    assert r.stop_pips == pytest.approx(50)
    assert r.loss_per_lot == pytest.approx(500)
    assert r.pip_value_per_lot == pytest.approx(10)
    assert r.size == 0.2
    assert r.units == pytest.approx(20_000)
    assert r.actual_risk == pytest.approx(100)


def test_rounds_down_not_to_nearest():
    # 37 pips -> 370 USD/lot; 100 / 370 = 0.27027 -> 0.27 lots (risk 99.90).
    r = calculate(P["EURUSD"], balance=10_000, risk_pct=1, entry=1.1000, stop=1.0963)
    assert r.size == 0.27
    assert r.actual_risk == pytest.approx(99.9)
    # 0.2799 would round to 0.28 to the nearest; down-rounding must give 0.27.
    assert floor_to_step(0.2799, 0.01) == 0.27


def test_usdjpy_pip_value_with_rate():
    # JPY pair: pip = 0.01. 30 pips = 0.30 JPY * 100,000 = 30,000 JPY per lot.
    # At USDJPY 150: 30,000 / 150 = 200 USD per lot. 100 / 200 = 0.50 lots.
    # Pip value: 0.01 * 100,000 = 1,000 JPY = 6.666... USD.
    r = calculate(
        P["USDJPY"],
        balance=10_000,
        risk_pct=1,
        entry=150.00,
        stop=149.70,
        quote_to_account=parse_rate("USDJPY", 150, "JPY", "USD"),
    )
    assert r.stop_pips == pytest.approx(30)
    assert r.loss_per_lot == pytest.approx(200)
    assert r.pip_value_per_lot == pytest.approx(1000 / 150)
    assert r.size == 0.5


def test_eurjpy_cross_with_usd_account():
    # EURJPY short 162.50, stop 162.90 = 40 pips = 0.40 * 100,000 = 40,000 JPY/lot.
    # USDJPY 160 -> 250 USD/lot. Risk 2% of 25,000 = 500 -> 2.00 lots.
    conv = parse_rate("USDJPY", 160, "JPY", "USD")
    r = calculate(
        P["EURJPY"], balance=25_000, risk_pct=2, entry=162.50, stop=162.90, quote_to_account=conv
    )
    assert r.side == "short"
    assert r.loss_per_lot == pytest.approx(250)
    assert r.size == 2.0


def test_eurgbp_with_usd_account_rate_direction():
    # EURGBP quote GBP; account USD; GBPUSD = 1.25 means 1 GBP = 1.25 USD.
    # 20 pips = 0.0020 * 100,000 = 200 GBP = 250 USD/lot. 100 / 250 = 0.40.
    conv = parse_rate("GBPUSD", 1.25, "GBP", "USD")
    assert conv == 1.25
    r = calculate(
        P["EURGBP"],
        balance=10_000,
        risk_amount=100,
        entry=0.8500,
        stop=0.8480,
        quote_to_account=conv,
    )
    assert r.size == 0.4


def test_base_currency_account_converts_at_stop():
    # EUR account trading EURUSD: loss in USD = 0.005 * 100,000 = 500 USD/lot,
    # in EUR at the stop price 1.08: 500 / 1.08 = 462.96. 100 / 462.96 = 0.216 -> 0.21.
    r = calculate(
        P["EURUSD"], balance=10_000, risk_pct=1, entry=1.085, stop=1.080, account_currency="EUR"
    )
    assert r.loss_per_lot == pytest.approx(500 / 1.08)
    assert r.size == 0.21
    assert r.actual_risk == pytest.approx(0.21 * 500 / 1.08)


def test_usd_base_pair_needs_no_rate():
    # USDJPY with a USD account: 0.30 JPY * 100,000 = 30,000 JPY, converted at the
    # stop price 149.70 -> 200.40 USD/lot. 100 / 200.40 = 0.499 -> 0.49 lots.
    r = calculate(P["USDJPY"], balance=10_000, risk_pct=1, entry=150, stop=149.7)
    assert r.loss_per_lot == pytest.approx(30_000 / 149.7)
    assert r.size == 0.49


def test_missing_conversion_rate_is_an_error():
    with pytest.raises(SizingError, match="USDJPY=<price>"):
        calculate(
            P["EURJPY"], balance=10_000, risk_pct=1, entry=162, stop=161.7, account_currency="USD"
        )
    with pytest.raises(SizingError, match="EURUSD"):
        calculate(P["GER40"], balance=10_000, risk_pct=1, entry=18000, stop=17950)


def test_gold_cfd():
    # XAUUSD 100 oz/lot: $10 stop -> 1,000 USD/lot. 0.5% of 50,000 = 250 -> 0.25 lots.
    r = calculate(P["XAUUSD"], balance=50_000, risk_pct=0.5, entry=2650.00, stop=2640.00)
    assert r.loss_per_lot == pytest.approx(1000)
    assert r.size == 0.25
    assert r.units == pytest.approx(25)  # ounces


def test_index_cfd_in_eur_with_commission():
    # GER40 1 EUR/point/lot, 50 points = 50 EUR = 54 USD at EURUSD 1.08,
    # plus 0.50 USD commission = 54.50/lot. 50 / 54.5 = 0.917 -> step 0.1 -> 0.9.
    r = calculate(
        P["GER40"],
        balance=10_000,
        risk_pct=0.5,
        entry=18000,
        stop=17950,
        quote_to_account=parse_rate("EURUSD", 1.08, "EUR", "USD"),
        commission_per_lot=0.5,
    )
    assert r.loss_per_lot == pytest.approx(54.5)
    assert r.size == 0.9
    assert r.actual_risk == pytest.approx(49.05)


def test_futures_es_ticks():
    # ES: 0.25 tick = 12.50 USD -> 50 USD/point. 4-point stop = 16 ticks = 200 USD.
    # 500 / 200 = 2.5 -> whole contracts -> 2.
    r = calculate(P["ES"], balance=50_000, risk_amount=500, entry=5000, stop=4996)
    assert r.stop_ticks == 16
    assert r.loss_per_lot == pytest.approx(200)
    assert r.size == 2
    assert r.unit_name == "contracts"
    assert r.units == 2


def test_futures_below_min_contract():
    # MNQ: 2 USD/point. 100-point stop = 200 USD > 150 budget -> 0 contracts.
    r = calculate(P["MNQ"], balance=15_000, risk_pct=1, entry=20_000, stop=19_900)
    assert r.size == 0
    assert r.status == "below_min_lot"
    assert "200.00 USD" in r.notes[0]


def test_stock_whole_and_fractional_shares():
    # 2,000 * 0.5% = 10 USD; stop 1.50 away -> 6.67 shares -> 6 whole, 6.666 fractional.
    whole = calculate(P["STOCK-USD"], balance=2_000, risk_pct=0.5, entry=101.50, stop=100.00)
    frac = calculate(
        P["STOCK-USD-FRACTIONAL"], balance=2_000, risk_pct=0.5, entry=101.50, stop=100.00
    )
    assert whole.size == 6 and whole.actual_risk == pytest.approx(9.0)
    assert frac.size == pytest.approx(6.666)


def test_crypto_units():
    # 1% of 1,000 = 10 USD; stop 1,000 away -> 0.01 BTC.
    r = calculate(P["BTCUSD"], balance=1_000, risk_pct=1, entry=65_000, stop=64_000)
    assert r.size == pytest.approx(0.01)


def test_max_lot_cap():
    spec = P["EURUSD"].with_overrides(max_lot=1.0)
    # 10 pips -> 100 USD/lot; 1% of 1,000,000 = 10,000 -> 100 lots, capped at 1.
    r = calculate(spec, balance=1_000_000, risk_pct=1, entry=1.1000, stop=1.0990)
    assert r.size == 1.0 and r.status == "capped_max_lot"
    assert r.actual_risk == pytest.approx(100)


def test_reward_to_risk():
    # Long 1.0850, stop 1.0800 (50 pips), target 1.0950 (100 pips): R:R 2.
    # 0.20 lots * 100 pips * 10 USD = 200 USD reward.
    r = calculate(P["EURUSD"], balance=10_000, risk_pct=1, entry=1.0850, stop=1.0800, target=1.0950)
    assert r.reward_to_risk == pytest.approx(2.0)
    assert r.reward == pytest.approx(200)


def test_reward_is_net_of_commission():
    # ES 2 contracts, 8-point target = 400/contract -> 800 - 2 * 5 commission = 790.
    r = calculate(
        P["ES"],
        balance=50_000,
        risk_amount=500,
        entry=5000,
        stop=4996,
        target=5008,
        commission_per_lot=5,
    )
    # loss per contract 205 -> 500/205 = 2.43 -> 2
    assert r.size == 2
    assert r.reward == pytest.approx(790)


def test_prop_daily_loss_binds():
    # Risk budget 500, but only 400 left today -> 400 / 200 = 2 contracts.
    r = calculate(
        P["ES"],
        balance=50_000,
        risk_amount=500,
        entry=5000,
        stop=4996,
        prop=PropLimits(daily_loss_left=400, max_drawdown_left=2000),
    )
    assert r.binding == ["daily_loss"]
    assert r.risk_cap == 400 and r.size == 2


def test_prop_drawdown_binds_with_open_risk():
    # Gold 1,000 USD/lot. Rooms: daily 3000-200 = 2800, drawdown 800-200 = 600.
    r = calculate(
        P["XAUUSD"],
        balance=100_000,
        risk_pct=1,
        entry=2650,
        stop=2640,
        prop=PropLimits(daily_loss_left=3000, max_drawdown_left=800, open_risk=200),
    )
    assert r.binding == ["max_drawdown"]
    assert r.size == 0.6


def test_prop_tie_reports_both():
    r = calculate(
        P["ES"],
        balance=50_000,
        risk_amount=400,
        entry=5000,
        stop=4996,
        prop=PropLimits(daily_loss_left=400),
    )
    assert r.binding == ["risk", "daily_loss"]


def test_prop_no_room():
    r = calculate(
        P["ES"],
        balance=50_000,
        risk_amount=400,
        entry=5000,
        stop=4996,
        prop=PropLimits(daily_loss_left=300, open_risk=300),
    )
    assert r.size == 0 and r.status == "no_room" and r.binding == ["daily_loss"]


def test_stop_from_distance():
    assert stop_from_distance(1.1, "long", price_distance=0.002) == pytest.approx(1.098)
    assert stop_from_distance(1.1, "short", price_distance=0.002) == pytest.approx(1.102)
    with pytest.raises(SizingError):
        stop_from_distance(1.1, "long", price_distance=0)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"balance": 0}, "balance"),
        ({"stop": 1.085}, "no risk distance"),
        ({"entry": -1}, "positive prices"),
        ({"risk_amount": 50}, "exactly one"),
        ({"risk_pct": 0}, "risk_pct"),
        ({"risk_pct": None, "risk_amount": -5}, "risk_amount"),
        ({"commission_per_lot": -1}, "commission"),
        ({"target": 1.07}, "wrong side"),
        ({"target": -1}, "positive price"),
        ({"quote_to_account": 0}, "quote_to_account"),
        ({"prop": PropLimits(open_risk=-1)}, "open_risk"),
    ],
)
def test_input_validation(kwargs, match):
    base = {"balance": 10_000, "risk_pct": 1, "entry": 1.085, "stop": 1.08}
    with pytest.raises(SizingError, match=match):
        calculate(P["EURUSD"], **{**base, **kwargs})


def test_parse_rate_errors():
    with pytest.raises(SizingError, match="does not convert"):
        parse_rate("EURUSD", 1.1, "JPY", "USD")
    with pytest.raises(SizingError, match="positive"):
        parse_rate("USDJPY", 0, "JPY", "USD")
    assert parse_rate("jpy/usd", 0.0066, "JPY", "USD") == 0.0066


def test_custom_spec_pips_for_non_forex():
    spec = InstrumentSpec(name="X", kind="cfd", quote_currency="USD")
    with pytest.raises(ValueError, match="pips"):
        _ = spec.pip
    assert spec.point == spec.tick_size


def test_huge_size_with_tiny_step_terminates():
    # Regression: 1,000,000 risk / (0.0001 * 1) = 1e10 units with a 0.00001 step.
    # At that magnitude a float minus one step equals itself, so sizing must work
    # on whole step counts rather than subtracting floats.
    spec = InstrumentSpec(name="X", kind="crypto", quote_currency="USD", lot_step=0.00001)
    r = calculate(spec, balance=10_000_000, risk_pct=10, entry=0.01, stop=0.0099)
    assert r.size == pytest.approx(1e10, rel=2e-9)  # within the documented 1e-9 tolerance
    assert r.actual_risk <= 1_000_000 * (1 + 1e-9)
