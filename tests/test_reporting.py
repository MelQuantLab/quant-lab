import json

import pandas as pd

from melquantlab.backtest import BacktestConfig, run_backtest
from melquantlab.reporting import export_result


def test_export_result_creates_excel_ready_files(tmp_path) -> None:
    prices = pd.Series(
        range(100, 180),
        index=pd.bdate_range("2026-01-01", periods=80),
        dtype=float,
    )
    result = run_backtest(prices, BacktestConfig(5, 20, 5))

    paths = export_result(result, tmp_path, label="TEST")

    assert all(path.exists() for path in paths.values())
    assert paths["timeseries"].suffix == ".csv"
    assert paths["chart"].suffix == ".png"
    metrics = json.loads(paths["metrics"].read_text(encoding="utf-8"))
    assert metrics["short_window"] == 5
    assert metrics["long_window"] == 20
