import unittest
from unittest.mock import patch

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

    def test_story_normalisation_separates_publisher(self):
        story = digest._normalise_story(
            {"title": "UK shares close higher - Reuters", "link": "https://example.com"}
        )

        self.assertEqual(story["title"], "UK shares close higher")
        self.assertEqual(story["source"], "Reuters")

    def test_pm_summary_is_concise_and_data_led(self):
        ftse = pd.DataFrame(
            {
                "company": ["Winner plc", "Laggard plc"],
                "day_pct": [4.0, -3.0],
            },
            index=["WIN.L", "LAG.L"],
        )
        sectors = pd.DataFrame(
            {"day_pct": [1.5, -1.2]}, index=["Technology", "Healthcare"]
        )
        drivers = pd.DataFrame(
            {"day_pct": [0.5, -1.0]}, index=["^FTSE", "BZ=F"]
        )
        auto = pd.DataFrame(
            {"day_pct": [1.0], "week_pct": [2.0]}, index=["AUTO.L"]
        )
        news = [
            {
                "title": "Company issues trading update",
                "source": "Reuters",
                "link": "https://example.com/story",
            }
        ]

        sections = digest.build_pm_summary(
            ftse, sectors, drivers, auto, news, forward_news=[]
        )
        titles = [title for title, _ in sections]
        summary = " ".join(body for _, body in sections)

        self.assertIn("Winner plc", summary)
        self.assertIn("Auto Trader", summary)
        self.assertIn("Reuters", summary)
        self.assertIn("Today's Market", titles)
        self.assertIn("What to Pay Attention To", titles)
        self.assertIn("Things We're Watching", titles)
        self.assertIn("Prepare for the Next Session", titles)
        self.assertLessEqual(len(summary.split()), 500)

    @patch("daily_ftse_digest.fetch_news")
    def test_forward_watch_rejects_backward_looking_headlines(self, fetch_news):
        fetch_news.return_value = [
            {"title": "FTSE 100 closed higher - Reuters", "link": "https://a"},
            {"title": "Week ahead: UK earnings to watch - Reuters", "link": "https://b"},
        ]

        stories = digest.collect_forward_watch()

        self.assertEqual(len(stories), 1)
        self.assertEqual(stories[0]["title"], "Week ahead: UK earnings to watch")


if __name__ == "__main__":
    unittest.main()
