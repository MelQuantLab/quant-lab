import unittest

from openpyxl import Workbook

import market_monitor


class EvaluateQuotesTests(unittest.TestCase):
    def test_first_large_move_triggers_once(self):
        quotes = {
            "AUTO.L": {"price": 103.0, "prev_close": 100.0, "day_pct": 3.0}
        }
        state = {}

        alerts, moves = market_monitor.evaluate_quotes(quotes, state, 3.0)

        self.assertEqual(len(alerts), 1)
        self.assertAlmostEqual(moves["AUTO.L"], 3.0)
        self.assertTrue(state["AUTO.L"]["alert_active"])
        self.assertEqual(state["AUTO.L"]["last_price"], 103.0)

        repeated_alerts, _ = market_monitor.evaluate_quotes(quotes, state, 3.0)
        self.assertEqual(repeated_alerts, [])

    def test_alert_resets_after_move_returns_below_threshold(self):
        state = {"AUTO.L": {"last_price": 103.0, "alert_active": True}}
        quiet_quote = {
            "AUTO.L": {"price": 103.1, "prev_close": 103.0, "day_pct": 0.1}
        }

        market_monitor.evaluate_quotes(quiet_quote, state, 3.0)

        self.assertFalse(state["AUTO.L"]["alert_active"])

    def test_dashboard_uses_pre_update_move(self):
        workbook = Workbook()
        workbook.remove(workbook.active)
        quotes = {
            "AUTO.L": {"price": 103.0, "prev_close": 100.0, "day_pct": 3.0}
        }
        state = {"AUTO.L": {"last_price": 103.0, "alert_active": True}}

        market_monitor.update_live_sheet(
            workbook,
            quotes,
            state,
            {"AUTO.L"},
            {"AUTO.L": 3.0},
        )

        sheet = workbook["Live"]
        self.assertEqual(sheet.cell(row=2, column=4).value, 3.0)
        self.assertEqual(sheet.cell(row=2, column=5).value, "ALERT")


if __name__ == "__main__":
    unittest.main()
