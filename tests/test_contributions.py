import unittest
from datetime import date, timedelta
from unittest.mock import patch
from xml.etree import ElementTree

from scripts.generate_contributions import activity_card, fetch_days, streak_card, streaks


class ContributionTests(unittest.TestCase):
    def test_current_streak_survives_unfinished_today(self):
        today = date(2026, 1, 2)
        days = {today - timedelta(days=2): 3, today - timedelta(days=1): 2, today: 0}
        self.assertEqual(streaks(days, today), (2, 2))

    def test_inactive_yesterday_breaks_current_streak(self):
        today = date(2026, 9, 22)
        days = {today - timedelta(days=3): 1, today - timedelta(days=2): 2, today: 0}
        self.assertEqual(streaks(days, today), (0, 2))

    def test_leap_day_and_year_boundary_are_consecutive(self):
        leap_days = {date(2024, 2, 28): 1, date(2024, 2, 29): 3, date(2024, 3, 1): 2}
        self.assertEqual(streaks(leap_days, date(2024, 3, 1)), (3, 3))
        new_year = {date(2025, 12, 31): 1, date(2026, 1, 1): 1}
        self.assertEqual(streaks(new_year, date(2026, 1, 1)), (2, 2))

    def test_zero_activity_is_valid_svg(self):
        today = date(2026, 9, 22)
        days = {today: 0}
        for svg in (activity_card(days, today), streak_card(days, today)):
            root = ElementTree.fromstring(svg)
            self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
            self.assertNotIn("nan", svg.lower())
        self.assertEqual(streaks(days, today), (0, 0))

    def test_activity_uses_exactly_last_31_days(self):
        today = date(2026, 9, 22)
        svg = activity_card({today: 7, today - timedelta(days=31): 9999}, today)
        root = ElementTree.fromstring(svg)
        circles = root.findall(".//{http://www.w3.org/2000/svg}circle")
        self.assertEqual(len(circles), 31)
        self.assertIn("2026-09-22: 7", svg)
        self.assertNotIn("9999", svg)

    @patch("scripts.generate_contributions.graphql")
    def test_partial_calendar_is_rejected(self, graphql):
        graphql.side_effect = [
            {"createdAt": "2026-01-01T00:00:00Z"},
            {"contributionsCollection": {"contributionCalendar": {"weeks": []}}},
        ]
        with self.assertRaisesRegex(RuntimeError, "Incomplete"):
            fetch_days("slacker007", date(2026, 1, 2))


if __name__ == "__main__":
    unittest.main()
