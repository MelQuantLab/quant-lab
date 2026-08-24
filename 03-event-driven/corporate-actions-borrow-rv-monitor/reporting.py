"""Controlled export helpers for desk review."""

from __future__ import annotations

from io import BytesIO

import pandas as pd


def build_excel_report(events: pd.DataFrame, exceptions: pd.DataFrame, audit: pd.DataFrame) -> bytes:
    """Create a review workbook with transparent, separate control sheets."""

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        events.to_excel(writer, sheet_name="Morning Monitor", index=False)
        exceptions.to_excel(writer, sheet_name="Data Exceptions", index=False)
        audit.to_excel(writer, sheet_name="Decision Audit", index=False)
        controls = pd.DataFrame(
            {
                "Control": [
                    "Confirm source and event terms",
                    "Confirm executable locate and fee",
                    "Review liquidity and recall risk",
                    "Record all decision overrides",
                ],
                "Required": ["Yes", "Yes", "Yes", "Yes"],
            }
        )
        controls.to_excel(writer, sheet_name="Control Checklist", index=False)
        for worksheet in writer.book.worksheets:
            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions
    return output.getvalue()
