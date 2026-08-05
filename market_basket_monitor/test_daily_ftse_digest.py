import unittest
from unittest.mock import patch

import pandas as pd

import daily_ftse_digest as digest


class DailyFtseDigestTests(unittest.TestCase):
    def test_compact_text_preserves_short_copy_and_truncates_long_copy(self):
        self.assertEqual(digest._compact_text("Short market note."), "Short market note.")
        compact = digest._compact_text("word " * 100, limit=40)
        self.assertLessEqual(len(compact), 40)
        self.assertTrue(compact.endswith("…"))

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

    def test_property_exposure_selects_relevant_ftse_sectors(self):
        frame = pd.DataFrame(
            {
                "company": ["Property REIT", "Barratt Redrow", "Consumer plc"],
                "sector": [
                    "Real Estate Investment Trusts",
                    "Household goods & home construction",
                    "Banks",
                ],
                "day_pct": [1.0, -0.5, 0.2],
            },
            index=["REIT.L", "BUILD.L", "BANK.L"],
        )

        result = digest.property_exposure(frame)

        self.assertEqual(set(result.index), {"REIT.L", "BUILD.L"})

    @patch("daily_ftse_digest.requests.get")
    def test_boe_property_rates_uses_latest_available_observation(self, get):
        get.return_value.text = (
            "DATE,IUDSOIA,IUDBEDR\n"
            "03 Aug 2026,3.7321,3.75\n"
            "04 Aug 2026,,3.75\n"
        )
        get.return_value.raise_for_status.return_value = None

        result = digest.fetch_boe_property_rates()

        self.assertEqual(result["SONIA"]["value"], 3.7321)
        self.assertEqual(result["SONIA"]["as_of"], "03 Aug 2026")
        self.assertEqual(result["Bank Rate"]["value"], 3.75)

    @patch("daily_ftse_digest.requests.get")
    def test_ftse_sector_metadata_combines_technology_and_communication(self, get):
        get.return_value.text = (
            '"asOf":{"formattedValue":"03/Aug/2026",'
            '"fullName":"exposureBreakdowns.asOf"},'
            '"fund":{"value":[0.31,0.82,10.38],'
            '"fullName":"exposureBreakdowns.fund"},'
            '"type":{"value":["Information Technology","Communication","Financials"],'
            '"fullName":"exposureBreakdowns.type"}'
        )
        get.return_value.raise_for_status.return_value = None

        weights, ticker_sectors, as_of = digest.fetch_ftse_sector_metadata()

        self.assertAlmostEqual(weights["Technology & Media"], 1.13)
        self.assertEqual(ticker_sectors, {})
        self.assertEqual(weights["Financials"], 10.38)
        self.assertEqual(as_of, "03/Aug/2026")

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

    @patch("daily_ftse_digest.fetch_news")
    def test_ranked_news_rejects_clickbait_even_from_known_platform(self, fetch_news):
        fetch_news.return_value = [
            {
                "title": "Here's 1 REIT I'm buying for juicy dividends! - Yahoo Finance UK",
                "link": "https://example.com/clickbait",
            },
            {
                "title": "Housebuilder reports annual results - Reuters",
                "link": "https://example.com/reuters",
            },
        ]

        stories = digest.collect_ranked_news(["Housebuilder"])

        self.assertEqual([story["source"] for story in stories], ["Reuters"])

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
        banks = pd.DataFrame(
            {"company": ["Lloyds"], "day_pct": [1.0]}, index=["LLOY.L"]
        )
        autos = pd.DataFrame(
            {"company": ["Auto Trader"], "day_pct": [0.6]}, index=["AUTO.L"]
        )
        technology = pd.DataFrame(
            {"company": ["Tech plc"], "day_pct": [1.2]}, index=["TECH.L"]
        )
        materials = pd.DataFrame(
            {"company": ["Copper"], "day_pct": [2.0]}, index=["HG=F"]
        )
        real_estate = pd.DataFrame(
            {"company": ["Landsec"], "day_pct": [0.8]}, index=["LAND.L"]
        )
        housebuilders = pd.DataFrame(
            {"company": ["Persimmon"], "day_pct": [-0.5]}, index=["PSN.L"]
        )
        consumers = pd.DataFrame(
            {"company": ["Next", "Tesco"], "day_pct": [0.4, -0.2]},
            index=["NXT.L", "TSCO.L"],
        )
        rates = {
            "SONIA": {"value": 3.7321, "as_of": "03 Aug 2026"},
            "Bank Rate": {"value": 3.75, "as_of": "04 Aug 2026"},
        }
        news = [
            {
                "title": "Company issues trading update",
                "source": "Reuters",
                "link": "https://example.com/story",
            }
        ]

        sections = digest.build_pm_summary(
            ftse,
            sectors,
            drivers,
            banks,
            autos,
            technology,
            materials,
            real_estate,
            housebuilders,
            consumers,
            rates,
            news,
            forward_news=[],
        )
        titles = [title for title, _ in sections]
        summary = " ".join(body for _, body in sections)

        self.assertIn("Winner plc", summary)
        self.assertIn("SONIA", summary)
        self.assertIn("housebuilders", summary)
        self.assertIn("Reuters", summary)
        self.assertIn("Today's Market", titles)
        self.assertIn("Autos", titles)
        self.assertIn("Financials", titles)
        self.assertIn("Technology", titles)
        self.assertIn("Macro View", titles)
        self.assertIn("What to Pay Attention To", titles)
        self.assertIn("Things We're Watching", titles)
        self.assertIn("Prepare for the Next Session", titles)
        self.assertEqual(
            titles[:3],
            [
                "What to Pay Attention To",
                "Things We're Watching",
                "Prepare for the Next Session",
            ],
        )
        self.assertLessEqual(len(summary.split()), 500)

    def test_alpha_view_has_four_distinct_time_horizons(self):
        ftse = pd.DataFrame(
            {"company": ["Leader plc"], "day_pct": [2.5], "month_pct": [5.0]},
            index=["LEAD.L"],
        )
        sectors = {"Industrials": ftse.copy(), "Financials": ftse.assign(day_pct=-1.0)}
        property_frame = pd.DataFrame(
            {"company": ["Property plc"], "day_pct": [0.5], "month_pct": [4.2]},
            index=["PROP.L"],
        )
        ideas = digest.build_alpha_view(
            ftse,
            sectors,
            property_frame,
            pd.DataFrame(),
            {"SONIA": {"value": 3.75}},
            [{"title": "Company announces results", "source": "Reuters"}],
            [{"title": "UK inflation data due"}],
        )

        self.assertEqual(
            [idea["horizon"] for idea in ideas],
            ["1 Day", "1 Week", "14 Days", "1 Month"],
        )
        self.assertIn("Company announces results", ideas[0]["thesis"])
        self.assertIn("UK inflation data due", ideas[2]["thesis"])
        self.assertIn("SONIA", ideas[3]["thesis"])

    def test_alpha_view_matches_headline_to_named_company(self):
        ftse = pd.DataFrame(
            {
                "company": ["Index Leader", "SEGRO"],
                "day_pct": [5.0, 1.2],
                "month_pct": [6.0, 2.0],
            },
            index=["LEAD.L", "SGRO.L"],
        )
        ideas = digest.build_alpha_view(
            ftse,
            {"Industrials": ftse.iloc[[0]], "Real Estate": ftse.iloc[[1]]},
            ftse.iloc[[1]],
            pd.DataFrame(),
            {},
            [{"title": "SEGRO agrees takeover offer", "source": "Reuters"}],
            [],
        )

        self.assertEqual(ideas[0]["title"], "Catalyst follow-through: SEGRO")
        self.assertIn("+1.20%", ideas[0]["thesis"])

    def test_alpha_view_does_not_invent_fortnight_catalyst(self):
        frame = pd.DataFrame(
            {"company": ["Example plc"], "day_pct": [1.0], "month_pct": [2.0]},
            index=["EX.L"],
        )
        ideas = digest.build_alpha_view(frame, {"Industrials": frame}, frame, pd.DataFrame(), {}, [], [])

        self.assertEqual(ideas[2]["title"], "No verified 14-day catalyst")
        self.assertIn("No investment hypothesis is asserted", ideas[2]["thesis"])

    def test_delivery_validation_rejects_stale_market_tape(self):
        frame = pd.DataFrame(
            {"as_of": ["2026-08-04"] * 100, "day_pct": [0.0] * 100},
            index=[f"T{i}.L" for i in range(100)],
        )
        with self.assertRaisesRegex(ValueError, "stale"):
            digest.validate_delivery(
                {"FTSE 100": frame},
                now=digest.datetime(2026, 8, 5, 16, 40).astimezone(),
            )

    def test_delivery_validation_accepts_complete_same_day_tape(self):
        frame = pd.DataFrame(
            {"as_of": ["2026-08-05"] * 100, "day_pct": [0.0] * 100},
            index=[f"T{i}.L" for i in range(100)],
        )
        result = digest.validate_delivery(
            {"FTSE 100": frame},
            now=digest.datetime(2026, 8, 5, 16, 40).astimezone(),
        )
        self.assertEqual(result, "2026-08-05")

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
