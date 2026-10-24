import pandas as pd
import pytest

import run_pipeline
import top3_actual
import top3_backtest


END = pd.Timestamp("2026-10-20")


def test_resolve_periods_from_config_sorted():
    periods = top3_backtest.resolve_periods({"start_date": "", "periods_years": [10, 3, 5]}, END, None)
    assert [y for y, _ in periods] == [3, 5, 10]
    assert periods[0][1] == pd.Timestamp("2023-10-20")


def test_resolve_periods_years_flag_and_explicit_start():
    assert top3_backtest.resolve_periods({"start_date": "", "periods_years": [3, 5]}, END, 7)[0][0] == 7
    (years, start), = top3_backtest.resolve_periods({"start_date": "2020-10-20", "periods_years": [3]}, END, None)
    assert years == 6.0 and start == pd.Timestamp("2020-10-20")


@pytest.mark.parametrize("argv,expected", [
    ([], [0.0]),
    (["--large-cap"], [10.0]),
    (["--min-cap-billions", "200"], [200.0]),
    (["--sweep"], [0.0, 10.0, 200.0]),
    (["--sweep", "--large-cap"], [10.0]),
])
def test_resolve_levels(argv, expected, cfg):
    assert top3_backtest.resolve_levels(top3_backtest.parse_args(argv), cfg) == expected


def test_backtest_args_defaults():
    args = top3_backtest.parse_args([])
    assert args.config == "config.toml" and not args.sweep and args.years is None


def test_actual_args():
    args = top3_actual.parse_args(["--months", "6", "--top-n", "3", "--large-cap", "--no-cache"])
    assert (args.months, args.top_n, args.large_cap, args.no_cache) == (6, 3, True, True)


def test_pipeline_steps(cfg):
    class Args:
        config, no_cache, years, tests, skip_backtest, skip_actual, skip_etf, skip_quant = (
            "config.toml", True, 7.0, True, False, False, False, False)

    steps = run_pipeline.build_steps(cfg, Args)
    names = [n for n, _ in steps]
    assert names[0] == "Tests" and names[-1] == "Exportar JSON del frontend"
    assert len(steps) == 1 + 1 + 3 + 1 + 1 + 1                 # tests + backtest + 3 universos + ETFs + modelo por score + export
    assert "Ranking de ETFs de Vanguard" in names and any(n.startswith("Modelo por score") for n in names)
    backtest = steps[1][1]
    assert "--sweep" in backtest and "--no-cache" in backtest and backtest[backtest.index("--years") + 1] == "7"
    actual_cmds = [c for n, c in steps if n.startswith("Top actual")]
    assert [("--min-cap-billions" in c) for c in actual_cmds] == [False, True, True]

    Args.skip_backtest = Args.skip_actual = Args.skip_etf = Args.skip_quant = True
    Args.tests = False
    assert [n for n, _ in run_pipeline.build_steps(cfg, Args)] == ["Exportar JSON del frontend"]


def test_pipeline_passes_no_cache_only_to_the_first_downloading_step(cfg):
    class Args:
        config, no_cache, years, tests, skip_backtest, skip_actual, skip_etf, skip_quant = (
            "config.toml", True, None, False, False, False, True, True)

    steps = run_pipeline.build_steps(cfg, Args)
    flags = {name: "--no-cache" in cmd for name, cmd in steps}
    assert [n for n, f in flags.items() if f] == [steps[0][0]]            # solo el backtest

    Args.skip_backtest = True                                             # sin backtest, el primer Top actual
    flags = {name: "--no-cache" in cmd for name, cmd in run_pipeline.build_steps(cfg, Args)}
    assert [n for n, f in flags.items() if f] == ["Top actual - índice completo"]

    Args.no_cache = False
    assert not any("--no-cache" in cmd for _, cmd in run_pipeline.build_steps(cfg, Args))
