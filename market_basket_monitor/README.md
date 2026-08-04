# Market Basket Monitor

Python, not VBA — Excel-for-Mac's VBA can't reliably hit the internet or run in the
background, so it's a dead end for this. This does the same job with free data sources.

Tracks your basket (defaults to Autotrader Group plc, ticker `AUTO.L` on the FTSE 100 — a
single stock, kept simple to start), fires a macOS
notification + email when a ticker moves past a threshold, and sends a weekly email
with price moves and news headlines. Every run also writes/updates an Excel workbook
(`basket_dashboard.xlsx`) so you can just open it in Excel to see the current picture —
no VBA involved, since VBA can't reliably fetch data or send mail on Mac. The workbook
has three tabs:

- **Live** — current price, day %, % since last check, alert flag (row highlighted
  yellow if it triggered an alert), last-updated time. Rewritten every check run.
- **Weekly History** — one row per ticker per week, so a trend builds up over time.
- **News** — latest headlines per ticker with clickable links.

If the file is open in Excel when the script runs, the save will be skipped (Excel
locks it) — you'll see a warning in the log, and it'll save on the next run. Excel also
won't auto-refresh from an external change, so close and reopen the file to see updates.

## 1. Setup

```bash
cd market_basket_monitor
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and add your email address and BT Internet password (or an app password —
generate one at https://www.bt.com/help/email/email-security if you have extra
security turned on).

Edit `config.py`:
- `TICKERS` — starts with just `AUTO.L` (Autotrader Group). Add more FTSE 100 or any
  Yahoo Finance symbols when you're ready, e.g. `"RR.L"` (Rolls-Royce), `"TSCO.L"` (Tesco).
- `ALERT_THRESHOLD_PCT` — how big a move (%) triggers an alert. Default 3%.

## 2. Test it

```bash
python3 market_monitor.py --mode check
python3 market_monitor.py --mode weekly
```

Check your inbox, open `basket_dashboard.xlsx` in Excel, and watch for a macOS
notification (if a threshold was hit).

## 3. Automate it

macOS's `launchd` is more reliable than cron here (cron jobs get killed when the Mac
sleeps; launchd wakes for scheduled jobs). Two plist files are included:

- `com.melisa.marketmonitor.alert.plist` — runs the price/news check every 30 minutes
- `com.melisa.marketmonitor.weekly.plist` — sends the weekly digest every Monday 8am

Before loading them, open each `.plist` and replace `/path/to/market_basket_monitor`
with the real absolute path to this folder (both the venv python path and the
working directory).

```bash
cp com.melisa.marketmonitor.alert.plist ~/Library/LaunchAgents/
cp com.melisa.marketmonitor.weekly.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.melisa.marketmonitor.alert.plist
launchctl load ~/Library/LaunchAgents/com.melisa.marketmonitor.weekly.plist
```

To stop:
```bash
launchctl unload ~/Library/LaunchAgents/com.melisa.marketmonitor.alert.plist
launchctl unload ~/Library/LaunchAgents/com.melisa.marketmonitor.weekly.plist
```

Logs land in `/tmp/market_monitor_alert.log` / `.err` and `/tmp/market_monitor_weekly.log` / `.err`
if something isn't firing as expected.

## 4. VBA control panel in Excel (optional)

Adds a "Refresh Now" macro/button in Excel that reruns the Python engine and reloads
the dashboard, so you never have to touch Terminal day-to-day. This needs a few manual
steps because modern Excel for Mac is sandboxed — VBA can't shell out directly anymore
(the old `Shell`/`MacScript` commands are deprecated and unreliable). The supported
route is `AppleScriptTask`, which calls a small helper AppleScript file.

**Step 1 — place the helper AppleScript.**
Create the folder if it doesn't exist, then copy the file in:
```bash
mkdir -p ~/"Library/Application Scripts/com.microsoft.Excel"
cp RunPythonMonitor.applescript ~/"Library/Application Scripts/com.microsoft.Excel/"
```

**Step 2 — import the VBA module.**
In Excel: `Tools > Macro > Visual Basic Editor` (or `Option+F11`). Then
`File > Import File...` and select `AutoMonitor.bas`.

**Step 3 — set your real paths.**
In the VBA editor, open the `AutoMonitor` module and edit the three constants at the
top (`PYTHON_PATH`, `SCRIPT_DIR`, `DASHBOARD_PATH`) to match wherever you put the
`market_basket_monitor` folder — e.g. if it's in `~/market_basket_monitor`, use
`/Users/<you>/market_basket_monitor/...`.

**Step 4 — add a button.**
Save your workbook as a macro-enabled file (`File > Save As` → File Format:
`Excel Macro-Enabled Workbook (.xlsm)`). Then `Insert > Shape`, draw a rectangle,
right-click it → `Assign Macro...` → pick `RefreshNow`. Repeat for a second button
assigned to `RunWeeklyDigestNow` if you want a manual "send digest now" button too.

**Step 5 — test it.**
Click the button. The first run will likely trigger a macOS permission prompt
(Automation / Apple Events) — allow it. If it errors, double-check the paths from
step 3 and that the `.applescript` file landed in the exact folder from step 1.

If this route gives you trouble (sandboxing on newer macOS versions can be finicky),
a more reliable alternative is skipping VBA entirely and using the Automator app or
Shortcuts.app to build a double-clickable "Refresh AUTO Monitor" app that runs the
same Python command — happy to build that instead if you'd rather not fight VBA.

## Notes

- Price data: `yfinance` (free, no API key, ~15-min delayed for most exchanges).
- News: Google News RSS per ticker (free, no API key).
- The alert check only fires when a threshold is crossed — no news means no email spam.
- `last_prices.json` tracks state between runs so alerts are "moved X% since last check,"
  not just "moved X% since yesterday's close."
- This only runs while your Mac is on and awake. If you want it to work even when your
  laptop is closed, say the word and I'll set up a hosted version instead.
