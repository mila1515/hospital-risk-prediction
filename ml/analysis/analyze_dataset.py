"""Generate a reproducible exploratory data analysis report."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


NUMERIC_FEATURES = [
    "age",
    "temperature_c",
    "systolic_bp",
    "diastolic_bp",
    "spo2",
    "heart_rate",
    "glucose_mg_dl",
    "pain_score",
    "risk_score",
]
REQUIRED_COLUMNS = ["patient_id", "recorded_at", "admission_type", "risk_level", *NUMERIC_FEATURES]
RISK_ORDER = ["Low", "Medium", "High", "Critical"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="analyze_dataset")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/processed/patient_vitals_processed.csv"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("reports/eda"))
    return parser.parse_args()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_schema(df: pd.DataFrame) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def build_summary(df: pd.DataFrame, input_path: Path) -> dict[str, object]:
    class_counts = df["risk_level"].value_counts().reindex(RISK_ORDER, fill_value=0)
    class_share = (class_counts / len(df)).round(4) if len(df) else class_counts.astype(float)
    correlations = df[NUMERIC_FEATURES].corr(numeric_only=True)["risk_score"].drop("risk_score")

    return {
        "dataset": {
            "path": input_path.as_posix(),
            "sha256": file_sha256(input_path),
            "rows": int(len(df)),
            "columns": int(len(df.columns)),
            "duplicate_rows": int(df.duplicated().sum()),
            "duplicate_patient_timestamps": int(df.duplicated(["patient_id", "recorded_at"]).sum()),
        },
        "missing_values": {column: int(value) for column, value in df.isna().sum().items()},
        "class_distribution": {
            level: {"count": int(class_counts[level]), "share": float(class_share[level])}
            for level in RISK_ORDER
        },
        "numeric_summary": df[NUMERIC_FEATURES].describe().round(3).to_dict(),
        "correlation_with_rule_based_risk_score": {
            column: float(value) for column, value in correlations.abs().sort_values(ascending=False).items()
        },
        "methodology_warning": (
            "risk_level is derived from risk_score using deterministic clinical-style rules. "
            "It is not an independently observed clinical outcome."
        ),
    }


def build_html_report(df: pd.DataFrame, output_path: Path) -> None:
    payload = {
        "classes": RISK_ORDER,
        "counts": [int((df["risk_level"] == level).sum()) for level in RISK_ORDER],
        "rows": df[["risk_level", "risk_score", "spo2", "heart_rate", "systolic_bp", "age"]]
        .to_dict(orient="records"),
    }
    data_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Hospital Risk Prediction — EDA</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #f7f9fc; color: #172033; }}
    .warning {{ padding: 1rem; background: #fff4d6; border-left: 4px solid #e7a400; margin-bottom: 1rem; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(440px, 1fr)); gap: 1rem; }}
    .chart {{ min-height: 390px; background: white; border-radius: 10px; box-shadow: 0 2px 10px #0001; }}
  </style>
</head>
<body>
  <h1>Hospital Risk Prediction — Exploratory Data Analysis</h1>
  <div class="warning"><strong>Methodology warning:</strong> risk_level is a rule-based proxy, not an observed clinical outcome.</div>
  <div class="grid"><div id="classes" class="chart"></div><div id="scores" class="chart"></div>
  <div id="spo2" class="chart"></div><div id="vitals" class="chart"></div></div>
  <script>
    const data = {data_json};
    const colors = {{Low:'#2ca02c', Medium:'#ffbf00', High:'#ff7f0e', Critical:'#d62728'}};
    Plotly.newPlot('classes', [{{type:'bar', x:data.classes, y:data.counts, marker:{{color:data.classes.map(x=>colors[x])}}}}],
      {{title:'Class balance', xaxis:{{title:'Risk level'}}, yaxis:{{title:'Rows'}}}}, {{responsive:true}});
    const byClass = level => data.rows.filter(row => row.risk_level === level);
    Plotly.newPlot('scores', data.classes.map(level => ({{type:'histogram', name:level, opacity:.7,
      x:byClass(level).map(row=>row.risk_score), marker:{{color:colors[level]}}}})),
      {{title:'Risk score by class', barmode:'overlay', xaxis:{{title:'Risk score'}}}}, {{responsive:true}});
    Plotly.newPlot('spo2', data.classes.map(level => ({{type:'box', name:level,
      y:byClass(level).map(row=>row.spo2), marker:{{color:colors[level]}}}})),
      {{title:'SpO2 by risk class', yaxis:{{title:'SpO2 (%)'}}}}, {{responsive:true}});
    Plotly.newPlot('vitals', data.classes.map(level => ({{type:'scatter', mode:'markers', name:level,
      x:byClass(level).map(row=>row.heart_rate), y:byClass(level).map(row=>row.systolic_bp),
      text:byClass(level).map(row=>`Age: ${{row.age}}<br>Risk score: ${{row.risk_score}}`),
      marker:{{color:colors[level], size:8, opacity:.75}}}})),
      {{title:'Heart rate vs systolic blood pressure', xaxis:{{title:'Heart rate'}}, yaxis:{{title:'Systolic BP'}}}},
      {{responsive:true}});
  </script>
</body>
</html>"""
    output_path.write_text(html, encoding="utf-8")


def main() -> None:
    args = parse_args()
    if not args.input.exists():
        raise SystemExit(f"Input CSV not found: {args.input.as_posix()}")

    df = pd.read_csv(args.input)
    validate_schema(df)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = args.output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(build_summary(df, args.input), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    html_path = args.output_dir / "eda_report.html"
    build_html_report(df, html_path)

    print(f"Wrote EDA summary to: {summary_path.as_posix()}")
    print(f"Wrote interactive EDA report to: {html_path.as_posix()}")


if __name__ == "__main__":
    main()
