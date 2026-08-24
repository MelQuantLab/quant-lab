"""Input validation and data-quality exceptions for the monitor."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class EventRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_id: str = Field(min_length=1)
    published_at: datetime
    issuer: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    sector: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    headline: str = Field(min_length=1)
    borrow_fee_pct: float = Field(ge=0)
    utilization_pct: float = Field(ge=0, le=100)
    availability_score: float = Field(ge=0, le=100)
    lender_concentration_pct: float = Field(ge=0, le=100)
    event_confidence: float = Field(ge=0, le=100)
    days_to_catalyst: int
    liquidity_score: float = Field(ge=0, le=100)

    @field_validator("ticker")
    @classmethod
    def normalise_ticker(cls, value: str) -> str:
        return value.strip().upper()


def validate_events(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return validated rows and explicit row-level exceptions."""

    valid: list[dict] = []
    exceptions: list[dict] = []
    for row_number, row in frame.iterrows():
        payload = row.to_dict()
        try:
            EventRecord.model_validate(payload)
            valid.append(payload)
        except ValidationError as error:
            exceptions.append(
                {
                    "row_number": int(row_number) + 2,
                    "event_id": payload.get("event_id", "UNKNOWN"),
                    "ticker": payload.get("ticker", "UNKNOWN"),
                    "exception": "; ".join(
                        f"{'.'.join(map(str, item['loc']))}: {item['msg']}" for item in error.errors()
                    ),
                }
            )
    return pd.DataFrame(valid, columns=frame.columns), pd.DataFrame(
        exceptions, columns=["row_number", "event_id", "ticker", "exception"]
    )


def freshness_status(published_at: pd.Series, as_of: pd.Timestamp | None = None) -> pd.Series:
    """Classify event timestamps for visible staleness control."""

    current = as_of or pd.Timestamp.now()
    timestamps = pd.to_datetime(published_at)
    if timestamps.dt.tz is not None and current.tzinfo is None:
        current = current.tz_localize(timestamps.dt.tz)
    age_hours = (current - timestamps).dt.total_seconds() / 3600
    return pd.cut(
        age_hours,
        bins=[float("-inf"), 6, 24, float("inf")],
        labels=["CURRENT", "AGING", "STALE"],
    ).astype(str)
