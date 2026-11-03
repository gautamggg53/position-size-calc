"""Command-line interface: ``psize``."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .sizing import PropLimits, SizeResult, SizingError, calculate, parse_rate, stop_from_distance
from .specs import KINDS, InstrumentSpec, SpecError, load_presets


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="psize",
        description="Risk-based position size for forex, CFDs, futures, stocks and crypto, "
        "rounded down to the lot step, with an optional prop-firm cap.",
        epilog="Instrument presets are EXAMPLES; check them against your broker's contract "
        "specs. Not financial advice.",
    )
    p.add_argument(
        "instrument",
        nargs="?",
        help="preset name, e.g. EURUSD, XAUUSD, ES "
        "(see --list-presets), or omit and describe it with --kind etc.",
    )
    p.add_argument(
        "--presets",
        metavar="FILE",
        help="your own preset file (JSON, or YAML with PyYAML installed)",
    )
    p.add_argument("--list-presets", action="store_true", help="list presets and exit")

    a = p.add_argument_group("account and risk")
    a.add_argument("--balance", type=float, help="account balance (account currency)")
    a.add_argument("--account-currency", default="USD", help="default: USD")
    r = a.add_mutually_exclusive_group()
    r.add_argument("--risk", type=float, metavar="PCT", help="risk as %% of balance, e.g. 1")
    r.add_argument("--risk-amount", type=float, metavar="MONEY", help="fixed risk in money")
    a.add_argument(
        "--rate",
        metavar="PAIR=PRICE",
        help="FX rate to convert the quote currency "
        "into the account currency, e.g. USDJPY=150.2 or EURUSD=1.085",
    )
    a.add_argument(
        "--commission-per-lot",
        type=float,
        default=0.0,
        help="round-turn commission per lot/contract, counted as risk",
    )

    t = p.add_argument_group("trade")
    t.add_argument("--entry", type=float, help="entry price")
    s = t.add_mutually_exclusive_group()
    s.add_argument("--stop", type=float, help="stop price")
    s.add_argument("--stop-pips", type=float, help="stop distance in pips (forex)")
    s.add_argument("--stop-points", type=float, help="stop distance in points")
    s.add_argument("--stop-ticks", type=float, help="stop distance in ticks")
    t.add_argument(
        "--side",
        choices=("long", "short"),
        help="needed with a stop distance unless --target shows the side (default long)",
    )
    t.add_argument("--target", type=float, help="take-profit price, for reward and R:R")

    pr = p.add_argument_group("prop mode (money left before each limit is hit)")
    pr.add_argument("--daily-loss-left", type=float)
    pr.add_argument("--max-dd-left", type=float)
    pr.add_argument(
        "--open-risk", type=float, default=0.0, help="money already at risk in other open positions"
    )

    c = p.add_argument_group("custom or overridden instrument spec")
    c.add_argument("--kind", choices=KINDS)
    c.add_argument("--quote-currency")
    c.add_argument("--base-currency")
    c.add_argument("--contract-size", type=float)
    c.add_argument("--tick-size", type=float)
    c.add_argument("--tick-value", type=float, help="money per tick per lot (quote currency)")
    c.add_argument("--pip-size", type=float)
    c.add_argument("--point-size", type=float)
    c.add_argument("--lot-step", type=float)
    c.add_argument("--min-lot", type=float)
    c.add_argument("--max-lot", type=float)

    p.add_argument("--json", action="store_true", help="print the result as JSON")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


_SPEC_ARGS = (
    "kind",
    "quote_currency",
    "base_currency",
    "contract_size",
    "tick_size",
    "tick_value",
    "pip_size",
    "point_size",
    "lot_step",
    "min_lot",
    "max_lot",
)


def resolve_spec(args: argparse.Namespace) -> InstrumentSpec:
    overrides = {k: getattr(args, k) for k in _SPEC_ARGS}
    for k in ("quote_currency", "base_currency"):
        if overrides[k]:
            overrides[k] = overrides[k].upper()
    if args.instrument:
        presets = load_presets(args.presets)
        name = args.instrument.upper()
        if name not in presets:
            raise SpecError(
                f"no preset named {name!r}; see --list-presets, or describe the "
                "instrument with --kind, --quote-currency, --tick-size, ..."
            )
        return presets[name].with_overrides(**overrides)
    if not overrides["kind"] or not overrides["quote_currency"]:
        raise SpecError("give a preset name, or at least --kind and --quote-currency")
    return InstrumentSpec(name="CUSTOM", **{k: v for k, v in overrides.items() if v is not None})


def _fmt(x: float | None, nd: int = 2) -> str:
    return "n/a" if x is None else f"{x:,.{nd}f}"


def _size(x: float) -> str:
    text = f"{x:.8f}".rstrip("0").rstrip(".")
    return text or "0"


def render(res: SizeResult, account: str, spec: InstrumentSpec) -> str:
    lines = [
        f"{res.instrument} {res.side}  entry {res.entry:g}  stop {res.stop:g}",
        f"Stop distance       {res.stop_distance:g}"
        + (f" ({res.stop_pips:g} pips)" if res.stop_pips is not None else "")
        + f" = {res.stop_ticks:g} ticks",
        f"Loss per {spec.unit_name[:-1]:<10} {_fmt(res.loss_per_lot)} {account} at the stop",
    ]
    if res.pip_value_per_lot is not None:
        lines.append(f"Pip value per lot   {_fmt(res.pip_value_per_lot)} {account}")
    if res.quote_to_account is not None:
        lines.append(
            f"Conversion          1 {spec.quote_currency} = {res.quote_to_account:.6g} {account}"
        )
    lines.append(f"Risk budget         {_fmt(res.target_risk)} {account}")
    if res.binding != ["risk"] or res.risk_cap != res.target_risk:
        lines.append(
            f"Allowed risk        {_fmt(res.risk_cap)} {account} "
            f"(binding: {', '.join(res.binding)})"
        )
    lines += [
        f"Raw size            {res.raw_size:.6f} {spec.unit_name}",
        f"POSITION SIZE       {_size(res.size)} {spec.unit_name}"
        + (
            f" ({_size(res.units)} units)"
            if spec.kind in ("forex", "cfd") and spec.contract_size != 1
            else ""
        ),
        f"Actual risk         {_fmt(res.actual_risk)} {account} "
        f"({_fmt(res.actual_risk_pct)}% of balance)",
    ]
    if res.target is not None:
        lines.append(
            f"Target {res.target:g}: reward {_fmt(res.reward)} {account}, "
            f"R:R {res.reward_to_risk:.2f}"
        )
    if res.status != "ok":
        lines.append(f"Status              {res.status}")
    lines += [f"Note: {n}" for n in res.notes]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.list_presets:
            for name, spec in load_presets(args.presets).items():
                print(f"{name:<22} {spec.kind:<8} {spec.quote_currency}  {spec.description}")
            print("\nThese are EXAMPLES. Check them against your broker's contract specs.")
            return 0
        spec = resolve_spec(args)
        missing = [f"--{n}" for n in ("balance", "entry") if getattr(args, n) is None]
        if args.risk is None and args.risk_amount is None:
            missing.append("--risk or --risk-amount")
        dist_args = {"pips": args.stop_pips, "points": args.stop_points, "ticks": args.stop_ticks}
        if args.stop is None and all(v is None for v in dist_args.values()):
            missing.append("--stop (or --stop-pips/--stop-points/--stop-ticks)")
        if missing:
            parser.error("missing " + ", ".join(missing))
        stop = args.stop
        if stop is None:
            unit, n = next((k, v) for k, v in dist_args.items() if v is not None)
            size = {
                "pips": lambda: spec.pip,
                "points": lambda: spec.point,
                "ticks": lambda: spec.tick_size,
            }[unit]()
            side = args.side
            if side is None and args.target is not None:
                side = "long" if args.target > args.entry else "short"
            stop = stop_from_distance(args.entry, side or "long", price_distance=n * size)
        elif args.side is not None and (args.side == "long") != (stop < args.entry):
            raise SizingError(
                f"--side {args.side} does not match a stop at {stop} with entry {args.entry}"
            )
        account = args.account_currency.upper()
        conv = None
        if args.rate:
            pair, _, value = args.rate.partition("=")
            try:
                rate = float(value)
            except ValueError as exc:
                raise SizingError(f"--rate must look like USDJPY=150.2, got {args.rate!r}") from exc
            conv = parse_rate(pair, rate, spec.quote_currency, account)
        prop = None
        if args.daily_loss_left is not None or args.max_dd_left is not None:
            prop = PropLimits(args.daily_loss_left, args.max_dd_left, args.open_risk)
        res = calculate(
            spec,
            balance=args.balance,
            entry=args.entry,
            stop=stop,
            account_currency=account,
            risk_pct=args.risk,
            risk_amount=args.risk_amount,
            quote_to_account=conv,
            commission_per_lot=args.commission_per_lot,
            target=args.target,
            prop=prop,
        )
    except (SizingError, SpecError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(
            json.dumps(
                {"account_currency": account, "spec": spec.to_dict(), **res.to_dict()}, indent=2
            )
        )
    else:
        sys.stdout.write(render(res, account, spec))
    return 0 if res.status != "no_room" and res.size > 0 else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
