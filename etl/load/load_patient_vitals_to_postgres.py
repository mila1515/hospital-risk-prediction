import argparse
import csv
import io
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import psycopg2
from psycopg2 import sql


@dataclass(frozen=True)
class PgConfig:
    host: str
    port: int
    database: str
    user: str
    password: str | None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="load_patient_vitals_to_postgres")
    p.add_argument(
        "--dataset",
        choices=["patient_vitals", "nhs_scotland_ae", "cqc_aip_2024"],
        default="patient_vitals",
        help="Choix du dataset à charger. 'patient_vitals' = dataset ML. 'nhs_scotland_ae' = KPI urgences (open data).",
    )
    p.add_argument("--csv", type=Path, default=None)
    p.add_argument(
        "--cqc-dir",
        type=Path,
        default=Path("data/raw/cqc/adult_inpatient_survey_2024"),
        help="Dossier contenant les fichiers ODS (aip_2024_*.ods). Utilisé quand --dataset cqc_aip_2024.",
    )
    p.add_argument("--schema", default="public")
    p.add_argument("--table", default=None)
    p.add_argument("--mode", choices=["append", "truncate", "replace"], default="replace")

    p.add_argument("--host", default=os.getenv("PGHOST", "localhost"))
    p.add_argument("--port", type=int, default=int(os.getenv("PGPORT", "5432")))
    p.add_argument("--db", default=os.getenv("PGDATABASE", "postgres"))
    p.add_argument("--user", default=os.getenv("PGUSER", "postgres"))
    p.add_argument("--password", default=os.getenv("PGPASSWORD"))

    return p.parse_args()


def get_pg_config(args: argparse.Namespace) -> PgConfig:
    pw = args.password
    if pw is not None and str(pw).strip() == "":
        pw = None
    return PgConfig(
        host=str(args.host),
        port=int(args.port),
        database=str(args.db),
        user=str(args.user),
        password=None if pw is None else str(pw),
    )


def connect(cfg: PgConfig):
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

    try:
        return psycopg2.connect(**kwargs)
    except UnicodeDecodeError as e:
        raise SystemExit(
            "Connexion PostgreSQL impossible (erreur d'encodage). Vérifie host/port/db/user/password.\n"
            "Astuce: essaie en passant explicitement --db postgres --user postgres --password <ton_mot_de_passe>."
        ) from e


def table_ident(schema: str, table: str) -> sql.Composed:
    return sql.SQL(".").join([sql.Identifier(schema), sql.Identifier(table)])


def create_table_patient_vitals(cur, schema: str, table: str) -> None:
    cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
    cur.execute(
        sql.SQL(
            """
            CREATE TABLE IF NOT EXISTS {tbl} (
              patient_id TEXT NOT NULL,
              recorded_at TIMESTAMP NOT NULL,
              age INTEGER NOT NULL,
              temperature_c DOUBLE PRECISION NOT NULL,
              systolic_bp DOUBLE PRECISION NOT NULL,
              diastolic_bp DOUBLE PRECISION NOT NULL,
              spo2 DOUBLE PRECISION NOT NULL,
              heart_rate DOUBLE PRECISION NOT NULL,
              glucose_mg_dl DOUBLE PRECISION NOT NULL,
              pain_score DOUBLE PRECISION NOT NULL,
              admission_type TEXT,
              risk_score INTEGER NOT NULL,
              risk_level TEXT NOT NULL,
              PRIMARY KEY (patient_id, recorded_at)
            )
            """
        ).format(tbl=table_ident(schema, table))
    )
    cur.execute(
        sql.SQL("CREATE INDEX IF NOT EXISTS {idx} ON {tbl} (risk_level)").format(
            idx=sql.Identifier(f"{table}_risk_level_idx"),
            tbl=table_ident(schema, table),
        )
    )
    cur.execute(
        sql.SQL("CREATE INDEX IF NOT EXISTS {idx} ON {tbl} (recorded_at)").format(
            idx=sql.Identifier(f"{table}_recorded_at_idx"),
            tbl=table_ident(schema, table),
        )
    )


def drop_table(cur, schema: str, table: str) -> None:
    cur.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(table_ident(schema, table)))


def truncate_table(cur, schema: str, table: str) -> None:
    cur.execute(sql.SQL("TRUNCATE TABLE {}").format(table_ident(schema, table)))


def copy_csv_patient_vitals(cur, schema: str, table: str, csv_path: Path) -> int:
    copy_stmt = sql.SQL(
        "COPY {tbl} (patient_id, recorded_at, age, temperature_c, systolic_bp, diastolic_bp, spo2, heart_rate, glucose_mg_dl, pain_score, admission_type, risk_score, risk_level) "
        "FROM STDIN WITH (FORMAT CSV, HEADER TRUE)"
    ).format(tbl=table_ident(schema, table))

    with csv_path.open("r", encoding="utf-8") as f:
        cur.copy_expert(copy_stmt.as_string(cur), f)

    cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(table_ident(schema, table)))
    return int(cur.fetchone()[0])


def create_table_nhs_scotland_ae(cur, schema: str, table: str) -> None:
    cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
    cur.execute(
        sql.SQL(
            """
            CREATE TABLE IF NOT EXISTS {tbl} (
              id BIGSERIAL PRIMARY KEY,
              month INTEGER NOT NULL,
              month_date DATE NOT NULL,
              country TEXT NOT NULL,
              hbt TEXT NOT NULL,
              treatment_location TEXT NOT NULL,
              department_type TEXT NOT NULL,
              attendance_category TEXT NOT NULL,
              number_of_attendances_all INTEGER,
              number_within_4_hours_all INTEGER,
              number_over_4_hours_all INTEGER,
              percentage_within_4_hours_all DOUBLE PRECISION,
              number_of_attendances_episode INTEGER,
              number_of_attendances_episode_qf TEXT,
              number_within_4_hours_episode INTEGER,
              number_within_4_hours_episode_qf TEXT,
              number_over_4_hours_episode INTEGER,
              number_over_4_hours_episode_qf TEXT,
              percentage_within_4_hours_episode DOUBLE PRECISION,
              percentage_within_4_hours_episode_qf TEXT,
              number_over_8_hours_episode INTEGER,
              number_over_8_hours_episode_qf TEXT,
              percentage_over_8_hours_episode DOUBLE PRECISION,
              percentage_over_8_hours_episode_qf TEXT,
              number_over_12_hours_episode INTEGER,
              number_over_12_hours_episode_qf TEXT,
              percentage_over_12_hours_episode DOUBLE PRECISION,
              percentage_over_12_hours_episode_qf TEXT
            )
            """
        ).format(tbl=table_ident(schema, table))
    )
    cur.execute(
        sql.SQL("CREATE INDEX IF NOT EXISTS {idx} ON {tbl} (month_date)").format(
            idx=sql.Identifier(f"{table}_month_date_idx"),
            tbl=table_ident(schema, table),
        )
    )
    cur.execute(
        sql.SQL("CREATE INDEX IF NOT EXISTS {idx} ON {tbl} (attendance_category)").format(
            idx=sql.Identifier(f"{table}_attendance_category_idx"),
            tbl=table_ident(schema, table),
        )
    )


def _parse_month_yyyymm(value: str) -> tuple[int, date]:
    s = str(value).strip().strip('"')
    if len(s) != 6 or not s.isdigit():
        raise ValueError(f"Invalid Month value (expected YYYYMM): {value!r}")
    year = int(s[:4])
    month = int(s[4:])
    return int(s), date(year, month, 1)


def _to_int_or_none(value: str | None) -> int | None:
    if value is None:
        return None
    s = str(value).strip()
    if s == "" or s.lower() == "z":
        return None
    return int(float(s))


def _to_float_or_none(value: str | None) -> float | None:
    if value is None:
        return None
    s = str(value).strip()
    if s == "" or s.lower() == "z":
        return None
    return float(s)


def copy_csv_nhs_scotland_ae(cur, schema: str, table: str, csv_path: Path) -> int:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")

    out_cols = [
        "month",
        "month_date",
        "country",
        "hbt",
        "treatment_location",
        "department_type",
        "attendance_category",
        "number_of_attendances_all",
        "number_within_4_hours_all",
        "number_over_4_hours_all",
        "percentage_within_4_hours_all",
        "number_of_attendances_episode",
        "number_of_attendances_episode_qf",
        "number_within_4_hours_episode",
        "number_within_4_hours_episode_qf",
        "number_over_4_hours_episode",
        "number_over_4_hours_episode_qf",
        "percentage_within_4_hours_episode",
        "percentage_within_4_hours_episode_qf",
        "number_over_8_hours_episode",
        "number_over_8_hours_episode_qf",
        "percentage_over_8_hours_episode",
        "percentage_over_8_hours_episode_qf",
        "number_over_12_hours_episode",
        "number_over_12_hours_episode_qf",
        "percentage_over_12_hours_episode",
        "percentage_over_12_hours_episode_qf",
    ]
    writer.writerow(out_cols)

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            month_int, month_dt = _parse_month_yyyymm(row["Month"])
            writer.writerow(
                [
                    month_int,
                    month_dt.isoformat(),
                    (row.get("Country") or "").strip(),
                    (row.get("HBT") or "").strip(),
                    (row.get("TreatmentLocation") or "").strip(),
                    (row.get("DepartmentType") or "").strip(),
                    (row.get("AttendanceCategory") or "").strip(),
                    _to_int_or_none(row.get("NumberOfAttendancesAll")),
                    _to_int_or_none(row.get("NumberWithin4HoursAll")),
                    _to_int_or_none(row.get("NumberOver4HoursAll")),
                    _to_float_or_none(row.get("PercentageWithin4HoursAll")),
                    _to_int_or_none(row.get("NumberOfAttendancesEpisode")),
                    (row.get("NumberOfAttendancesEpisodeQF") or "").strip() or None,
                    _to_int_or_none(row.get("NumberWithin4HoursEpisode")),
                    (row.get("NumberWithin4HoursEpisodeQF") or "").strip() or None,
                    _to_int_or_none(row.get("NumberOver4HoursEpisode")),
                    (row.get("NumberOver4HoursEpisodeQF") or "").strip() or None,
                    _to_float_or_none(row.get("PercentageWithin4HoursEpisode")),
                    (row.get("PercentageWithin4HoursEpisodeQF") or "").strip() or None,
                    _to_int_or_none(row.get("NumberOver8HoursEpisode")),
                    (row.get("NumberOver8HoursEpisodeQF") or "").strip() or None,
                    _to_float_or_none(row.get("PercentageOver8HoursEpisode")),
                    (row.get("PercentageOver8HoursEpisodeQF") or "").strip() or None,
                    _to_int_or_none(row.get("NumberOver12HoursEpisode")),
                    (row.get("NumberOver12HoursEpisodeQF") or "").strip() or None,
                    _to_float_or_none(row.get("PercentageOver12HoursEpisode")),
                    (row.get("PercentageOver12HoursEpisodeQF") or "").strip() or None,
                ]
            )

    out.seek(0)
    copy_stmt = sql.SQL("COPY {tbl} ({cols}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE)").format(
        tbl=table_ident(schema, table),
        cols=sql.SQL(", ").join(sql.Identifier(c) for c in out_cols),
    )
    cur.copy_expert(copy_stmt.as_string(cur), out)

    cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(table_ident(schema, table)))
    return int(cur.fetchone()[0])


def _slugify_column(name: str) -> str:
    s = str(name).strip().lower()
    s = re.sub(r"[^\w]+", "_", s, flags=re.UNICODE).strip("_")
    if s == "" or s[0].isdigit():
        s = f"col_{s}" if s else "col"
    return s[:63]


def _create_table_from_headers(cur, schema: str, table: str, headers: list[str]) -> list[str]:
    cols: list[str] = []
    seen: set[str] = set()
    for c in headers:
        base = _slugify_column(c)
        col = base
        i = 2
        while col in seen:
            suffix = f"_{i}"
            col = (base[: 63 - len(suffix)] + suffix) if len(base) + len(suffix) > 63 else (base + suffix)
            i += 1
        seen.add(col)
        cols.append(col)

    cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
    cur.execute(
        sql.SQL("CREATE TABLE IF NOT EXISTS {tbl} ({cols})").format(
            tbl=table_ident(schema, table),
            cols=sql.SQL(", ").join(sql.SQL("{} TEXT").format(sql.Identifier(c)) for c in cols),
        )
    )
    return cols


def _copy_rows_as_csv(cur, schema: str, table: str, headers: list[str], rows: list[list[str | None]], cols: list[str]) -> int:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(cols)
    for r in rows:
        fixed = (r + [None] * len(headers))[: len(headers)]
        writer.writerow(["" if v is None else str(v) for v in fixed])
    out.seek(0)
    copy_stmt = sql.SQL("COPY {tbl} ({cols}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE, NULL '')").format(
        tbl=table_ident(schema, table),
        cols=sql.SQL(", ").join(sql.Identifier(c) for c in cols),
    )
    cur.copy_expert(copy_stmt.as_string(cur), out)
    cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(table_ident(schema, table)))
    return int(cur.fetchone()[0])


def load_cqc_aip_2024(cur, schema: str, mode: str, cqc_dir: Path) -> dict[str, int]:
    from odf import teletype
    from odf.opendocument import load
    from odf.table import Table, TableCell, TableRow

    files = {
        "cqc_aip2024_national": cqc_dir / "aip_2024_national_tables.ods",
        "cqc_aip2024_trust": cqc_dir / "aip_2024_benchmark_trust_level.ods",
        "cqc_aip2024_site": cqc_dir / "aip_2024_benchmark_site_level.ods",
    }

    results: dict[str, int] = {}
    for table_name, ods_path in files.items():
        if not ods_path.exists():
            raise SystemExit(f"ODS not found: {ods_path.as_posix()}")

        doc = load(str(ods_path))
        tables = doc.spreadsheet.getElementsByType(Table)

        best_sheet_name = None
        best_headers: list[str] | None = None
        best_rows: list[list[str | None]] | None = None
        best_data_rows = -1

        for t in tables:
            sheet_name = str(t.getAttribute("name") or "sheet")

            raw_rows: list[list[str | None]] = []
            for tr in t.getElementsByType(TableRow):
                repeat_row = tr.getAttribute("numberrowsrepeated")
                repeat_row_n = int(repeat_row) if repeat_row and str(repeat_row).isdigit() else 1

                row_values: list[str | None] = []
                for tc in tr.getElementsByType(TableCell):
                    repeat_col = tc.getAttribute("numbercolumnsrepeated")
                    repeat_col_n = int(repeat_col) if repeat_col and str(repeat_col).isdigit() else 1

                    text = teletype.extractText(tc).strip()
                    if text == "":
                        val = tc.getAttribute("value")
                        val = None if val is None else str(val).strip()
                        text = "" if val is None else val
                    cell_val: str | None = text if text != "" else None
                    row_values.extend([cell_val] * repeat_col_n)

                trimmed = list(row_values)
                while trimmed and (trimmed[-1] is None or str(trimmed[-1]).strip() == ""):
                    trimmed.pop()

                if repeat_row_n > 1:
                    if not trimmed:
                        continue
                    for _ in range(repeat_row_n):
                        raw_rows.append(trimmed)
                else:
                    raw_rows.append(trimmed)

            first_idx = None
            for i, r in enumerate(raw_rows):
                if any(v is not None and str(v).strip() != "" for v in r):
                    first_idx = i
                    break
            if first_idx is None:
                continue

            headers = [str(v).strip() if v is not None else "" for v in raw_rows[first_idx]]
            headers = [h if h != "" else f"col_{i+1}" for i, h in enumerate(headers)]
            data_rows = raw_rows[first_idx + 1 :]
            data_rows = [r for r in data_rows if any(v is not None and str(v).strip() != "" for v in r)]

            if len(data_rows) > best_data_rows:
                best_data_rows = len(data_rows)
                best_sheet_name = sheet_name
                best_headers = headers
                best_rows = data_rows

        if best_sheet_name is None or best_headers is None or best_rows is None:
            raise SystemExit(f"Aucune feuille exploitable dans: {ods_path.as_posix()}")

        if mode == "replace":
            drop_table(cur, schema, table_name)

        cols = _create_table_from_headers(cur, schema, table_name, best_headers)

        if mode == "truncate":
            truncate_table(cur, schema, table_name)

        row_count = _copy_rows_as_csv(cur, schema, table_name, best_headers, best_rows, cols)
        results[f"{schema}.{table_name} ({best_sheet_name})"] = row_count

    return results


def main() -> None:
    args = parse_args()
    cfg = get_pg_config(args)

    if args.dataset == "patient_vitals":
        csv_path = Path(args.csv) if args.csv is not None else Path("data/processed/patient_vitals_processed.csv")
        table_name = str(args.table) if args.table is not None else "patient_vitals"
    else:
        csv_path = Path(args.csv) if args.csv is not None else None
        table_name = str(args.table) if args.table is not None else None

    if args.dataset in {"patient_vitals", "nhs_scotland_ae"}:
        if csv_path is None:
            csv_path = (
                Path("data/processed/patient_vitals_processed.csv")
                if args.dataset == "patient_vitals"
                else Path("data/raw/nhs_scotland/monthly_ae_activity_waiting_times.csv")
            )
        if table_name is None:
            table_name = "patient_vitals" if args.dataset == "patient_vitals" else "ae_waiting_times"
        if not csv_path.exists():
            raise SystemExit(f"CSV not found: {csv_path.as_posix()}")

    with connect(cfg) as conn:
        with conn.cursor() as cur:
            if args.dataset == "cqc_aip_2024":
                results = load_cqc_aip_2024(cur, args.schema, args.mode, args.cqc_dir)
                conn.commit()
                for k, v in results.items():
                    print(f"Loaded into {k}")
                    print(f"Rows in table: {v:,}")
                return

            if args.mode == "replace":
                drop_table(cur, args.schema, table_name)
                if args.dataset == "patient_vitals":
                    create_table_patient_vitals(cur, args.schema, table_name)
                else:
                    create_table_nhs_scotland_ae(cur, args.schema, table_name)
            else:
                if args.dataset == "patient_vitals":
                    create_table_patient_vitals(cur, args.schema, table_name)
                else:
                    create_table_nhs_scotland_ae(cur, args.schema, table_name)
                if args.mode == "truncate":
                    truncate_table(cur, args.schema, table_name)

            if args.dataset == "patient_vitals":
                row_count = copy_csv_patient_vitals(cur, args.schema, table_name, csv_path)
            else:
                row_count = copy_csv_nhs_scotland_ae(cur, args.schema, table_name, csv_path)
            conn.commit()

    print(f"Loaded into {args.schema}.{table_name}")
    print(f"Rows in table: {row_count:,}")


if __name__ == "__main__":
    main()
