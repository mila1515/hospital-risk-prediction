import unittest
from pathlib import Path

import pandas as pd

from etl.transform.transform_patient_vitals import compute_risk_level


class ProcessedDataQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = Path("data/processed/patient_vitals_processed.csv")
        if not cls.path.exists():
            raise unittest.SkipTest(f"Processed dataset not found: {cls.path}")
        cls.df = pd.read_csv(cls.path)

    def test_patient_timestamp_key_is_unique(self):
        self.assertEqual(int(self.df.duplicated(["patient_id", "recorded_at"]).sum()), 0)

    def test_model_features_have_no_missing_values(self):
        features = [
            "age", "temperature_c", "systolic_bp", "diastolic_bp", "spo2",
            "heart_rate", "glucose_mg_dl", "pain_score", "admission_type",
        ]
        self.assertFalse(self.df[features].isna().any().any())

    def test_risk_label_matches_documented_score_rules(self):
        expected = self.df["risk_score"].map(compute_risk_level)
        pd.testing.assert_series_equal(expected, self.df["risk_level"], check_names=False)


if __name__ == "__main__":
    unittest.main()
