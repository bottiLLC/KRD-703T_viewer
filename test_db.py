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
    """Fixture providing a temporary SQLite database path."""
    return tmp_path / "test_measurements.db"


def test_get_default_db_path() -> None:
    """Verify get_default_db_path returns expected path inside ./data."""
    # Arrange & Act
    db_path = get_default_db_path()
    # Assert
    assert db_path.name == "body_composition_raw.db"
    assert db_path.parent.name == "data"


def test_init_db_creates_table(temp_db_path: Path) -> None:
    """Verify that init_db creates the database and table without error."""
    # Arrange & Act
    init_db(temp_db_path)
    # Assert
    assert temp_db_path.exists()
    df = load_data(temp_db_path)
    assert df.empty


def test_parse_csv_bytes_with_utf8_and_bom() -> None:
    """Verify parse_csv_bytes handles UTF-8 with BOM properly."""
    # Arrange
    csv_text = "測定日,体重(kg),体脂肪(%)\n2026/08/01 07:00,68.0,20.0\n"
    content_bom = b"\xef\xbb\xbf" + csv_text.encode("utf-8")
    # Act
    df = parse_csv_bytes(content_bom)
    # Assert
    assert list(df.columns) == ["測定日", "体重(kg)", "体脂肪(%)"]
    assert len(df) == 1


def test_parse_csv_bytes_with_cp932() -> None:
    """Verify parse_csv_bytes handles CP932 encoded CSV."""
    # Arrange
    csv_text = "測定日,体重(kg),体脂肪(%)\n2026/08/01 07:00,68.0,20.0\n"
    content_cp932 = csv_text.encode("cp932")
    # Act
    df = parse_csv_bytes(content_cp932)
    # Assert
    assert list(df.columns) == ["測定日", "体重(kg)", "体脂肪(%)"]
    assert len(df) == 1


def test_parse_csv_bytes_invalid_raises_value_error() -> None:
    """Verify invalid binary raises ValueError."""
    # Arrange
    invalid_bytes = b"\x81\x00\x81\x00"
    # Act & Assert
    with pytest.raises(ValueError, match="Failed to decode CSV"):
        parse_csv_bytes(invalid_bytes)


def test_insert_data_and_prevent_duplicates(temp_db_path: Path) -> None:
    """Verify insert_data ignores duplicate timestamps and inserts correctly."""
    # Arrange
    raw_df = pd.DataFrame(
        {
            "測定日": ["2026/08/01 07:00", "2026/08/02 07:00"],
            "体重(kg)": [68.0, 67.5],
            "体脂肪(%)": [20.0, 19.8],
            "骨格筋率（両腕）(%)": [38.5, 38.6],
        }
    )
    # Act
    inserted_first = insert_data(raw_df, temp_db_path)
    loaded_first = load_data(temp_db_path)
    inserted_second = insert_data(raw_df, temp_db_path)
    loaded_second = load_data(temp_db_path)

    # Assert
    assert inserted_first == 2
    assert len(loaded_first) == 2
    assert inserted_second == 0
    assert len(loaded_second) == 2
    assert loaded_second.iloc[0]["skeletal_muscle_arms_pct"] == 38.5


def test_insert_data_missing_measured_at_raises_value_error(temp_db_path: Path) -> None:
    """Verify missing 測定日 column raises ValueError."""
    # Arrange
    invalid_df = pd.DataFrame({"体重(kg)": [68.0]})
    # Act & Assert
    with pytest.raises(ValueError, match="測定日"):
        insert_data(invalid_df, temp_db_path)


def test_insert_empty_df_returns_zero(temp_db_path: Path) -> None:
    """Verify inserting empty dataframe returns 0 without error."""
    # Arrange & Act
    count = insert_data(pd.DataFrame(), temp_db_path)
    # Assert
    assert count == 0


def test_clear_db(temp_db_path: Path) -> None:
    """Verify clear_db empties the table."""
    # Arrange
    raw_df = pd.DataFrame({"測定日": ["2026/08/01 07:00"], "体重(kg)": [68.0]})
    insert_data(raw_df, temp_db_path)
    assert len(load_data(temp_db_path)) == 1

    # Act
    clear_db(temp_db_path)

    # Assert
    assert len(load_data(temp_db_path)) == 0


def test_krd_csv_ingestion(temp_db_path: Path) -> None:
    """Verify ingesting full-specification Omron KRD-703T CSV payload."""
    # Arrange
    csv_header = (
        '"測定日","タイムゾーン","体重(kg)","体脂肪(%)","体脂肪量(kg)","内臓脂肪レベル",'
        '"基礎代謝(kcal)","骨格筋(%)","骨格筋量(kg)","骨格筋率（両腕）(%)","骨格筋率（体幹）(%)",'
        '"骨格筋率（両脚）(%)","皮下脂肪率(%)","皮下脂肪率（両腕）(%)","皮下脂肪率（体幹）(%)",'
        '"皮下脂肪率（両脚）(%)","BMI","体年齢(才)","機種"\n'
    )
    row_1 = (
        '"2026/07/23 01:06","Asia/Tokyo","67.50","17.3","11.70","6.0","1592","34.6","23.40",'
        '"39.3","28.8","51.8","12.0","16.5","10.5","15.9","21.8","36","KRD-703T"\n'
    )
    row_2 = (
        '"2026/07/23 08:56","Asia/Tokyo","67.60","20.7","14.00","6.5","1576","33.1","22.40",'
        '"38.5","26.7","50.4","14.2","19.8","12.4","19.4","21.8","38","KRD-703T"\n'
    )
    csv_bytes = (csv_header + row_1 + row_2).encode("utf-8")

    # Act
    df_raw = parse_csv_bytes(csv_bytes)
    inserted = insert_data(df_raw, temp_db_path)
    loaded = load_data(temp_db_path)

    # Assert
    assert inserted == 2
    assert len(loaded) == 2
    assert "skeletal_muscle_arms_pct" in loaded.columns
    assert "subcutaneous_fat_legs_pct" in loaded.columns
    assert loaded["weight"].min() > 50.0
    assert loaded.iloc[0]["device"] == "KRD-703T"
    assert loaded.iloc[0]["visceral_fat_level"] == 6.0
