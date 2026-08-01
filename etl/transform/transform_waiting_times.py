from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_INPUT = Path("data/raw/nhs_scotland/monthly_ae_activity_waiting_times.csv")
DEFAULT_OUTPUT = Path("data/processed/waiting_times_processed.csv")

REQUIRED_COLUMNS = [
    "Month",
    "HBT",
    "TreatmentLocation",
    "DepartmentType",
    "AttendanceCategory",
    "NumberOfAttendancesAll",
    "NumberWithin4HoursAll",
    "NumberOver4HoursAll",
    "NumberOver8HoursEpisode",
    "NumberOver12HoursEpisode",
]

OUTPUT_COLUMNS = [
    "month_date",
    "health_board_code",
    "site_code",
    "attendances",
    "within_4_hours",
    "over_4_hours",
    "over_8_hours",
    "over_12_hours",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare Type 1 unplanned A&E waiting-time data for analysis."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def transform_waiting_times(raw: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in REQUIRED_COLUMNS if column not in raw.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    filtered = raw.loc[
        (raw["DepartmentType"] == "Type 1")
        & (raw["AttendanceCategory"] == "Unplanned"),
        REQUIRED_COLUMNS,
    ].copy()
    if filtered.empty:
        raise ValueError("No Type 1 unplanned attendance rows were found")

    filtered = filtered.rename(
        columns={
            "Month": "month_date",
            "HBT": "health_board_code",
            "TreatmentLocation": "site_code",
            "NumberOfAttendancesAll": "attendances",
            "NumberWithin4HoursAll": "within_4_hours",
            "NumberOver4HoursAll": "over_4_hours",
            "NumberOver8HoursEpisode": "over_8_hours",
            "NumberOver12HoursEpisode": "over_12_hours",
        }
    )
    filtered["month_date"] = pd.to_datetime(
        filtered["month_date"].astype("string"), format="%Y%m", errors="coerce"
    )

    count_columns = [
        "attendances",
        "within_4_hours",
        "over_4_hours",
        "over_8_hours",
        "over_12_hours",
    ]
    for column in count_columns:
        filtered[column] = pd.to_numeric(filtered[column], errors="coerce")

    filtered = filtered.dropna(
        subset=[
            "month_date",
            "health_board_code",
            "site_code",
            "attendances",
            "within_4_hours",
            "over_4_hours",
        ]
    )
    if (filtered[["attendances", "within_4_hours", "over_4_hours"]] < 0).any().any():
        raise ValueError("Attendance counts cannot be negative")

    grouped = (
        filtered.groupby(
            ["month_date", "health_board_code", "site_code"], as_index=False, dropna=False
        )[count_columns]
        .sum(min_count=1)
        .sort_values(["month_date", "health_board_code", "site_code"])
        .reset_index(drop=True)
    )

    inconsistent = grouped["within_4_hours"] + grouped["over_4_hours"] != grouped["attendances"]
    if inconsistent.any():
        raise ValueError(f"Inconsistent four-hour totals in {int(inconsistent.sum())} rows")

    for column in count_columns:
        grouped[column] = grouped[column].astype("Int64")

    return grouped[OUTPUT_COLUMNS]


def main() -> None:
    args = parse_args()
    if not args.input.exists():
        raise SystemExit(f"Input CSV not found: {args.input.as_posix()}")

    processed = transform_waiting_times(pd.read_csv(args.input))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    processed.to_csv(args.output, index=False, date_format="%Y-%m-%d")
    print(f"Prepared {len(processed):,} rows")
    print(f"Saved processed data to: {args.output.as_posix()}")


if __name__ == "__main__":
    main()
