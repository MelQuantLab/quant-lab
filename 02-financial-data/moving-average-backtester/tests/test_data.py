import pandas as pd
import pytest

from melquantlab.data import download_prices, load_prices_from_csv


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


@pytest.mark.parametrize("multi_index", [False, True])
def test_download_prices_handles_flat_and_multiindex_columns(
    monkeypatch,
    multi_index: bool,
) -> None:
    index = pd.bdate_range("2026-01-01", periods=2)
    if multi_index:
        columns = pd.MultiIndex.from_tuples([("Close", "SPY")])
        downloaded = pd.DataFrame([[100.0], [101.5]], index=index, columns=columns)
    else:
        downloaded = pd.DataFrame({"Close": [100.0, 101.5]}, index=index)

    monkeypatch.setattr("yfinance.download", lambda *args, **kwargs: downloaded)

    prices = download_prices("SPY", "2026-01-01", "2026-01-10")

    expected = pd.Series([100.0, 101.5], index=index, name="price")
    pd.testing.assert_series_equal(prices, expected)


def test_download_prices_rejects_blank_ticker() -> None:
    with pytest.raises(ValueError, match="ticker cannot be blank"):
        download_prices(" ", "2026-01-01", "2026-01-10")


def test_download_prices_rejects_empty_download(monkeypatch) -> None:
    monkeypatch.setattr(
        "yfinance.download",
        lambda *args, **kwargs: pd.DataFrame(),
    )

    with pytest.raises(ValueError, match="no price data returned"):
        download_prices("SPY", "2026-01-01", "2026-01-10")
