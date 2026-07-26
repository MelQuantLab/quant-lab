# Excel/VBA weekly reporting

This folder contains the user-facing reporting layer for Project 1.

## Files

- `MelQuantLab_Weekly_Dashboard.xlsx` — verified Excel dashboard template.
- `MelQuantLabWeeklyReport.bas` — VBA module for refreshing the Python CSV,
  exporting a dated PDF and creating an email draft.
- `MelQuantLabEmail.applescript` — macOS Mail helper used by the VBA module to
  create a draft with the PDF attached.

## Intended workflow

1. Run the Python backtester to generate the latest time-series CSV.
2. Open the Excel dashboard and inspect the current settings.
3. Run `RefreshWeeklyReport`.
4. Review the formulas, charts and plain-English conclusion.
5. Run `CreateWeeklyPDFAndEmail`.
6. Review the resulting email draft and attachment before sending.

The automation deliberately creates a draft rather than silently sending
research. The workbook and macros require final testing in desktop Excel on
macOS before this stage is marked complete.

Generated weekly PDFs and refreshed report outputs should not be committed to
Git.
