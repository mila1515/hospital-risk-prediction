from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
from typing import TYPE_CHECKING
import urllib.request
import zipfile

try:
    import numpy as np
    import pandas as pd
except ModuleNotFoundError:
    np = None
    pd = None

if TYPE_CHECKING:
    import pandas as _pd


# Script "extract" (en 1 fichier) :
# 1) Télécharge MIMIC-IV Demo (open access) depuis PhysioNet (ZIP)
# 2) Dézippe dans data/raw/mimic_iv_demo/...
# 3) Construit un CSV raw au format du projet (patient_vitals_*.csv)
#
# L'idée : tu peux lancer UNE seule commande pour avoir des "vraies" données brutes.

DEFAULT_VERSION = "2.2"
DEFAULT_BASE_URL = "https://physionet.org/content/mimic-iv-demo/get-zip/{version}/"

DEFAULT_NHS_SCOTLAND_AE_URL = (
    "https://www.opendata.nhs.scot/dataset/997acaa5-afe0-49d9-b333-dcf84584603d/"
    "resource/37ba17b1-c323-492c-87d5-e986aae9ab59/download/monthly_ae_activity_202603.csv"
)

DEFAULT_CQC_AIP2024_NATIONAL_ODS_URL = (
    "https://www.cqc.org.uk/sites/default/files/2025-09/20250909_aip24_National.ods"
)
DEFAULT_CQC_AIP2024_TRUST_ODS_URL = (
    "https://www.cqc.org.uk/sites/default/files/2025-09/20250909_aip24_Benchmark_TrustLevel.ods"
)
DEFAULT_CQC_AIP2024_SITE_ODS_URL = (
    "https://www.cqc.org.uk/sites/default/files/2025-09/20250909_aip24_Benchmark_SiteLevel.ods"
)

ITEM_HEART_RATE = 220045
ITEM_SPO2 = 220277
ITEM_TEMP_C = 223762
ITEM_TEMP_F = 223761
ITEM_NIBP_SYS = 220179
ITEM_NIBP_DIA = 220180
ITEM_ART_SYS = 220050
ITEM_ART_DIA = 220051
ITEM_MAN_SYS = 227243
ITEM_MAN_DIA = 227242
ITEM_PAIN_LEVEL = 223791

GLUCOSE_ITEMIDS = [50931, 52569, 50809, 52027]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="build_raw_from_mimic_iv_demo")
    p.add_argument("--version", default=DEFAULT_VERSION)
    p.add_argument("--raw-root", type=Path, default=Path("data/raw/mimic_iv_demo"))
    p.add_argument(
        "--demo-dir",
        type=Path,
        default=None,
        help="Chemin vers le dossier MIMIC dézippé qui contient hosp/ et icu/. Si non fourni, le script télécharge+dézippe.",
    )
    p.add_argument("--expected-sha256", default=None)
    p.add_argument("--force", action="store_true", help="Retélécharger / redézipper même si les fichiers existent.")
    p.add_argument("--out", type=Path, default=Path("data/raw/patient_vitals_mimic_demo_raw.csv"))
    p.add_argument(
        "--download-nhs-scotland-ae",
        action="store_true",
        help="Télécharge un CSV open data (NHS Scotland) sur l'activité A&E + temps d'attente, utile pour le dashboard KPI.",
    )
    p.add_argument("--nhs-scotland-ae-url", default=DEFAULT_NHS_SCOTLAND_AE_URL)
    p.add_argument(
        "--nhs-scotland-ae-out",
        type=Path,
        default=Path("data/raw/nhs_scotland/monthly_ae_activity_waiting_times.csv"),
    )
    p.add_argument(
        "--download-cqc-aip-2024",
        action="store_true",
        help="Télécharge les fichiers open data du CQC Adult inpatient survey 2024 (ODS) pour KPI/satisfaction.",
    )
    p.add_argument("--cqc-aip-2024-national-ods-url", default=DEFAULT_CQC_AIP2024_NATIONAL_ODS_URL)
    p.add_argument("--cqc-aip-2024-trust-ods-url", default=DEFAULT_CQC_AIP2024_TRUST_ODS_URL)
    p.add_argument("--cqc-aip-2024-site-ods-url", default=DEFAULT_CQC_AIP2024_SITE_ODS_URL)
    p.add_argument(
        "--cqc-aip-2024-out-dir",
        type=Path,
        default=Path("data/raw/cqc/adult_inpatient_survey_2024"),
    )
    return p.parse_args()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url) as r, tmp.open("wb") as f:
        shutil.copyfileobj(r, f)
    tmp.replace(dest)


def extract_zip(zip_path: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(out_dir)


def find_mimic_root(extract_dir: Path) -> Path:
    # PhysioNet met un dossier racine du style "mimic-iv-clinical-database-demo-2.2/"
    # mais on garde une détection robuste : on cherche un dossier qui contient hosp/ et icu/.
    candidates = [extract_dir] + [p for p in extract_dir.rglob("*") if p.is_dir()]
    for c in candidates:
        if (c / "hosp").is_dir() and (c / "icu").is_dir():
            return c
    raise FileNotFoundError(f"Impossible de trouver un dossier contenant 'hosp' et 'icu' sous: {extract_dir.as_posix()}")


def _first_by_stay(events: pd.DataFrame, itemid: int, col_name: str) -> pd.DataFrame:
    # On prend la première mesure disponible par séjour ICU (stay_id),
    # pour construire un dataset "état initial" simple.
    df = events.loc[events["itemid"] == itemid, ["stay_id", "charttime", "valuenum"]].dropna(subset=["valuenum"])
    if df.empty:
        return pd.DataFrame(columns=["stay_id", col_name, f"{col_name}__time"])
    df = df.sort_values(["stay_id", "charttime"])
    df = df.drop_duplicates(subset=["stay_id"], keep="first").rename(
        columns={"valuenum": col_name, "charttime": f"{col_name}__time"}
    )
    return df[["stay_id", col_name, f"{col_name}__time"]]


def main() -> None:
    args = parse_args()
    version: str = str(args.version)
    raw_root: Path = args.raw_root
    out_path: Path = args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Étape 0 — (Optionnel) Télécharger un dataset open data (sans accès credentialed)
    # Objectif: compléter le projet avec des KPI "activité/temps d'attente" (utile pour Power BI),
    # sans toucher aux données patient-level.
    if args.download_nhs_scotland_ae:
        nhs_out: Path = args.nhs_scotland_ae_out
        if args.force and nhs_out.exists():
            nhs_out.unlink()
        if not nhs_out.exists():
            download(str(args.nhs_scotland_ae_url), nhs_out)
        print(f"Downloaded NHS Scotland A&E CSV to {nhs_out.as_posix()}")

    if args.download_cqc_aip_2024:
        cqc_dir: Path = args.cqc_aip_2024_out_dir
        cqc_dir.mkdir(parents=True, exist_ok=True)

        national_ods = cqc_dir / "aip_2024_national_tables.ods"
        trust_ods = cqc_dir / "aip_2024_benchmark_trust_level.ods"
        site_ods = cqc_dir / "aip_2024_benchmark_site_level.ods"

        if args.force:
            for p in [national_ods, trust_ods, site_ods]:
                if p.exists():
                    p.unlink()

        if not national_ods.exists():
            download(str(args.cqc_aip_2024_national_ods_url), national_ods)
        if not trust_ods.exists():
            download(str(args.cqc_aip_2024_trust_ods_url), trust_ods)
        if not site_ods.exists():
            download(str(args.cqc_aip_2024_site_ods_url), site_ods)

        print(f"Downloaded CQC Adult inpatient survey 2024 ODS files to {cqc_dir.as_posix()}")

    if pd is None or np is None:
        raise SystemExit(
            "Il manque des dépendances Python pour construire le CSV MIMIC (pandas/numpy). "
            "Installe-les avec: pip install -r requirements.txt"
        )

    # Étape A — Obtenir le dataset MIMIC-IV Demo (download + unzip) si demo_dir n'est pas donné.
    if args.demo_dir is not None:
        demo_dir = Path(args.demo_dir)
    else:
        url = DEFAULT_BASE_URL.format(version=version)
        zip_path = raw_root / f"mimic-iv-demo-{version}.zip"
        extract_dir = raw_root / f"mimic-iv-demo-{version}"

        if args.force:
            if extract_dir.exists():
                shutil.rmtree(extract_dir)
            if zip_path.exists():
                zip_path.unlink()

        if not zip_path.exists():
            download(url, zip_path)

        actual_sha = sha256_file(zip_path)
        if args.expected_sha256 and actual_sha.lower() != str(args.expected_sha256).lower():
            raise SystemExit(f"SHA256 mismatch for {zip_path.name}: got {actual_sha}")

        if not extract_dir.exists():
            extract_zip(zip_path, extract_dir)

        demo_dir = find_mimic_root(extract_dir)

    # Étape B — Construire un CSV raw au format du projet depuis MIMIC (hosp/icu).
    patients = pd.read_csv(demo_dir / "hosp" / "patients.csv.gz")
    icustays = pd.read_csv(demo_dir / "icu" / "icustays.csv.gz", parse_dates=["intime", "outtime"])

    chartevents = pd.read_csv(
        demo_dir / "icu" / "chartevents.csv.gz",
        usecols=["subject_id", "hadm_id", "stay_id", "charttime", "itemid", "valuenum", "valueuom"],
        parse_dates=["charttime"],
    )

    needed_itemids = {
        ITEM_HEART_RATE,
        ITEM_SPO2,
        ITEM_TEMP_C,
        ITEM_TEMP_F,
        ITEM_NIBP_SYS,
        ITEM_NIBP_DIA,
        ITEM_ART_SYS,
        ITEM_ART_DIA,
        ITEM_MAN_SYS,
        ITEM_MAN_DIA,
        ITEM_PAIN_LEVEL,
    }
    ce = chartevents.loc[chartevents["itemid"].isin(needed_itemids)].copy()

    temp_c = _first_by_stay(ce, ITEM_TEMP_C, "temperature_c")
    temp_f = _first_by_stay(ce, ITEM_TEMP_F, "temperature_f")
    if not temp_f.empty:
        temp_f["temperature_c"] = (temp_f["temperature_f"] - 32.0) * (5.0 / 9.0)
        temp_f = temp_f.drop(columns=["temperature_f"]).rename(columns={"temperature_f__time": "temperature_c__time"})

    hr = _first_by_stay(ce, ITEM_HEART_RATE, "heart_rate")
    spo2 = _first_by_stay(ce, ITEM_SPO2, "spo2")
    pain = _first_by_stay(ce, ITEM_PAIN_LEVEL, "pain_score")

    sys_nibp = _first_by_stay(ce, ITEM_NIBP_SYS, "systolic_bp")
    sys_art = _first_by_stay(ce, ITEM_ART_SYS, "systolic_bp_alt1")
    sys_man = _first_by_stay(ce, ITEM_MAN_SYS, "systolic_bp_alt2")

    dia_nibp = _first_by_stay(ce, ITEM_NIBP_DIA, "diastolic_bp")
    dia_art = _first_by_stay(ce, ITEM_ART_DIA, "diastolic_bp_alt1")
    dia_man = _first_by_stay(ce, ITEM_MAN_DIA, "diastolic_bp_alt2")

    base = icustays[["stay_id", "subject_id", "hadm_id", "first_careunit", "intime", "outtime"]].copy()
    df = base.merge(hr, on="stay_id", how="left")
    df = df.merge(spo2, on="stay_id", how="left")
    df = df.merge(pain, on="stay_id", how="left")
    df = df.merge(sys_nibp, on="stay_id", how="left").merge(sys_art, on="stay_id", how="left").merge(
        sys_man, on="stay_id", how="left"
    )
    df = df.merge(dia_nibp, on="stay_id", how="left").merge(dia_art, on="stay_id", how="left").merge(
        dia_man, on="stay_id", how="left"
    )

    df["systolic_bp"] = df["systolic_bp"].fillna(df["systolic_bp_alt1"]).fillna(df["systolic_bp_alt2"])
    df["diastolic_bp"] = df["diastolic_bp"].fillna(df["diastolic_bp_alt1"]).fillna(df["diastolic_bp_alt2"])

    df = df.drop(
        columns=[
            "systolic_bp_alt1",
            "systolic_bp_alt2",
            "diastolic_bp_alt1",
            "diastolic_bp_alt2",
        ]
    )

    df = df.merge(temp_c, on="stay_id", how="left")
    if not temp_f.empty:
        df = df.merge(temp_f[["stay_id", "temperature_c", "temperature_c__time"]], on="stay_id", how="left", suffixes=("", "_f"))
        df["temperature_c"] = df["temperature_c"].fillna(df["temperature_c_f"])
        df["temperature_c__time"] = df["temperature_c__time"].fillna(df["temperature_c__time_f"])
        df = df.drop(columns=["temperature_c_f", "temperature_c__time_f"])

    time_cols = [c for c in df.columns if c.endswith("__time")]
    for c in time_cols:
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df["recorded_at"] = df[time_cols].min(axis=1)
    df["recorded_at"] = df["recorded_at"].fillna(df["intime"])

    df = df.merge(patients[["subject_id", "anchor_age"]], on="subject_id", how="left").rename(
        columns={"anchor_age": "age"}
    )

    labevents = pd.read_csv(
        demo_dir / "hosp" / "labevents.csv.gz",
        usecols=["hadm_id", "itemid", "charttime", "valuenum", "valueuom"],
        parse_dates=["charttime"],
    )
    gl = labevents.loc[labevents["itemid"].isin(GLUCOSE_ITEMIDS)].dropna(subset=["hadm_id", "valuenum"])
    if not gl.empty:
        gl = gl.sort_values(["hadm_id", "charttime"]).drop_duplicates(subset=["hadm_id"], keep="first")
        gl = gl.rename(columns={"valuenum": "glucose_mg_dl"})[["hadm_id", "glucose_mg_dl"]]
        df = df.merge(gl, on="hadm_id", how="left")
    else:
        df["glucose_mg_dl"] = np.nan

    df["patient_id"] = df["subject_id"].astype(str)
    df["stress_level"] = np.nan
    df["satisfaction_score"] = np.nan
    df["admission_type"] = df["first_careunit"].fillna("ICU")

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
        "stress_level",
        "satisfaction_score",
        "admission_type",
    ]
    out = df[out_cols].sort_values(["patient_id", "recorded_at"]).reset_index(drop=True)
    out.to_csv(out_path, index=False)

    print(f"Wrote {len(out):,} rows to {out_path.as_posix()}")
    print("Columns:", ", ".join(out.columns))


if __name__ == "__main__":
    main()
