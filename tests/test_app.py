"""Unit test suite for Streamlit dashboard application UI contracts and state transitions."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from db import init_db, insert_data, parse_csv_bytes

_APP_PATH: Path = Path(__file__).resolve().parent.parent / "app.py"

_SAMPLE_CSV_HEADER: str = (
    '"測定日","タイムゾーン","体重(kg)","体脂肪(%)","体脂肪量(kg)","内臓脂肪レベル",'
    '"基礎代謝(kcal)","骨格筋(%)","骨格筋量(kg)","骨格筋率（両腕）(%)","骨格筋率（体幹）(%)",'
    '"骨格筋率（両脚）(%)","皮下脂肪率(%)","皮下脂肪率（両腕）(%)","皮下脂肪率（体幹）(%)",'
    '"皮下脂肪率（両脚）(%)","BMI","体年齢(才)","機種"\n'
)
_SAMPLE_ROW_1: str = (
    '"2026/07/23 01:06","Asia/Tokyo","67.50","17.3","11.70","6.0","1592","34.6","23.40",'
    '"39.3","28.8","51.8","12.0","16.5","10.5","15.9","21.8","36","KRD-703T"\n'
)
_SAMPLE_ROW_2: str = (
    '"2026/07/24 08:56","Asia/Tokyo","67.20","17.0","11.42","6.0","1588","34.8","23.38",'
    '"39.5","29.0","52.0","11.8","16.2","10.3","15.6","21.7","36","KRD-703T"\n'
)


@pytest.fixture
def empty_temp_db(tmp_path: Path) -> Path:
    """Provide an initialized but empty SQLite database."""
    db_path = tmp_path / "empty_test.db"
    init_db(db_path)
    return db_path


@pytest.fixture
def populated_temp_db(tmp_path: Path) -> Path:
    """Provide an SQLite database populated with two sample KRD-703T records."""
    db_path = tmp_path / "populated_test.db"
    init_db(db_path)
    csv_bytes = (_SAMPLE_CSV_HEADER + _SAMPLE_ROW_1 + _SAMPLE_ROW_2).encode("utf-8")
    raw_df = parse_csv_bytes(csv_bytes)
    insert_data(raw_df, db_path)
    return db_path


def test_empty_database_renders_sidebar_and_guidance(empty_temp_db: Path) -> None:
    """Verify that an empty database triggers sidebar upload guidance and instructions."""
    with patch("db.get_default_db_path", return_value=empty_temp_db):
        at = AppTest.from_file(str(_APP_PATH), default_timeout=15)
        at.run()

    assert len(at.exception) == 0
    assert any("KRD-703T" in t.value for t in at.title)
    assert any("測定データが登録されていません" in info.value for info in at.info)
    assert any("データ同期 (CSV)" in h.value for h in at.sidebar.header)
    assert len(at.sidebar.file_uploader) == 1


def test_sidebar_csv_upload_empty_to_populated(empty_temp_db: Path) -> None:
    """Verify that uploading sample CSV via sidebar populates the database and transitions to dashboard."""
    sample_file = Path(__file__).resolve().parent.parent / "KRD-703T_sample.csv"
    assert sample_file.exists()
    content = sample_file.read_bytes()

    with patch("db.get_default_db_path", return_value=empty_temp_db):
        at = AppTest.from_file(str(_APP_PATH), default_timeout=15)
        at.run()

        # Database is initially empty
        assert len(at.metric) == 0

        # Upload via sidebar file_uploader
        uploader = at.sidebar.file_uploader[0]
        uploader.upload(filename="KRD-703T_sample.csv", content=content)
        at.run()

    assert len(at.exception) == 0
    assert len(at.metric) >= 6
    labels = [m.label for m in at.metric]
    assert "体重" in labels
    assert "体脂肪率" in labels
    assert "骨格筋率" in labels


def test_sidebar_csv_upload_duplicate_handling(populated_temp_db: Path) -> None:
    """Verify that uploading already ingested CSV in sidebar displays duplicate record notice."""
    csv_bytes = (_SAMPLE_CSV_HEADER + _SAMPLE_ROW_1).encode("utf-8")

    with patch("db.get_default_db_path", return_value=populated_temp_db):
        at = AppTest.from_file(str(_APP_PATH), default_timeout=15)
        at.run()

        uploader = at.sidebar.file_uploader[0]
        uploader.upload(filename="duplicate_test.csv", content=csv_bytes)
        at.run()

    assert len(at.exception) == 0
    assert any("新規データはありませんでした" in i.value for i in at.sidebar.info)


def test_populated_database_clear_two_step_safety(populated_temp_db: Path) -> None:
    """Verify that database clear button is disabled until 2-step confirmation checkbox is toggled."""
    with patch("db.get_default_db_path", return_value=populated_temp_db):
        at = AppTest.from_file(str(_APP_PATH), default_timeout=15)
        at.run()

        clear_btn = next(b for b in at.button if "全データを消去して初期化" in b.label)
        assert clear_btn.disabled is True

        confirm_cb = next(
            c for c in at.checkbox if "全測定データの完全消去を確認しました" in c.label
        )
        confirm_cb.check()
        at.run()

        clear_btn_active = next(b for b in at.button if "全データを消去して初期化" in b.label)
        assert clear_btn_active.disabled is False

        clear_btn_active.click()
        at.run()

    assert len(at.exception) == 0
    assert any("測定データが登録されていません" in info.value for info in at.info)
