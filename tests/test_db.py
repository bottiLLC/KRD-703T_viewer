"""Unit test suite for SQLite persistence layer and Omron CSV parsing."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from db import (
    clear_db,
    get_default_db_path,
    init_db,
    insert_data,
    load_data,
    parse_csv_bytes,
)


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Provide a temporary SQLite database path fixture."""
    return tmp_path / "test_measurements.db"


def test_get_default_db_path() -> None:
    """Verify get_default_db_path returns expected path inside ./data."""
    db_path = get_default_db_path()
    assert db_path.name == "body_composition_raw.db"
    assert db_path.parent.name == "data"


def test_init_db_creates_table(temp_db_path: Path) -> None:
    """Verify that init_db creates the database and table without error."""
    init_db(temp_db_path)
    assert temp_db_path.exists()
    df = load_data(temp_db_path)
    assert df.empty


def test_parse_csv_bytes_with_utf8_and_bom() -> None:
    """Verify parse_csv_bytes handles UTF-8 with BOM properly."""
    csv_text = "測定日,体重(kg),体脂肪(%)\n2026/08/01 07:00,68.0,20.0\n"
    content_bom = b"\xef\xbb\xbf" + csv_text.encode("utf-8")
    df = parse_csv_bytes(content_bom)
    assert list(df.columns) == ["測定日", "体重(kg)", "体脂肪(%)"]
    assert len(df) == 1


def test_parse_csv_bytes_with_cp932() -> None:
    """Verify parse_csv_bytes handles CP932 encoded CSV."""
    csv_text = "測定日,体重(kg),体脂肪(%)\n2026/08/01 07:00,68.0,20.0\n"
    content_cp932 = csv_text.encode("cp932")
    df = parse_csv_bytes(content_cp932)
    assert list(df.columns) == ["測定日", "体重(kg)", "体脂肪(%)"]
    assert len(df) == 1


def test_parse_csv_bytes_invalid_raises_value_error() -> None:
    """Verify invalid binary raises ValueError."""
    invalid_bytes = b"\x81\x00\x81\x00"
    with pytest.raises(ValueError, match="Failed to decode CSV"):
        parse_csv_bytes(invalid_bytes)


def test_insert_data_and_prevent_duplicates(temp_db_path: Path) -> None:
    """Verify insert_data ignores duplicate timestamps and inserts correctly."""
    raw_df = pd.DataFrame(
        {
            "測定日": ["2026/08/01 07:00", "2026/08/02 07:00"],
            "体重(kg)": [68.0, 67.5],
            "体脂肪(%)": [20.0, 19.8],
            "骨格筋率（両腕）(%)": [38.5, 38.6],
        }
    )
    inserted_first = insert_data(raw_df, temp_db_path)
    loaded_first = load_data(temp_db_path)
    inserted_second = insert_data(raw_df, temp_db_path)
    loaded_second = load_data(temp_db_path)

    assert inserted_first == 2
    assert len(loaded_first) == 2
    assert inserted_second == 0
    assert len(loaded_second) == 2
    assert loaded_second.iloc[0]["skeletal_muscle_arms_pct"] == 38.5


def test_insert_data_missing_measured_at_raises_value_error(temp_db_path: Path) -> None:
    """Verify missing 測定日 column raises ValueError."""
    invalid_df = pd.DataFrame({"体重(kg)": [68.0]})
    with pytest.raises(ValueError, match="測定日"):
        insert_data(invalid_df, temp_db_path)


def test_insert_empty_df_returns_zero(temp_db_path: Path) -> None:
    """Verify inserting empty dataframe returns 0 without error."""
    count = insert_data(pd.DataFrame(), temp_db_path)
    assert count == 0


def test_clear_db(temp_db_path: Path) -> None:
    """Verify clear_db empties the table."""
    raw_df = pd.DataFrame({"測定日": ["2026/08/01 07:00"], "体重(kg)": [68.0]})
    insert_data(raw_df, temp_db_path)
    assert len(load_data(temp_db_path)) == 1

    clear_db(temp_db_path)
    assert len(load_data(temp_db_path)) == 0


def test_krd_csv_ingestion(temp_db_path: Path) -> None:
    """Verify ingesting full-specification Omron KRD-703T CSV payload."""
    csv_header = (
        '"測定日","タイムゾーン","体重(kg)","体脂肪(%)","体脂肪量(kg)","内臓脂肪レベル",'
        '"基礎代謝(kcal)","骨格筋(%)","骨格筋量(kg)","骨格筋率（両腕）(%)","骨格筋率（体幹）(%)",'
        '"骨格筋率（両脚）(%)","皮下脂肪率(%)","皮下脂肪率（両腕）(%)","皮下脂肪率（体幹）(%)",'
        '"皮下脂肪率（両脚）(%)","BMI","体年齢(才)","機種"\n'
    )
    csv_row = (
        '"2026/07/23 01:06","Asia/Tokyo","67.50","17.3","11.70","6.0","1592","34.6","23.40",'
        '"39.3","28.8","51.8","12.0","16.5","10.5","15.9","21.8","36","KRD-703T"\n'
    )
    raw_df = parse_csv_bytes((csv_header + csv_row).encode("utf-8"))
    inserted = insert_data(raw_df, temp_db_path)
    assert inserted == 1

    loaded = load_data(temp_db_path)
    assert len(loaded) == 1
    assert loaded.iloc[0]["weight"] == 67.50
    assert loaded.iloc[0]["skeletal_muscle_arms_pct"] == 39.3
    assert loaded.iloc[0]["subcutaneous_fat_legs_pct"] == 15.9
    assert loaded.iloc[0]["device"] == "KRD-703T"


def test_krd_703t_sample_csv_exact_file_import(temp_db_path: Path) -> None:
    """Verify that actual KRD-703T_sample.csv imports with 100% layout and column fidelity."""
    sample_file = Path(__file__).resolve().parent.parent / "KRD-703T_sample.csv"
    assert sample_file.exists(), f"Sample file not found at {sample_file}"

    sample_bytes = sample_file.read_bytes()
    raw_df = parse_csv_bytes(sample_bytes)
    assert len(raw_df) == 58

    inserted_count = insert_data(raw_df, temp_db_path)
    assert inserted_count == 57  # 1 duplicate row excluded

    loaded = load_data(temp_db_path)
    assert len(loaded) == 57
    assert loaded["measured_at"].isnull().sum() == 0
    assert loaded["weight"].isnull().sum() == 0
    assert (loaded["device"] == "KRD-703T").all()
