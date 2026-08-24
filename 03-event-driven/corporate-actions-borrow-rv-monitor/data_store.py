"""DuckDB-backed read model for events, securities and decisions."""

from __future__ import annotations

import duckdb
import pandas as pd


def build_store(events: pd.DataFrame, security_master: pd.DataFrame) -> duckdb.DuckDBPyConnection:
    """Create an isolated in-memory store suitable for the public prototype."""

    connection = duckdb.connect(":memory:")
    connection.register("events_frame", events)
    connection.register("security_master_frame", security_master)
    connection.execute("CREATE TABLE events AS SELECT * FROM events_frame")
    connection.execute("CREATE TABLE security_master AS SELECT * FROM security_master_frame")
    connection.execute(
        """
        CREATE TABLE decision_audit (
            recorded_at TIMESTAMP,
            event_id VARCHAR,
            ticker VARCHAR,
            model_decision VARCHAR,
            desk_decision VARCHAR,
            reason VARCHAR
        )
        """
    )
    return connection


def joined_event_view(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Return one de-duplicated event view enriched by dated security metadata."""

    return connection.execute(
        """
        SELECT e.*, s.security_id, s.isin, s.sedol, s.country, s.currency,
               s.exchange, s.market_cap_segment, s.primary_universe,
               s.ftse_100_member, s.ftse_250_member,
               s.euro_stoxx_50_member, s.stoxx_europe_600_member,
               s.effective_from, s.effective_to, s.data_mode
        FROM events e
        LEFT JOIN security_master s USING (ticker)
        ORDER BY e.published_at DESC
        """
    ).df()
