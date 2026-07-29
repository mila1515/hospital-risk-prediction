import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class TransformConfig:
    input_csv: Path
    output_csv: Path


def parse_args() -> TransformConfig:
    p = argparse.ArgumentParser(prog="transform_patient_vitals")
    p.add_argument("--input", type=Path, default=Path("data/raw/patient_vitals_mimic_demo_raw.csv"))
    p.add_argument("--output", type=Path, default=Path("data/processed/patient_vitals_processed.csv"))
    args = p.parse_args()
    return TransformConfig(input_csv=args.input, output_csv=args.output)


def coerce_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def clip_ranges(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["age"] = out["age"].clip(lower=0, upper=120)
    out["temperature_c"] = out["temperature_c"].clip(lower=30, upper=45)
    out["systolic_bp"] = out["systolic_bp"].clip(lower=50, upper=260)
    out["diastolic_bp"] = out["diastolic_bp"].clip(lower=20, upper=160)
    out["spo2"] = out["spo2"].clip(lower=50, upper=100)
    out["heart_rate"] = out["heart_rate"].clip(lower=20, upper=250)
    out["glucose_mg_dl"] = out["glucose_mg_dl"].clip(lower=20, upper=800)
    out["pain_score"] = out["pain_score"].clip(lower=0, upper=10)
    return out


def impute_medians(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        med = float(out[c].median(skipna=True)) if out[c].notna().any() else np.nan
        out[c] = out[c].fillna(med)
    return out


def compute_risk_score(row: pd.Series) -> int:
    score = 0

    age = row["age"]
    temp = row["temperature_c"]
    sys_bp = row["systolic_bp"]
    dia_bp = row["diastolic_bp"]
    spo2 = row["spo2"]
    hr = row["heart_rate"]
    glu = row["glucose_mg_dl"]
    pain = row["pain_score"]

    if age >= 80:
        score += 2
    elif age >= 65:
        score += 1

    if temp >= 39:
        score += 3
    elif temp >= 38:
        score += 2
    elif temp < 36:
        score += 2

    if sys_bp < 90:
        score += 3
    elif sys_bp > 180:
        score += 2

    if dia_bp < 60:
        score += 1
    elif dia_bp > 120:
        score += 1

    if spo2 < 90:
        score += 4
    elif spo2 < 94:
        score += 2

    if hr > 140:
        score += 3
    elif hr > 120:
        score += 2
    elif hr < 50:
        score += 2

    if glu > 300:
        score += 3
    elif glu > 200:
        score += 2
    elif glu < 70:
        score += 2

    if pain >= 7:
        score += 1

    return int(score)


def compute_risk_level(score: int) -> str:
    if score >= 10:
        return "Critical"
    if score >= 7:
        return "High"
    if score >= 4:
        return "Medium"
    return "Low"


def main() -> None:
    cfg = parse_args()
    cfg.output_csv.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(cfg.input_csv)

    df["recorded_at"] = pd.to_datetime(df["recorded_at"], errors="coerce")
    df = df.dropna(subset=["patient_id", "recorded_at"])

    numeric_cols = [
        "age",
        "temperature_c",
        "systolic_bp",
        "diastolic_bp",
        "spo2",
        "heart_rate",
        "glucose_mg_dl",
        "pain_score",
    ]
    df = coerce_numeric(df, numeric_cols)
    df = clip_ranges(df)

    df = df.sort_values(["patient_id", "recorded_at"])
    df = df.drop_duplicates(subset=["patient_id", "recorded_at"], keep="last")

    df = impute_medians(df, numeric_cols)

    df["risk_score"] = df.apply(compute_risk_score, axis=1)
    df["risk_level"] = df["risk_score"].map(compute_risk_level)

    out_cols = [
        "patient_id",
        "recorded_at",
        "age",
        "temperature_c",
        "systolic_bp",
        "diastolic_bp",
        "spo2",
        "heart_rate",
        "glucose_mg_dl",
        "pain_score",
        "admission_type",
        "risk_score",
        "risk_level",
    ]
    out = df[out_cols].reset_index(drop=True)
    out.to_csv(cfg.output_csv, index=False)

    print(f"Wrote {len(out):,} rows to {cfg.output_csv.as_posix()}")
    print("risk_level distribution:", out["risk_level"].value_counts(dropna=False).to_dict())


if __name__ == "__main__":
    main()
