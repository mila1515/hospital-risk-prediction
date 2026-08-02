import unittest

import pandas as pd

from dashboard.streamlit_app import aggregate_monthly, aggregate_sites, weighted_rate
from dashboard.site_names import site_label


class DashboardAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.data = pd.DataFrame(
            [
                {
                    "month_date": pd.Timestamp("2026-01-01"),
                    "health_board_code": "BOARD1",
                    "site_code": "SITE1",
                    "attendances": 100,
                    "within_4_hours": 90,
                    "over_4_hours": 10,
                    "over_8_hours": 3,
                    "over_12_hours": 1,
                },
                {
                    "month_date": pd.Timestamp("2026-01-01"),
                    "health_board_code": "BOARD1",
                    "site_code": "SITE2",
                    "attendances": 50,
                    "within_4_hours": 30,
                    "over_4_hours": 20,
                    "over_8_hours": 5,
                    "over_12_hours": 2,
                },
            ]
        )

    def test_weighted_rate_uses_attendance_volumes(self):
        self.assertAlmostEqual(weighted_rate(self.data), 80.0)

    def test_monthly_aggregation_preserves_totals(self):
        monthly = aggregate_monthly(self.data).iloc[0]
        self.assertEqual(monthly["attendances"], 150)
        self.assertEqual(monthly["over_4_hours"], 30)
        self.assertAlmostEqual(monthly["pct_within_4_hours"], 80.0)

    def test_site_ranking_prioritizes_number_over_four_hours(self):
        sites = aggregate_sites(self.data)
        self.assertEqual(sites.iloc[0]["site_code"], "SITE2")

    def test_zero_attendances_returns_zero_rate(self):
        empty_volume = self.data.copy()
        empty_volume[["attendances", "within_4_hours", "over_4_hours"]] = 0
        self.assertEqual(weighted_rate(empty_volume), 0.0)

    def test_site_label_includes_name_and_source_code(self):
        self.assertEqual(site_label("N101H"), "Aberdeen Royal Infirmary (N101H)")

    def test_site_label_falls_back_to_unknown_code(self):
        self.assertEqual(site_label("UNKNOWN"), "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
