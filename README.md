# Hospital Risk Prediction 🏥🤖

ETL and AI-powered healthcare analytics system for patient risk prediction, hospital monitoring, and intelligent decision support.

---

# 📌 Project Overview

This repository contains a healthcare analytics pipeline built with Python to:

* Extract and transform patient vitals data
* Load cleaned data into PostgreSQL
* Train a risk prediction model
* Visualize results with a Streamlit dashboard

The system combines:

* Data Engineering
* Machine Learning
* Healthcare Analytics
* Dashboarding

---

# 🎯 Problem Statement

Hospitals collect massive amounts of patient data every day:

* Vital signs
* Medical measurements
* Patient surveys
* Admission details

These data are often:

* fragmented
* underutilized
* manually processed
* difficult to analyze quickly

This project automates the workflow from raw medical records to risk scoring and dashboard monitoring.

---

# ✅ Solution

The platform provides:

✔ A Python-based ETL pipeline
✔ Risk score calculation and classification
✔ Machine Learning risk prediction
✔ PostgreSQL storage for analytics
✔ Streamlit dashboard for visualization

---

# 🏗 System Architecture

```text
Patient data files / Public demo datasets
            ↓
       Python ETL scripts
 (extract / transform / load)
            ↓
      PostgreSQL database
            ↓
   Machine Learning training
            ↓
    Streamlit dashboard app
```

---

# 🧠 Machine Learning

## Objective

Predict patient risk level based on vital signs and admission metadata.

---

## Input Features

* age
* temperature_c
* systolic_bp
* diastolic_bp
* spo2
* heart_rate
* glucose_mg_dl
* pain_score
* admission_type

---

## Target

Risk classification:

* Low
* Medium
* High
* Critical

---

## ML Implementation

### Implemented

* Reproducible exploratory analysis with JSON and interactive HTML reports
* Dummy baseline, class-balanced Logistic Regression, and Random Forest comparison
* Stratified cross-validation and holdout evaluation
* Macro F1, balanced accuracy, weighted F1, confusion matrix, and feature importance
* Model and dataset traceability through metadata and SHA256 fingerprints

> **Methodology note:** the current `risk_level` is generated from deterministic rules applied to the same vital signs used by the models. The experiment therefore measures rule reproduction, not the prediction of an independently observed clinical outcome. See `docs/DATA_SCIENCE_METHODOLOGY.md`.

### Possible Extensions

* Logistic Regression
* XGBoost
* LightGBM
* Model explainability

---

# 🔄 ETL Pipeline

## Extract

The extraction script builds raw patient vitals data from the MIMIC-IV Demo dataset and can optionally download open data sources for hospital KPI analysis.

Script: `etl/extract/build_raw_from_mimic_iv_demo.py`

## Transform

The transformation script cleans and normalizes vitals, imputes missing values, computes a risk score, and assigns a risk level.

Script: `etl/transform/transform_patient_vitals.py`

## Load

The load script inserts cleaned CSV data into PostgreSQL and supports multiple dataset types including `patient_vitals`.

Script: `etl/load/load_patient_vitals_to_postgres.py`

---

# 📊 Dashboard

The dashboard is built with Streamlit and reads from PostgreSQL.

File: `dashboard/streamlit_app.py`

Dashboard features:

* Patient risk distribution
* Vital sign histograms
* Daily risk trends
* Interactive risk prediction form
* Model probability visualization

---

# 🛠 Tech Stack

| Category         | Technology                |
| ---------------- | ------------------------- |
| Programming      | Python                    |
| Data Analysis    | Pandas, NumPy             |
| Machine Learning | scikit-learn              |
| Database         | PostgreSQL                |
| ETL              | Python scripts            |
| Dashboard        | Streamlit, Plotly         |
| Version Control  | Git                       |

---

# 📁 Project Structure

```text
hospital-risk-prediction/
│
├── data/
│   ├── raw/
│   └── processed/
│
├── etl/
│   ├── extract/
│   ├── transform/
│   └── load/
│
├── database/
├── docs/
├── dashboard/
│   └── streamlit_app.py
├── ml/
│   ├── models/
│   └── training/
├── notebooks/
├── requirements.txt
├── README.md
└── docker-compose.yml
```

---

# 📚 Data Sources

## Supported / referenced sources

* MIMIC-IV Demo (PhysioNet)
* NHS Scotland A&E open data
* CQC Adult Inpatient Survey 2024 open data

---

# 🚀 Getting Started

## 1. Clone the repository

```bash
git clone https://github.com/your-username/hospital-risk-prediction.git
cd hospital-risk-prediction
```

## 2. Create a virtual environment

```bash
python -m venv venv
```

### Activate environment

#### Windows (PowerShell)

```powershell
.\venv\Scripts\Activate.ps1
```

#### Linux / macOS

```bash
source venv/bin/activate
```

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

# ▶️ Run the pipeline

## Extract raw data

```bash
python etl/extract/build_raw_from_mimic_iv_demo.py
```

## Transform cleaned data

```bash
python etl/transform/transform_patient_vitals.py
```

## Load into PostgreSQL

```bash
python etl/load/load_patient_vitals_to_postgres.py --csv data/processed/patient_vitals_processed.csv --dataset patient_vitals
```

> Set `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, and `PGPASSWORD` if you use a custom PostgreSQL instance.

---

# 🧪 Train the model

## Generate the exploratory analysis

```bash
python ml/analysis/analyze_dataset.py
```

This creates `reports/eda/summary.json` and an interactive report at
`reports/eda/eda_report.html`.

## Compare and train models

```bash
python ml/training/train_risk_model.py --input data/processed/patient_vitals_processed.csv --model-out ml/models/risk_model.joblib
```

Evaluation artifacts are written to `reports/model/`. Model selection is based on
cross-validated macro F1 to account for class imbalance.

## Run tests

```bash
python -m unittest discover -s tests -v
```

---

# 📈 Run the dashboard

```bash
streamlit run dashboard/streamlit_app.py
```

The app reads from PostgreSQL and loads `ml/models/risk_model.joblib` for the prediction form.

---

# 🔐 Data Privacy

This project uses:

* public datasets
* anonymized or demo patient data
* simulated hospital metrics

No sensitive personal medical data is included.

---

# 📌 Project Goals

This project demonstrates skills in:

* Data engineering
* ETL workflows
* Machine learning
* Dashboard development
* Healthcare analytics

---

# 👨‍💻 Author

Data & AI student passionate about:

* healthcare innovation
* intelligent systems
* predictive analytics
* data-driven decision making

---

# ⭐ Potential Use Cases

* Hospitals
* Clinics
* Healthcare analytics platforms
* Smart monitoring systems
* Medical decision support systems

