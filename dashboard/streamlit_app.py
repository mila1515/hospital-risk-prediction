from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import psycopg2
import streamlit as st

from dashboard.site_names import site_label


DEFAULT_CSV = Path("data/processed/waiting_times_processed.csv")


@dataclass(frozen=True)
class PgConfig:
    host: str
    port: int
    database: str
    user: str
    password: str | None


def pg_config_from_env() -> PgConfig:
    password = os.getenv("PGPASSWORD") or None
    return PgConfig(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        database=os.getenv("PGDATABASE", "hospital"),
        user=os.getenv("PGUSER", "postgres"),
        password=password,
    )


@st.cache_data(ttl=300)
def load_waiting_times() -> tuple[pd.DataFrame, str]:
    config = pg_config_from_env()
    source = "PostgreSQL"
    try:
        with psycopg2.connect(
            host=config.host,
            port=config.port,
            dbname=config.database,
            user=config.user,
            password=config.password,
            connect_timeout=3,
        ) as connection:
            data = pd.read_sql_query(
                """
                SELECT
                    month_date,
                    health_board_code,
                    site_code,
                    attendances,
                    within_4_hours,
                    over_4_hours,
                    over_8_hours,
                    over_12_hours
                FROM public.ae_waiting_times
                ORDER BY month_date, health_board_code, site_code
                """,
                connection,
            )
    except Exception as database_error:
        if not DEFAULT_CSV.exists():
            raise RuntimeError(
                "PostgreSQL is unavailable and the processed CSV does not exist. Run the ETL pipeline first."
            ) from database_error
        data = pd.read_csv(DEFAULT_CSV)
        source = "CSV local (mode sans PostgreSQL)"

    data["month_date"] = pd.to_datetime(data["month_date"], errors="coerce")
    return data.dropna(subset=["month_date"]), source


def aggregate_monthly(data: pd.DataFrame) -> pd.DataFrame:
    monthly = (
        data.groupby("month_date", as_index=False)[
            [
                "attendances",
                "within_4_hours",
                "over_4_hours",
                "over_8_hours",
                "over_12_hours",
            ]
        ]
        .sum(min_count=1)
        .sort_values("month_date")
    )
    monthly["pct_within_4_hours"] = (
        monthly["within_4_hours"].div(monthly["attendances"]).mul(100)
    )
    return monthly


def aggregate_sites(data: pd.DataFrame) -> pd.DataFrame:
    sites = (
        data.groupby(["health_board_code", "site_code"], as_index=False)[
            ["attendances", "within_4_hours", "over_4_hours", "over_8_hours", "over_12_hours"]
        ]
        .sum(min_count=1)
    )
    sites["pct_within_4_hours"] = sites["within_4_hours"].div(sites["attendances"]).mul(100)
    return sites.sort_values("over_4_hours", ascending=False)


def weighted_rate(data: pd.DataFrame) -> float:
    attendances = float(data["attendances"].sum())
    if attendances == 0:
        return 0.0
    return float(data["within_4_hours"].sum()) / attendances * 100


def apply_filters(data: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("Filtres")
    minimum = data["month_date"].min().date()
    maximum = data["month_date"].max().date()
    default_start = max(minimum, (data["month_date"].max() - pd.DateOffset(months=23)).date())

    start_date = st.sidebar.date_input("Début", value=default_start, min_value=minimum, max_value=maximum)
    end_date = st.sidebar.date_input("Fin", value=maximum, min_value=minimum, max_value=maximum)
    if start_date > end_date:
        st.sidebar.error("La date de début doit précéder la date de fin.")
        return data.iloc[0:0]

    boards = sorted(data["health_board_code"].dropna().unique().tolist())
    selected_boards = st.sidebar.multiselect("Organismes hospitaliers", boards, default=boards)

    available_sites = sorted(
        data.loc[data["health_board_code"].isin(selected_boards), "site_code"].dropna().unique().tolist()
    )
    selected_sites = st.sidebar.multiselect(
        "Sites",
        available_sites,
        default=available_sites,
        format_func=site_label,
    )

    mask = (
        data["month_date"].dt.date.between(start_date, end_date)
        & data["health_board_code"].isin(selected_boards)
        & data["site_code"].isin(selected_sites)
    )
    return data.loc[mask].copy()


def render_kpis(data: pd.DataFrame) -> None:
    attendances = int(data["attendances"].sum())
    over_4 = int(data["over_4_hours"].sum())
    over_8 = int(data["over_8_hours"].sum(skipna=True))
    over_12 = int(data["over_12_hours"].sum(skipna=True))

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Passages", f"{attendances:,}".replace(",", " "))
    col2.metric("Pris en charge < 4 h", f"{weighted_rate(data):.1f} %")
    col3.metric("Dépassements de 4 h", f"{over_4:,}".replace(",", " "))
    col4.metric(
        "Dépassements de 8 h / 12 h",
        f"{over_8:,} / {over_12:,}".replace(",", " "),
    )


def render_monthly_trends(data: pd.DataFrame) -> None:
    monthly = aggregate_monthly(data)
    st.subheader("Évolution mensuelle")

    left, right = st.columns(2)
    with left:
        rate_chart = px.line(
            monthly,
            x="month_date",
            y="pct_within_4_hours",
            markers=True,
            labels={"month_date": "Mois", "pct_within_4_hours": "Pris en charge < 4 h (%)"},
            title="Respect de l'objectif des quatre heures",
        )
        rate_chart.update_yaxes(range=[0, 100])
        st.plotly_chart(rate_chart, width="stretch")

    with right:
        volume_chart = go.Figure()
        volume_chart.add_bar(
            x=monthly["month_date"], y=monthly["within_4_hours"], name="Moins de 4 h"
        )
        volume_chart.add_bar(
            x=monthly["month_date"], y=monthly["over_4_hours"], name="Plus de 4 h"
        )
        volume_chart.update_layout(
            barmode="stack",
            title="Volume mensuel des passages",
            xaxis_title="Mois",
            yaxis_title="Passages",
        )
        st.plotly_chart(volume_chart, width="stretch")


def render_site_priorities(data: pd.DataFrame) -> None:
    sites = aggregate_sites(data)
    sites["site_name"] = sites["site_code"].map(site_label)
    st.subheader("Établissements à analyser en priorité")
    st.caption(
        "Les sites situés en bas à droite combinent un volume important et un faible taux de prise en charge en moins de quatre heures."
    )

    scatter = px.scatter(
        sites,
        x="attendances",
        y="pct_within_4_hours",
        size="over_4_hours",
        color="health_board_code",
        hover_name="site_name",
        hover_data={"site_code": True, "site_name": False},
        labels={
            "attendances": "Passages",
            "pct_within_4_hours": "Pris en charge < 4 h (%)",
            "health_board_code": "Organisme",
            "over_4_hours": "Dépassements de 4 h",
        },
        title="Matrice volume / performance",
    )
    scatter.update_yaxes(range=[0, 100])
    st.plotly_chart(scatter, width="stretch")

    ranking = sites.head(10).copy()
    ranking["pct_within_4_hours"] = ranking["pct_within_4_hours"].round(1)
    ranking = ranking.rename(
        columns={
            "health_board_code": "Organisme",
            "site_code": "Code",
            "site_name": "Établissement",
            "attendances": "Passages",
            "over_4_hours": "Dépassements de 4 h",
            "pct_within_4_hours": "Pris en charge < 4 h (%)",
        }
    )
    st.dataframe(
        ranking[
            [
                "Organisme",
                "Établissement",
                "Code",
                "Passages",
                "Dépassements de 4 h",
                "Pris en charge < 4 h (%)",
            ]
        ],
        width="stretch",
        hide_index=True,
    )


def main() -> None:
    st.set_page_config(page_title="Hospital Waiting Time Analytics", page_icon="🏥", layout="wide")
    st.title("🏥 Emergency Department Waiting Time Analytics")
    st.write(
        "Analyse des passages non planifiés dans les urgences principales de type 1 en Écosse."
    )

    try:
        data, source = load_waiting_times()
    except Exception as error:
        st.error("Impossible de charger les données depuis PostgreSQL.")
        st.code(str(error))
        st.info("Exécutez le pipeline ETL décrit dans le README, puis rechargez la page.")
        st.stop()

    if data.empty:
        st.warning("La table ae_waiting_times ne contient aucune donnée.")
        st.stop()

    st.caption(f"Source chargée : {source}")

    filtered = apply_filters(data)
    if filtered.empty:
        st.warning("Aucune donnée ne correspond aux filtres sélectionnés.")
        st.stop()

    render_kpis(filtered)
    render_monthly_trends(filtered)
    render_site_priorities(filtered)

    st.subheader("Données filtrées")
    export = filtered.sort_values(["month_date", "health_board_code", "site_code"])
    st.download_button(
        "Télécharger le CSV filtré",
        data=export.to_csv(index=False).encode("utf-8"),
        file_name="waiting_times_filtered.csv",
        mime="text/csv",
    )

    with st.expander("Limites de l'analyse"):
        st.write(
            "Les données sont mensuelles et agrégées. Elles ne décrivent ni les temps d'attente individuels, "
            "ni les effectifs, les lits disponibles ou la gravité clinique. Le dashboard aide à détecter "
            "les tensions, mais ne permet pas d'en établir les causes."
        )


if __name__ == "__main__":
    main()
