from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2 import sql


DEFAULT_INPUT = Path("data/processed/waiting_times_processed.csv")
EXPECTED_COLUMNS = [
    "month_date",
    "health_board_code",
    "site_code",
    "attendances",
    "within_4_hours",
    "over_4_hours",
    "over_8_hours",
    "over_12_hours",
]


@dataclass(frozen=True)
class PgConfig:
    host: str
    port: int
    database: str
    user: str
    password: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load processed A&E waiting times into PostgreSQL.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--schema", default="public")
    parser.add_argument("--table", default="ae_waiting_times")
    parser.add_argument("--host", default=os.getenv("PGHOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PGPORT", "5432")))
    parser.add_argument("--db", default=os.getenv("PGDATABASE", "hospital"))
    parser.add_argument("--user", default=os.getenv("PGUSER", "postgres"))
    parser.add_argument("--password", default=os.getenv("PGPASSWORD"))
    return parser.parse_args()


def validate_csv(path: Path) -> int:
    if not path.exists():
        raise FileNotFoundError(f"Processed CSV not found: {path.as_posix()}")
    preview = pd.read_csv(path, nrows=5)
    if list(preview.columns) != EXPECTED_COLUMNS:
        raise ValueError(f"Unexpected CSV columns: {list(preview.columns)}")
    with path.open("r", encoding="utf-8") as stream:
        return max(sum(1 for _ in stream) - 1, 0)


def connect(config: PgConfig):
    return psycopg2.connect(
        host=config.host,
        port=config.port,
        dbname=config.database,
        user=config.user,
        password=config.password,
        connect_timeout=10,
    )


def replace_table(connection, csv_path: Path, schema: str, table: str) -> None:
    table_identifier = sql.Identifier(schema, table)
    with connection.cursor() as cursor:
        cursor.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
        cursor.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(table_identifier))
        cursor.execute(
            sql.SQL(
                """
                CREATE TABLE {} (
                    month_date DATE NOT NULL,
                    health_board_code TEXT NOT NULL,
                    site_code TEXT NOT NULL,
                    attendances INTEGER NOT NULL CHECK (attendances >= 0),
                    within_4_hours INTEGER NOT NULL CHECK (within_4_hours >= 0),
                    over_4_hours INTEGER NOT NULL CHECK (over_4_hours >= 0),
                    over_8_hours INTEGER,
                    over_12_hours INTEGER,
                    PRIMARY KEY (month_date, health_board_code, site_code)
                )
                """
            ).format(table_identifier)
        )
        columns = sql.SQL(", ").join(map(sql.Identifier, EXPECTED_COLUMNS))
        copy_statement = sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE)").format(
            table_identifier, columns
        )
        with csv_path.open("r", encoding="utf-8") as stream:
            cursor.copy_expert(copy_statement.as_string(connection), stream)
    connection.commit()


def main() -> None:
    args = parse_args()
    row_count = validate_csv(args.input)
    config = PgConfig(args.host, args.port, args.db, args.user, args.password)
    with connect(config) as connection:
        replace_table(connection, args.input, args.schema, args.table)
    print(f"Loaded {row_count:,} rows into {args.schema}.{args.table}")


if __name__ == "__main__":
    main()
