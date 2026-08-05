#!/usr/bin/env python3
"""Run the daily briefing once per weekday after the 16:40 local close."""

import subprocess
import sys
from datetime import datetime, time
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
STATE_PATH = BASE_DIR / ".daily_ftse_last_success"
TARGET_TIME = time(16, 50)


def should_run(now: datetime, last_success: str) -> bool:
    """Return True once after 16:40 on Monday-Friday."""
    return (
        now.weekday() < 5
        and now.time().replace(tzinfo=None) >= TARGET_TIME
        and last_success != now.date().isoformat()
    )


def read_last_success(path: Path = STATE_PATH) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def record_success(date_text: str, path: Path = STATE_PATH) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(date_text + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    now = datetime.now().astimezone()
    if not should_run(now, read_last_success()):
        return 0

    print(f"[scheduler] daily briefing due for {now.date().isoformat()}", flush=True)
    subprocess.run(
        [sys.executable, str(BASE_DIR / "daily_ftse_digest.py")],
        cwd=BASE_DIR,
        check=True,
    )
    record_success(now.date().isoformat())
    print("[scheduler] delivery completed and recorded", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
