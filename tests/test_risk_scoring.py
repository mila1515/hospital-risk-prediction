import unittest

import pandas as pd

from etl.transform.transform_patient_vitals import compute_risk_level, compute_risk_score


class RiskScoringTests(unittest.TestCase):
    def setUp(self):
        self.normal = {
            "age": 40,
            "temperature_c": 37.0,
            "systolic_bp": 120,
            "diastolic_bp": 80,
            "spo2": 98,
            "heart_rate": 75,
            "glucose_mg_dl": 100,
            "pain_score": 0,
        }

    def score(self, **changes):
        row = {**self.normal, **changes}
        return compute_risk_score(pd.Series(row))

    def test_normal_vitals_have_zero_score(self):
        self.assertEqual(self.score(), 0)

    def test_low_spo2_is_heavily_weighted(self):
        self.assertEqual(self.score(spo2=89), 4)

    def test_multiple_alerts_accumulate(self):
        self.assertEqual(self.score(age=82, temperature_c=39.2, systolic_bp=85, spo2=88), 12)

    def test_risk_level_boundaries(self):
        expected = {0: "Low", 3: "Low", 4: "Medium", 6: "Medium", 7: "High", 9: "High", 10: "Critical"}
        for score, level in expected.items():
            with self.subTest(score=score):
                self.assertEqual(compute_risk_level(score), level)


if __name__ == "__main__":
    unittest.main()
