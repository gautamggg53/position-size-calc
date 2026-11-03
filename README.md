# position-size-calc

[![CI](https://github.com/gautamggg53/position-size-calc/actions/workflows/ci.yml/badge.svg)](https://github.com/gautamggg53/position-size-calc/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A small, dependency-free Python library and CLI (`psize`) for risk-based
position sizing. Give it a balance, a risk (% or amount), an entry and a stop,
and an instrument spec; it returns the largest size that keeps a stop-out
within your risk, **rounded down** to the lot step, plus the actual risk after
rounding and the R:R to an optional target.

- Forex: pip value including JPY pairs; cross-currency conversion with a rate
  you supply; exact conversion when the account currency is the pair's base.
- CFDs, indices and metals: contract size, tick size and tick value.
- Futures: tick size and tick value per contract.
- Stocks and crypto: units, with whole or fractional steps.
- Stop as a price, or as a distance in pips, points or ticks.
- Optional round-turn commission, counted as part of the risk.
- **Prop mode:** pass the money left before your daily-loss and max-drawdown
  limits (and any risk already open). The size is capped so a stop-out cannot
  breach either, and the output says which limit binds.

> **Not financial advice.** This is a calculator. It does not tell you whether
> to trade. The bundled instrument presets are **examples**: contract sizes,
> tick values and lot steps differ between brokers and change over time.
> **Check every value against your broker's or exchange's contract spec.**

## Install

```bash
pip install git+https://github.com/gautamggg53/position-size-calc
pip install "position-size-calc[yaml] @ git+https://github.com/gautamggg53/position-size-calc"  # YAML presets
```

Python 3.10+, no runtime dependencies. (Not on PyPI yet.)

## Examples

Real runs (default account currency is USD; change it with `--account-currency`):

```text
$ psize EURUSD --balance 10000 --risk 1 --entry 1.0850 --stop 1.0800 --target 1.0950
EURUSD long  entry 1.085  stop 1.08
Stop distance       0.005 (50 pips) = 500 ticks
Loss per lot        500.00 USD at the stop
Pip value per lot   10.00 USD
Risk budget         100.00 USD
Raw size            0.200000 lots
POSITION SIZE       0.2 lots (20000 units)
Actual risk         100.00 USD (1.00% of balance)
Target 1.095: reward 200.00 USD, R:R 2.00
```

JPY cross with a USD account. The JPY to USD rate is yours to supply:

```text
$ psize GBPJPY --balance 10000 --risk 0.5 --entry 191.20 --stop-pips 35 --side short --rate USDJPY=151.4
GBPJPY short  entry 191.2  stop 191.55
Stop distance       0.35 (35 pips) = 350 ticks
Loss per lot        231.18 USD at the stop
Pip value per lot   6.61 USD
Conversion          1 JPY = 0.00660502 USD
Risk budget         50.00 USD
Raw size            0.216286 lots
POSITION SIZE       0.21 lots (21000 units)
Actual risk         48.55 USD (0.49% of balance)
```

Prop mode: 1% of 100,000 is 1,000, but only 800 is left before the max
drawdown and 200 is already at risk in another trade, so 600 is allowed:

```text
$ psize XAUUSD --balance 100000 --risk 1 --entry 2650 --stop 2640 --daily-loss-left 3000 --max-dd-left 800 --open-risk 200
XAUUSD long  entry 2650  stop 2640
Stop distance       10 = 1000 ticks
Loss per lot        1,000.00 USD at the stop
Risk budget         1,000.00 USD
Allowed risk        600.00 USD (binding: max_drawdown)
Raw size            0.600000 lots
POSITION SIZE       0.6 lots (60 units)
Actual risk         600.00 USD (0.60% of balance)
```

Futures with commission and a target:

```text
$ psize MES --balance 50000 --risk-amount 300 --entry 5000 --stop-points 12 --commission-per-lot 1.24 --target 5030
MES long  entry 5000  stop 4988
Stop distance       12 = 48 ticks
Loss per contract   61.24 USD at the stop
Risk budget         300.00 USD
Raw size            4.898759 contracts
POSITION SIZE       4 contracts
Actual risk         244.96 USD (0.49% of balance)
Target 5030: reward 595.04 USD, R:R 2.50
```

A personal preset file, where even one contract is too big for the budget
(exit code 1):

```text
$ psize MGC --presets examples/my_presets.yaml --balance 5000 --risk 1 --entry 2650 --stop 2640
MGC long  entry 2650  stop 2640
Stop distance       10 = 100 ticks
Loss per contract   100.00 USD at the stop
Risk budget         50.00 USD
Raw size            0.500000 contracts
POSITION SIZE       0 contracts
Actual risk         0.00 USD (0.00% of balance)
Status              below_min_lot
Note: The smallest tradable size (1 contracts) would risk 100.00 USD, more than the 50.00 allowed, so the size is 0.
```

`--json` prints every field (spec, loss per lot, raw and rounded size, binding
limit, notes) for scripts. `psize --list-presets` lists the bundled examples.

## How it calculates

1. **Money per 1.0 price move per lot** (quote currency): `tick_value / tick_size`
   if the spec has a tick value, otherwise `contract_size`.
2. **Conversion to the account currency:** 1 if the quote currency is the account
   currency; your `--rate` (e.g. `USDJPY=150.2`, either direction works); or,
   for forex where the account currency is the pair's base currency, the stop
   price itself (that is the exact rate at which a stop-out is realised).
   Otherwise it stops with an error instead of guessing.
3. **Loss per lot** = `|entry − stop| × money per price move × conversion + commission per lot`.
4. **Allowed risk** = the smallest of: your risk budget, `daily_loss_left − open_risk`,
   `max_dd_left − open_risk`. Every limit equal to the smallest is reported as binding.
5. **Size** = `allowed risk / loss per lot`, rounded **down** to `lot_step`, then
   capped at `max_lot`. If that is below `min_lot`, the size is 0 and the note
   says what the minimum size would risk.
6. **Reward** (with `--target`) = size × target distance × money per price move ×
   conversion − commission. **R:R** is the price ratio `|target − entry| / |entry − stop|`.

Pips: `pip_size` from the spec, otherwise 0.01 for JPY-quoted forex and 0.0001
for other forex. Points use `point_size` (default: tick size).

Floating point: a relative tolerance of 1e-9 stops float noise such as
`0.3 / 0.1 = 2.9999999999999996` from costing a whole lot step. Actual risk can
exceed the cap by at most that fraction (e.g. 0.0000001 on 100). The property
tests check this bound.

## Presets

`src/position_size_calc/presets/instruments.json` ships example specs for
major forex pairs (including JPY pairs), XAUUSD/XAGUSD, index CFDs (US500,
US30, GER40), CME-style futures (ES, MES, NQ, MNQ, CL, GC), stocks and spot
crypto. Copy it (or `examples/my_presets.yaml`), edit the values to match your
broker, and pass it with `--presets FILE`. Any spec field can also be
overridden on the command line, e.g. `--contract-size 10 --lot-step 0.1`, or
you can skip presets entirely:

```bash
psize --kind futures --quote-currency USD --tick-size 0.25 --tick-value 1.25 \
      --lot-step 1 --min-lot 1 --balance 5000 --risk 1 --entry 5000 --stop 4990
```

## Library use

```python
from position_size_calc import PropLimits, calculate, load_presets, parse_rate

spec = load_presets()["USDJPY"]
res = calculate(
    spec,
    balance=10_000,
    risk_pct=1,
    entry=150.0,
    stop=149.7,
    account_currency="USD",
    prop=PropLimits(daily_loss_left=400, max_drawdown_left=900),
)
print(res.size, res.actual_risk, res.binding)
```

## Tests

`pytest` runs hand-worked examples (`tests/test_worked_examples.py`, with the
arithmetic in comments) and hypothesis property tests
(`tests/test_properties.py`): actual risk never exceeds the budget or any prop
limit, sizes are whole lot steps within min/max, one more step would breach the
budget, more risk never gives a smaller size, and JPY conversion matches the
manual formula.

## Limitations

- Assumes the stop fills at the stop price. Slippage and gaps can make a real
  loss larger; leave room for them in your budget.
- Conversion rates are fixed at the value you supply; there is no live FX data.
- Spread is not modelled separately. Include it in the stop distance if your
  platform measures stops from the other side of the spread.
- Margin and leverage are not checked.
- Prop limits are taken as plain money amounts. How a firm measures them
  (balance vs equity, trailing, reset time) is up to you to work out.

## Roadmap

Plans, not promises:

- Margin requirement check with a user-supplied leverage.
- Optional slippage buffer (extra ticks added to the stop distance).
- Sizing several entries (scale-in) against one risk budget.
- Publish to PyPI.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md): `pip install -e ".[dev]"`, then
`pytest --cov` and `ruff check .`.

## License

MIT, see [LICENSE](LICENSE).
