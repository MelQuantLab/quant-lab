"""SQLite persistence for reproducible Black-Scholes scenario runs."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from options_analytics import SurfacePoint


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS inputs (
    CalculationId INTEGER PRIMARY KEY AUTOINCREMENT,
    StockPrice REAL NOT NULL CHECK (StockPrice > 0),
    StrikePrice REAL NOT NULL CHECK (StrikePrice > 0),
    Volatility REAL NOT NULL CHECK (Volatility > 0),
    TimeToExpiry REAL NOT NULL CHECK (TimeToExpiry > 0),
    RiskFreeRate REAL NOT NULL,
    CallPurchasePrice REAL NOT NULL CHECK (CallPurchasePrice >= 0),
    PutPurchasePrice REAL NOT NULL CHECK (PutPurchasePrice >= 0),
    CreatedAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outputs (
    OutputId INTEGER PRIMARY KEY AUTOINCREMENT,
    CalculationId INTEGER NOT NULL,
    ShockedStockPrice REAL NOT NULL CHECK (ShockedStockPrice > 0),
    ShockedVolatility REAL NOT NULL CHECK (ShockedVolatility > 0),
    CallModelValue REAL NOT NULL,
    PutModelValue REAL NOT NULL,
    CallPnL REAL NOT NULL,
    PutPnL REAL NOT NULL,
    FOREIGN KEY (CalculationId) REFERENCES inputs (CalculationId) ON DELETE CASCADE,
    UNIQUE (CalculationId, ShockedStockPrice, ShockedVolatility)
);

CREATE INDEX IF NOT EXISTS idx_outputs_calculation
    ON outputs (CalculationId);
"""


def connect(database_path: str | Path) -> sqlite3.Connection:
    """Open a database connection with relational constraints enabled."""
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialise_database(database_path: str | Path) -> None:
    """Create the database schema when it does not yet exist."""
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    with connect(database_path) as connection:
        connection.executescript(SCHEMA)


def save_calculation(
    database_path: str | Path,
    *,
    stock_price: float,
    strike_price: float,
    volatility: float,
    time_to_expiry: float,
    risk_free_rate: float,
    call_purchase_price: float,
    put_purchase_price: float,
    surface: Iterable[SurfacePoint],
) -> int:
    """Atomically persist one input set and all linked scenario outputs."""
    initialise_database(database_path)
    rows = list(surface)
    if not rows:
        raise ValueError("At least one scenario output is required.")

    with connect(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO inputs (
                StockPrice, StrikePrice, Volatility, TimeToExpiry,
                RiskFreeRate, CallPurchasePrice, PutPurchasePrice, CreatedAt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stock_price,
                strike_price,
                volatility,
                time_to_expiry,
                risk_free_rate,
                call_purchase_price,
                put_purchase_price,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        calculation_id = int(cursor.lastrowid)
        connection.executemany(
            """
            INSERT INTO outputs (
                CalculationId, ShockedStockPrice, ShockedVolatility,
                CallModelValue, PutModelValue, CallPnL, PutPnL
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    calculation_id,
                    point.shocked_spot,
                    point.shocked_volatility,
                    point.call_value,
                    point.put_value,
                    point.call_pnl,
                    point.put_pnl,
                )
                for point in rows
            ],
        )
    return calculation_id


def recent_calculations(database_path: str | Path, limit: int = 10) -> list[sqlite3.Row]:
    """Return recent saved base inputs and the number of output scenarios."""
    initialise_database(database_path)
    with connect(database_path) as connection:
        return connection.execute(
            """
            SELECT i.*, COUNT(o.OutputId) AS ScenarioCount
            FROM inputs AS i
            JOIN outputs AS o ON o.CalculationId = i.CalculationId
            GROUP BY i.CalculationId
            ORDER BY i.CalculationId DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
