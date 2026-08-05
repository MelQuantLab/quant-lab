import unittest

import pandas as pd

import daily_ftse_digest as digest


class DailyFtseDigestTests(unittest.TestCase):
    def test_lse_ticker_conversion(self):
        self.assertEqual(digest.yahoo_lse_ticker("AUTO"), "AUTO.L")
        self.assertEqual(digest.yahoo_lse_ticker("BT.A"), "BT-A.L")
        self.assertEqual(digest.yahoo_lse_ticker("BA."), "BA.L")

    def test_notable_moves_detects_price_and_volume_events(self):
        frame = pd.DataFrame(
            {
                "day_pct": [3.2, 0.4, -0.2],
                "volume_ratio": [1.0, 2.4, 0.8],
            },
            index=["AAA.L", "BBB.L", "CCC.L"],
        )

        result = digest.notable_moves(frame)

        self.assertEqual(set(result.index), {"AAA.L", "BBB.L"})

    def test_attach_names_keeps_unknown_ticker_readable(self):
        frame = pd.DataFrame({"day_pct": [1.0]}, index=["TEST.L"])

        result = digest.attach_names(frame, {})

        self.assertEqual(result.loc["TEST.L", "company"], "TEST.L")

    def test_move_colours_distinguish_direction(self):
        self.assertEqual(digest._move_colour(1.0), "#34D6A2")
        self.assertEqual(digest._move_colour(-1.0), "#FF6B7A")

    def test_metric_card_contains_label_and_value(self):
        card = digest._metric_card("FTSE 100", "+1.25%", "#34D6A2", "market close")
        self.assertIn("FTSE 100", card)
        self.assertIn("+1.25%", card)
        self.assertIn("market close", card)

    def test_table_can_bold_the_top_mover(self):
        frame = pd.DataFrame(
            {
                "company": ["Winner plc", "Runner-up plc"],
                "day_pct": [5.2, 3.1],
            },
            index=["WIN.L", "RUN.L"],
        )

        table = digest._table(
            frame,
            [("company", "Company"), ("day_pct", "1 day")],
            emphasise_first=True,
        )

        winner_cell = table.split("Winner plc", 1)[0].rsplit("<td", 1)[-1]
        runner_up_cell = table.split("Runner-up plc", 1)[0].rsplit("<td", 1)[-1]
        self.assertIn("font-weight:800", winner_cell)
        self.assertIn("font-weight:500", runner_up_cell)


if __name__ == "__main__":
    unittest.main()
