import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import run_daily_if_due as scheduler


class DailySchedulerTests(unittest.TestCase):
    def test_runs_after_close_on_weekday(self):
        now = datetime(2026, 8, 5, 16, 50)
        self.assertTrue(scheduler.should_run(now, ""))

    def test_does_not_run_before_close(self):
        now = datetime(2026, 8, 5, 16, 49)
        self.assertFalse(scheduler.should_run(now, ""))

    def test_does_not_run_twice_on_same_day(self):
        now = datetime(2026, 8, 5, 18, 0)
        self.assertFalse(scheduler.should_run(now, "2026-08-05"))

    def test_does_not_run_on_weekend(self):
        now = datetime(2026, 8, 8, 17, 0)
        self.assertFalse(scheduler.should_run(now, ""))

    def test_success_marker_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "last-success"
            scheduler.record_success("2026-08-05", path)
            self.assertEqual(scheduler.read_last_success(path), "2026-08-05")


if __name__ == "__main__":
    unittest.main()
