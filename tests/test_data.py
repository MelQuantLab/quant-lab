import pandas as pd
import pytest

from melquantlab.data import load_prices_from_csv


def test_load_prices_from_csv(tmp_path) -> None:
    path = tmp_path / "prices.csv"
    path.write_text(
        "Date,Close\n2026-01-02,100.0\n2026-01-05,101.5\n",
        encoding="utf-8",
    )

    prices = load_prices_from_csv(path)

    assert isinstance(prices.index, pd.DatetimeIndex)
    assert prices.tolist() == [100.0, 101.5]


def test_load_prices_from_csv_reports_missing_columns(tmp_path) -> None:
    path = tmp_path / "prices.csv"
    path.write_text("timestamp,value\n2026-01-02,100.0\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing required columns"):
        load_prices_from_csv(path)
