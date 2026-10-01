"""SQLite persistence layer and Omron KRD-703T CSV ingestion engine."""

from __future__ import annotations

import io
import sqlite3
from pathlib import Path
from types import MappingProxyType
from typing import Final

import pandas as pd

DEFAULT_DATA_DIR: Final[str] = "data"
DEFAULT_DB_NAME: Final[str] = "body_composition_raw.db"

COLUMN_MAP: Final[MappingProxyType[str, str]] = MappingProxyType(
    {
        "測定日": "measured_at",
        "タイムゾーン": "timezone",
        "体重(kg)": "weight",
        "体脂肪(%)": "body_fat_pct",
        "体脂肪量(kg)": "body_fat_mass",
        "内臓脂肪レベル": "visceral_fat_level",
        "基礎代謝(kcal)": "bmr",
        "骨格筋(%)": "skeletal_muscle_pct",
        "骨格筋量(kg)": "skeletal_muscle_mass",
        "骨格筋率（両腕）(%)": "skeletal_muscle_arms_pct",
        "骨格筋率（体幹）(%)": "skeletal_muscle_trunk_pct",
        "骨格筋率（両脚）(%)": "skeletal_muscle_legs_pct",
        "皮下脂肪率(%)": "subcutaneous_fat_pct",
        "皮下脂肪率（両腕）(%)": "subcutaneous_fat_arms_pct",
        "皮下脂肪率（体幹）(%)": "subcutaneous_fat_trunk_pct",
        "皮下脂肪率（両脚）(%)": "subcutaneous_fat_legs_pct",
        "BMI": "bmi",
        "体年齢(才)": "body_age",
        "機種": "device",
    }
)

ALL_COLUMNS: Final[tuple[str, ...]] = (
    "measured_at",
    "timezone",
    "weight",
    "body_fat_pct",
    "body_fat_mass",
    "visceral_fat_level",
    "bmr",
    "skeletal_muscle_pct",
    "skeletal_muscle_mass",
    "skeletal_muscle_arms_pct",
    "skeletal_muscle_trunk_pct",
    "skeletal_muscle_legs_pct",
    "subcutaneous_fat_pct",
    "subcutaneous_fat_arms_pct",
    "subcutaneous_fat_trunk_pct",
    "subcutaneous_fat_legs_pct",
    "bmi",
    "body_age",
    "device",
)


def get_default_db_path() -> Path:
    """Get deterministic database file path relative to current script inside ./data.

    Returns:
        Path pointing to default SQLite database within data directory.
    """
    data_dir = Path(__file__).resolve().parent / DEFAULT_DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / DEFAULT_DB_NAME


def init_db(db_path: Path) -> None:
    """Initialize SQLite database with measurements schema if not exists.

    Args:
        db_path: Absolute filesystem path to the SQLite database file.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS measurements (
                measured_at TEXT PRIMARY KEY,
                timezone TEXT,
                weight REAL,
                body_fat_pct REAL,
                body_fat_mass REAL,
                visceral_fat_level REAL,
                bmr INTEGER,
                skeletal_muscle_pct REAL,
                skeletal_muscle_mass REAL,
                skeletal_muscle_arms_pct REAL,
                skeletal_muscle_trunk_pct REAL,
                skeletal_muscle_legs_pct REAL,
                subcutaneous_fat_pct REAL,
                subcutaneous_fat_arms_pct REAL,
                subcutaneous_fat_trunk_pct REAL,
                subcutaneous_fat_legs_pct REAL,
                bmi REAL,
                body_age INTEGER,
                device TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def parse_csv_bytes(content: bytes) -> pd.DataFrame:
    """Parse CSV raw bytes with encoding fallback (utf-8-sig, utf-8, cp932).

    Args:
        content: Raw bytes from uploaded file or disk.

    Returns:
        pd.DataFrame containing parsed tabular data.

    Raises:
        ValueError: If file cannot be decoded with supported encodings.
    """
    for enc in ("utf-8-sig", "utf-8", "cp932"):
        try:
            return pd.read_csv(io.BytesIO(content), encoding=enc)
        except UnicodeDecodeError, pd.errors.ParserError:
            continue
    raise ValueError("Failed to decode CSV: Unsupported encoding (must be UTF-8 or CP932).")


def insert_data(df: pd.DataFrame, db_path: Path) -> int:
    """Sanitize, map and persist body composition measurements into SQLite.

    Args:
        df: Raw DataFrame parsed from Omron CSV.
        db_path: Absolute filesystem path to the SQLite database file.

    Returns:
        Number of newly inserted records.

    Raises:
        ValueError: If required '測定日' column is missing or DataFrame is empty.
    """
    if df.empty:
        return 0

    init_db(db_path)
    target_cols = [c for c in COLUMN_MAP if c in df.columns]
    if "測定日" not in target_cols:
        raise ValueError("Invalid CSV format: '測定日' column is required.")

    sub_df = (
        df[target_cols]
        .rename(columns=COLUMN_MAP)
        .reindex(columns=list(ALL_COLUMNS))
        .dropna(subset=["measured_at"])
    )
    sub_df["measured_at"] = sub_df["measured_at"].astype(str).str.strip()

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM measurements")
        initial_row: tuple[int] | None = cursor.fetchone()
        initial_count: int = initial_row[0] if initial_row else 0

        sub_df.to_sql("temp_measurements", conn, if_exists="replace", index=False)
        cols_str = ", ".join(ALL_COLUMNS)
        conn.execute(
            f"""
            INSERT OR IGNORE INTO measurements ({cols_str})
            SELECT {cols_str} FROM temp_measurements
            """
        )
        conn.execute("DROP TABLE temp_measurements")
        conn.commit()

        cursor.execute("SELECT COUNT(*) FROM measurements")
        new_row: tuple[int] | None = cursor.fetchone()
        new_count: int = new_row[0] if new_row else 0

        return new_count - initial_count
    finally:
        conn.close()


def load_data(db_path: Path) -> pd.DataFrame:
    """Load all measurements ordered chronologically.

    Args:
        db_path: Absolute filesystem path to the SQLite database file.

    Returns:
        DataFrame with parsed datetime index/column.
    """
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql("SELECT * FROM measurements ORDER BY measured_at ASC", conn)
    finally:
        conn.close()

    if not df.empty:
        df["measured_at"] = pd.to_datetime(df["measured_at"])
    return df


def clear_db(db_path: Path) -> None:
    """Clear all records from the measurements table.

    Args:
        db_path: Absolute filesystem path to the SQLite database file.
    """
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM measurements")
        conn.commit()
    finally:
        conn.close()
