import json

import pytest

from position_size_calc import InstrumentSpec, SpecError, load_presets, spec_from_dict
from position_size_calc.cli import main


def test_bundled_presets_valid_and_labelled():
    presets = load_presets()
    assert {"EURUSD", "USDJPY", "XAUUSD", "ES", "MNQ", "BTCUSD"} <= set(presets)
    assert presets["USDJPY"].pip == 0.01
    assert presets["EURUSD"].pip == 0.0001
    assert presets["ES"].value_per_price_unit == 50
    assert presets["MNQ"].value_per_price_unit == 2
    assert presets["CL"].value_per_price_unit == pytest.approx(1000)


def test_jpy_pip_default_without_explicit_pip_size():
    s = InstrumentSpec(name="CADJPY", kind="forex", quote_currency="JPY")
    assert s.pip == 0.01
    assert InstrumentSpec(name="AUDCAD", kind="forex", quote_currency="CAD").pip == 0.0001


@pytest.mark.parametrize(
    ("data", "match"),
    [
        ({"kind": "bond", "quote_currency": "USD"}, "kind"),
        ({"kind": "cfd"}, "required"),
        ({"kind": "cfd", "quote_currency": "USD", "lot_step": 0}, "lot_step"),
        ({"kind": "cfd", "quote_currency": "USD", "tick_value": -1}, "tick_value"),
        ({"kind": "cfd", "quote_currency": "USD", "min_lot": -1}, "min_lot"),
        ({"kind": "cfd", "quote_currency": "USD", "min_lot": 5, "max_lot": 1}, "max_lot"),
        ({"kind": "cfd", "quote_currency": "US"}, "3-letter"),
        ({"kind": "cfd", "quote_currency": "USD", "colour": "red"}, "unknown field"),
    ],
)
def test_spec_validation(data, match):
    with pytest.raises(SpecError, match=match):
        spec_from_dict("X", data)


def test_custom_preset_files(tmp_path):
    j = tmp_path / "p.json"
    j.write_text(
        json.dumps(
            {
                "instruments": {
                    "nas100": {
                        "kind": "cfd",
                        "quote_currency": "USD",
                        "contract_size": 1,
                        "lot_step": 0.1,
                    }
                }
            }
        )
    )
    assert "NAS100" in load_presets(j)
    y = tmp_path / "p.yaml"
    y.write_text(
        "instruments:\n  MYM:\n    kind: futures\n    quote_currency: USD\n"
        "    tick_size: 1\n    tick_value: 0.5\n    lot_step: 1\n"
    )
    assert load_presets(y)["MYM"].value_per_price_unit == 0.5
    bad = tmp_path / "bad.json"
    bad.write_text("{")
    with pytest.raises(SpecError, match="invalid JSON"):
        load_presets(bad)
    bad.write_text("[]")
    with pytest.raises(SpecError, match="instruments"):
        load_presets(bad)
    with pytest.raises(SpecError, match="cannot read"):
        load_presets(tmp_path / "missing.json")


def run(capsys, *args):
    rc = main(list(args))
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


def test_cli_basic(capsys):
    rc, out, _ = run(
        capsys,
        "EURUSD",
        "--balance",
        "10000",
        "--risk",
        "1",
        "--entry",
        "1.085",
        "--stop",
        "1.08",
        "--target",
        "1.095",
    )
    assert rc == 0
    assert "POSITION SIZE       0.2 lots (20000 units)" in out
    assert "R:R 2.00" in out


def test_cli_pips_and_rate(capsys):
    rc, out, _ = run(
        capsys,
        "usdjpy",
        "--balance",
        "10000",
        "--risk",
        "1",
        "--entry",
        "150",
        "--stop-pips",
        "30",
        "--rate",
        "USDJPY=150",
        "--json",
    )
    data = json.loads(out)
    assert rc == 0 and data["size"] == 0.5 and data["stop"] == pytest.approx(149.7)


def test_cli_side_from_target_and_points(capsys):
    rc, out, _ = run(
        capsys,
        "ES",
        "--balance",
        "50000",
        "--risk-amount",
        "500",
        "--entry",
        "5000",
        "--stop-points",
        "4",
        "--target",
        "4990",
        "--json",
    )
    data = json.loads(out)
    assert rc == 0
    assert data["side"] == "short" and data["stop"] == 5004 and data["size"] == 2


def test_cli_ticks_and_prop(capsys):
    rc, out, _ = run(
        capsys,
        "ES",
        "--balance",
        "50000",
        "--risk-amount",
        "500",
        "--entry",
        "5000",
        "--stop-ticks",
        "16",
        "--side",
        "short",
        "--daily-loss-left",
        "400",
        "--max-dd-left",
        "2000",
    )
    assert rc == 0
    assert "binding: daily_loss" in out and "2 contracts" in out


def test_cli_custom_instrument(capsys):
    rc, out, _ = run(
        capsys,
        "--kind",
        "futures",
        "--quote-currency",
        "usd",
        "--tick-size",
        "0.25",
        "--tick-value",
        "1.25",
        "--lot-step",
        "1",
        "--min-lot",
        "1",
        "--balance",
        "5000",
        "--risk",
        "1",
        "--entry",
        "5000",
        "--stop",
        "4990",
    )
    # 10 points * 5 USD = 50 per contract; 50 / 50 = 1
    assert rc == 0 and "POSITION SIZE       1 contracts" in out


def test_cli_override_preset(capsys):
    rc, out, _ = run(
        capsys,
        "XAUUSD",
        "--contract-size",
        "10",
        "--balance",
        "10000",
        "--risk",
        "1",
        "--entry",
        "2650",
        "--stop",
        "2640",
        "--json",
    )
    assert rc == 0
    assert json.loads(out)["size"] == 1.0  # 10 oz * 10 USD = 100/lot


def test_cli_list_presets(capsys):
    rc, out, _ = run(capsys, "--list-presets")
    assert rc == 0 and "EURUSD" in out and "EXAMPLES" in out


def test_cli_exit_codes(capsys):
    rc, out, _ = run(
        capsys, "MNQ", "--balance", "15000", "--risk", "1", "--entry", "20000", "--stop", "19900"
    )
    assert rc == 1 and "below_min_lot" in out
    rc, _, err = run(
        capsys, "NOPE", "--balance", "1", "--risk", "1", "--entry", "1", "--stop", "0.9"
    )
    assert rc == 2 and "no preset" in err
    rc, _, err = run(
        capsys, "EURJPY", "--balance", "10000", "--risk", "1", "--entry", "162", "--stop", "161"
    )
    assert rc == 2 and "USDJPY=<price>" in err
    rc, _, err = run(
        capsys,
        "USDJPY",
        "--balance",
        "10000",
        "--risk",
        "1",
        "--entry",
        "150",
        "--stop",
        "149",
        "--rate",
        "USDJPY=abc",
    )
    assert rc == 2 and "--rate" in err
    rc, _, err = run(
        capsys,
        "EURUSD",
        "--balance",
        "10000",
        "--risk",
        "1",
        "--entry",
        "1.1",
        "--stop",
        "1.09",
        "--side",
        "short",
    )
    assert rc == 2 and "does not match" in err
    rc, _, err = run(capsys, "--balance", "1")
    assert rc == 2 and "--kind" in err
    rc, _, err = run(
        capsys, "ES", "--stop-pips", "3", "--balance", "1000", "--risk", "1", "--entry", "5000"
    )
    assert rc == 2 and "pips are only defined for forex" in err


@pytest.mark.parametrize(
    "extra",
    [
        ["--balance", "inf", "--risk", "1"],
        ["--balance", "10000", "--risk-amount", "inf"],
        ["--balance", "10000", "--risk", "1", "--commission-per-lot", "nan"],
        ["--balance", "10000", "--risk", "1", "--daily-loss-left", "nan"],
    ],
)
def test_cli_rejects_non_finite_numbers(capsys, extra):
    rc, out, err = run(capsys, "EURUSD", "--entry", "1.085", "--stop", "1.08", *extra)
    assert rc == 2 and "must be a finite number" in err and out == ""


def test_cli_missing_args():
    with pytest.raises(SystemExit):
        main(["EURUSD", "--balance", "1000"])


def test_cli_no_room_exit_code(capsys):
    rc, out, _ = run(
        capsys,
        "ES",
        "--balance",
        "50000",
        "--risk-amount",
        "400",
        "--entry",
        "5000",
        "--stop",
        "4996",
        "--daily-loss-left",
        "0",
    )
    assert rc == 1 and "no_room" in out


def test_module_entry():
    import subprocess
    import sys

    r = subprocess.run(
        [sys.executable, "-m", "position_size_calc", "--version"], capture_output=True, text=True
    )
    assert r.returncode == 0 and "0.1.0" in r.stdout
