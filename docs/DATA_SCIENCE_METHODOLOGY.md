# Data Science Methodology

## Analytical question

The current experiment asks: **how well can standard classifiers reproduce the rule-based patient risk level from vital signs?**

This is intentionally narrower than predicting deterioration, mortality, readmission, or ICU transfer. The current target, `risk_level`, is calculated from `risk_score` in the transformation pipeline. It is therefore a **rule-based proxy**, not an independently observed clinical outcome.

## Dataset

- Source: MIMIC-IV Demo-derived initial ICU measurements.
- Unit of analysis: one initial observation per ICU stay in the extracted dataset.
- Features: age, temperature, blood pressure, SpO2, heart rate, glucose, pain score, and admission type.
- Target: `Low`, `Medium`, `High`, or `Critical` risk class.

The EDA command records the dataset SHA256, dimensions, missingness, duplicates, descriptive statistics, class balance, and correlations:

```bash
python ml/analysis/analyze_dataset.py
```

Outputs:

- `reports/eda/summary.json`
- `reports/eda/eda_report.html`

## Experimental design

The training command compares three models:

1. Most-frequent dummy classifier as the minimum baseline.
2. Class-balanced logistic regression as an interpretable linear baseline.
3. Class-balanced random forest for nonlinear relationships.

Model selection uses stratified cross-validation on the training partition. The primary metric is macro F1 because all four risk classes matter and the dataset is imbalanced. Accuracy, balanced accuracy, and weighted F1 are also reported. A stratified holdout set is kept for the final evaluation.

```bash
python ml/training/train_risk_model.py
```

Outputs:

- `reports/model/model_comparison.csv`
- `reports/model/metrics.json`
- `reports/model/confusion_matrix.csv`
- `reports/model/holdout_predictions.csv`
- `reports/model/feature_importance.csv` when supported
- `ml/models/risk_model.joblib`

Every model artifact contains its feature contract, selected model name, target type, dataset hash, and holdout metrics.

## Interpretation limits

- High scores do not establish clinical validity because the label is derived from the predictors.
- The demo dataset is small, especially for `High` and `Critical` cases.
- Median imputation and clipping are pragmatic preprocessing choices that require clinical review.
- The model must not be used for diagnosis or patient-care decisions.

## Path toward a genuine clinical prediction project

Replace the proxy target with a temporally valid observed outcome, for example deterioration within 24 hours, ICU mortality, unexpected ICU transfer, or readmission. Features must be restricted to information available before the prediction time. Evaluation should then use patient-level or temporal splits, confidence intervals, calibration metrics, subgroup analysis, and external validation.
