import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import joblib
import pandas as pd
import plotly.express as px
import psycopg2
import streamlit as st


@dataclass(frozen=True)
class PgConfig:
    host: str
    port: int
    database: str
    user: str
    password: str | None


def _pg_config_from_env() -> PgConfig:
    pw = os.getenv("PGPASSWORD")
    if pw is not None and pw.strip() == "":
        pw = None
    return PgConfig(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        database=os.getenv("PGDATABASE", "hospital"),
        user=os.getenv("PGUSER", "postgres"),
        password=pw,
    )


def _connect(cfg: PgConfig):
    dsn = os.getenv("DATABASE_URL")
    if dsn:
        return psycopg2.connect(dsn, connect_timeout=5)
    kwargs: dict[str, object] = dict(
        host=cfg.host,
        port=cfg.port,
        dbname=cfg.database,
        user=cfg.user,
        connect_timeout=5,
    )
    if cfg.password is not None:
        kwargs["password"] = cfg.password
    return psycopg2.connect(**kwargs)


@st.cache_data(ttl=300)
def load_table(query: str) -> pd.DataFrame:
    cfg = _pg_config_from_env()
    with _connect(cfg) as conn:
        return pd.read_sql_query(query, conn)


def _load_model():
    model_path = Path("ml/models/risk_model.joblib")
    if not model_path.exists():
        return None
    return joblib.load(model_path)


def _patient_vitals_section():
    st.subheader("Patient Risk (patient_vitals)")

    df = load_table(
        """
        SELECT
          patient_id,
          recorded_at,
          age,
          temperature_c,
          systolic_bp,
          diastolic_bp,
          spo2,
          heart_rate,
          glucose_mg_dl,
          pain_score,
          admission_type,
          risk_score,
          risk_level
        FROM public.patient_vitals
        ORDER BY recorded_at
        """
    )
    df["recorded_at"] = pd.to_datetime(df["recorded_at"], errors="coerce")
    st.metric("Patients (rows)", f"{len(df):,}")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.plotly_chart(
            px.histogram(
                df,
                x="risk_level",
                category_orders={"risk_level": ["Low", "Medium", "High", "Critical"]},
                title="Distribution des niveaux de risque",
            ),
            use_container_width=True,
        )
    with col2:
        vitals = ["temperature_c", "systolic_bp", "diastolic_bp", "spo2", "heart_rate", "glucose_mg_dl", "pain_score"]
        v = st.selectbox("Feature", vitals, index=0)
        st.plotly_chart(px.histogram(df, x=v, nbins=30, title=f"Distribution: {v}"), use_container_width=True)
    with col3:
        daily = (
            df.assign(day=df["recorded_at"].dt.date)
            .groupby(["day", "risk_level"], as_index=False)
            .size()
            .rename(columns={"size": "count"})
        )
        st.plotly_chart(
            px.area(
                daily,
                x="day",
                y="count",
                color="risk_level",
                category_orders={"risk_level": ["Low", "Medium", "High", "Critical"]},
                title="Évolution du risque (par jour)",
            ),
            use_container_width=True,
        )

    st.divider()
    st.subheader("Prédire un risque (modèle RandomForest)")
    model_blob = _load_model()
    if model_blob is None:
        st.warning("Modèle introuvable: ml/models/risk_model.joblib")
        return

    pipeline = model_blob["pipeline"]
    feature_cols = model_blob["feature_cols"]
    metadata = model_blob.get("metadata", {})
    if metadata.get("selected_model"):
        st.caption(f"Modèle sélectionné par validation croisée : {metadata['selected_model']}")
    if metadata.get("target_type") == "rule_based_proxy":
        st.info(
            "Démonstrateur Data Science : la cible est dérivée de règles appliquées aux constantes vitales. "
            "La prédiction ne constitue pas une validation clinique."
        )

    defaults = df[feature_cols].dropna().tail(50)
    ref = defaults.median(numeric_only=True).to_dict()
    if "admission_type" in defaults.columns and defaults["admission_type"].notna().any():
        ref["admission_type"] = str(defaults["admission_type"].mode().iloc[0])
    else:
        ref["admission_type"] = "ICU"

    with st.form("predict_form"):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            age = st.number_input("Age", min_value=0, max_value=120, value=int(ref.get("age", 60)))
            temperature_c = st.number_input("Température (°C)", value=float(ref.get("temperature_c", 37.0)))
            spo2 = st.number_input("SpO₂ (%)", min_value=0.0, max_value=100.0, value=float(ref.get("spo2", 97.0)))
        with c2:
            systolic_bp = st.number_input("Systolique (mmHg)", value=float(ref.get("systolic_bp", 120.0)))
            diastolic_bp = st.number_input("Diastolique (mmHg)", value=float(ref.get("diastolic_bp", 80.0)))
            heart_rate = st.number_input("Fréquence cardiaque", value=float(ref.get("heart_rate", 80.0)))
        with c3:
            glucose_mg_dl = st.number_input("Glucose (mg/dL)", value=float(ref.get("glucose_mg_dl", 110.0)))
            pain_score = st.number_input("Pain score", min_value=0.0, max_value=10.0, value=float(ref.get("pain_score", 2.0)))
            admission_type = st.text_input("Admission type", value=str(ref.get("admission_type", "ICU")))
        with c4:
            height_cm = st.number_input("Taille (cm)", min_value=0.0, max_value=250.0, value=0.0)
            weight_kg = st.number_input("Poids (kg)", min_value=0.0, max_value=400.0, value=0.0)
            bmi = None
            if height_cm and weight_kg and height_cm > 0:
                bmi = weight_kg / ((height_cm / 100.0) ** 2)
            st.text_input("BMI", value="" if bmi is None else f"{bmi:.1f}", disabled=True)

        submitted = st.form_submit_button("Predict")

    if submitted:
        X = pd.DataFrame(
            [
                {
                    "age": age,
                    "temperature_c": temperature_c,
                    "systolic_bp": systolic_bp,
                    "diastolic_bp": diastolic_bp,
                    "spo2": spo2,
                    "heart_rate": heart_rate,
                    "glucose_mg_dl": glucose_mg_dl,
                    "pain_score": pain_score,
                    "admission_type": admission_type,
                }
            ]
        )[feature_cols]

        pred = pipeline.predict(X)[0]
        st.success(f"Risk level prédit: {pred}")
        st.caption(
            "Taille/Poids/BMI sont affichés pour le questionnaire. Le modèle actuel ne les utilise pas encore dans la prédiction."
        )

        if hasattr(pipeline.named_steps["model"], "predict_proba"):
            proba = pipeline.predict_proba(X)[0]
            labels = list(pipeline.named_steps["model"].classes_)
            dfp = pd.DataFrame({"risk_level": labels, "probability": proba}).sort_values("probability", ascending=False)
            st.plotly_chart(px.bar(dfp, x="risk_level", y="probability", title="Probabilités"), use_container_width=True)

    st.divider()
    st.subheader("Feature importance (modèle)")
    prep = pipeline.named_steps["preprocess"]
    model = pipeline.named_steps["model"]
    if hasattr(prep, "get_feature_names_out") and hasattr(model, "feature_importances_"):
        names = list(prep.get_feature_names_out())
        imp = pd.DataFrame({"feature": names, "importance": model.feature_importances_}).sort_values(
            "importance", ascending=False
        )
        st.plotly_chart(px.bar(imp.head(20), x="importance", y="feature", orientation="h", title="Top 20"), use_container_width=True)


def _ae_waiting_times_section():
    st.subheader("A&E Waiting Times (NHS Scotland)")

    df = load_table(
        """
        SELECT
          month,
          month_date,
          country,
          hbt,
          treatment_location,
          department_type,
          attendance_category,
          number_of_attendances_all,
          number_within_4_hours_all,
          number_over_4_hours_all,
          percentage_within_4_hours_all
        FROM public.ae_waiting_times
        """
    )
    df["month_date"] = pd.to_datetime(df["month_date"], errors="coerce")

    st.metric("Rows", f"{len(df):,}")

    min_d = df["month_date"].min()
    max_d = df["month_date"].max()
    if pd.isna(min_d) or pd.isna(max_d):
        st.warning("Dates manquantes dans ae_waiting_times.")
        return

    filters = st.container()
    with filters:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            dept = st.multiselect("DepartmentType", sorted(df["department_type"].dropna().unique().tolist()), default=["Type 1"])
        with c2:
            cat = st.multiselect(
                "AttendanceCategory",
                sorted(df["attendance_category"].dropna().unique().tolist()),
                default=["Unplanned"],
            )
        with c3:
            start = st.date_input("Start", value=min_d.date())
        with c4:
            end = st.date_input("End", value=max_d.date())

    mask = (df["month_date"].dt.date >= start) & (df["month_date"].dt.date <= end)
    if dept:
        mask &= df["department_type"].isin(dept)
    if cat:
        mask &= df["attendance_category"].isin(cat)
    dff = df.loc[mask].copy()

    monthly = (
        dff.groupby(["month_date", "department_type", "attendance_category"], as_index=False)
        .agg(
            attendances=("number_of_attendances_all", "sum"),
            within4=("number_within_4_hours_all", "sum"),
        )
        .assign(pct_within4=lambda x: (x["within4"] / x["attendances"]) * 100.0)
    )

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(
            px.line(
                monthly,
                x="month_date",
                y="pct_within4",
                color="department_type",
                line_dash="attendance_category",
                title="% within 4 hours (pondéré par volumes)",
            ),
            use_container_width=True,
        )
    with c2:
        top = (
            dff.groupby(["treatment_location"], as_index=False)
            .agg(attendances=("number_of_attendances_all", "sum"), within4=("number_within_4_hours_all", "sum"))
            .assign(pct_within4=lambda x: (x["within4"] / x["attendances"]) * 100.0)
            .sort_values("attendances", ascending=False)
            .head(20)
        )
        st.plotly_chart(
            px.bar(top.sort_values("pct_within4"), x="pct_within4", y="treatment_location", orientation="h", title="Top 20 sites (par volume)"),
            use_container_width=True,
        )


def _cqc_section():
    st.subheader("CQC Adult Inpatient Survey 2024")

    table = st.selectbox(
        "Table",
        ["public.cqc_aip2024_national", "public.cqc_aip2024_trust", "public.cqc_aip2024_site"],
        index=1,
    )
    df = load_table(f"SELECT * FROM {table} LIMIT 5000")
    st.metric("Rows (preview)", f"{len(df):,}")
    st.dataframe(df, use_container_width=True)

    numeric_cols = []
    for c in df.columns:
        s = pd.to_numeric(df[c], errors="coerce")
        if s.notna().sum() >= max(10, int(0.2 * len(df))):
            numeric_cols.append(c)

    if not numeric_cols:
        st.info("Aucune colonne numérique détectée automatiquement sur les 5000 premières lignes.")
        return

    ycol = st.selectbox("Colonne numérique", numeric_cols, index=0)
    s = pd.to_numeric(df[ycol], errors="coerce")
    st.plotly_chart(px.histogram(s.dropna(), nbins=30, title=f"Distribution: {ycol}"), use_container_width=True)


def main():
    st.set_page_config(page_title="Hospital Risk Prediction Dashboard", layout="wide")
    st.title("Hospital Risk Prediction")

    st.sidebar.header("Navigation")
    page = st.sidebar.radio("Page", ["Patient Risk", "A&E Waiting Times", "CQC Survey"], index=0)

    if page == "Patient Risk":
        _patient_vitals_section()
    elif page == "A&E Waiting Times":
        _ae_waiting_times_section()
    else:
        _cqc_section()


if __name__ == "__main__":
    main()
