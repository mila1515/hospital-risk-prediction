import unittest

import pandas as pd

from etl.transform.transform_waiting_times import OUTPUT_COLUMNS, transform_waiting_times


def source_row(**changes):
    row = {
        "Month": 202601,
        "HBT": "BOARD1",
        "TreatmentLocation": "SITE1",
        "DepartmentType": "Type 1",
        "AttendanceCategory": "Unplanned",
        "NumberOfAttendancesAll": 100,
        "NumberWithin4HoursAll": 80,
        "NumberOver4HoursAll": 20,
        "NumberOver8HoursEpisode": 5,
        "NumberOver12HoursEpisode": 1,
    }
    row.update(changes)
    return row


class WaitingTimeTransformTests(unittest.TestCase):
    def test_keeps_only_type_1_unplanned_rows(self):
        raw = pd.DataFrame(
            [
                source_row(),
                source_row(DepartmentType="Type 3"),
                source_row(AttendanceCategory="All"),
            ]
        )

        result = transform_waiting_times(raw)

        self.assertEqual(len(result), 1)
        self.assertEqual(list(result.columns), OUTPUT_COLUMNS)

    def test_aggregates_duplicates_and_calculates_weighted_rate(self):
        raw = pd.DataFrame(
            [
                source_row(),
                source_row(
                    NumberOfAttendancesAll=50,
                    NumberWithin4HoursAll=40,
                    NumberOver4HoursAll=10,
                    NumberOver8HoursEpisode=2,
                    NumberOver12HoursEpisode=1,
                ),
            ]
        )

        result = transform_waiting_times(raw).iloc[0]

        self.assertEqual(result["attendances"], 150)
        self.assertEqual(result["within_4_hours"], 120)
        self.assertEqual(result["over_4_hours"], 30)
        self.assertEqual(result["over_8_hours"], 7)
        self.assertEqual(result["over_12_hours"], 2)

    def test_rejects_inconsistent_four_hour_totals(self):
        raw = pd.DataFrame([source_row(NumberOver4HoursAll=10)])

        with self.assertRaisesRegex(ValueError, "Inconsistent four-hour totals"):
            transform_waiting_times(raw)

    def test_rejects_missing_columns(self):
        raw = pd.DataFrame([source_row()]).drop(columns=["NumberWithin4HoursAll"])

        with self.assertRaisesRegex(ValueError, "Missing required columns"):
            transform_waiting_times(raw)


if __name__ == "__main__":
    unittest.main()
