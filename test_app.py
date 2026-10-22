"""Unit test suite for Streamlit dashboard application UI contracts and state transitions."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from db import init_db, insert_data, parse_csv_bytes

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


def test_empty_database_renders_initial_upload_and_guide(empty_temp_db: Path) -> None:
    """Verify that an empty database triggers the initial upload form and guidance."""
    # Arrange & Act
    with patch("db.get_default_db_path", return_value=empty_temp_db):
        at = AppTest.from_file("app.py", default_timeout=15)
        at.run()

    # Assert
    assert len(at.exception) == 0
    assert any("KRD-703T" in t.value for t in at.title)
    assert any("測定データが登録されていません" in info.value for info in at.info)
    assert len(at.form) >= 1
    # Check that initial upload submit button exists
    assert any("CSVを取り込んで分析を開始" in btn.label for btn in at.button)


def test_empty_database_initial_upload_empty_submission(empty_temp_db: Path) -> None:
    """Verify that submitting initial upload form without a file displays an error."""
    # Arrange
    with patch("db.get_default_db_path", return_value=empty_temp_db):
        at = AppTest.from_file("app.py", default_timeout=15)
        at.run()

        # Act
        upload_btn = next(b for b in at.button if "CSVを取り込んで分析を開始" in b.label)
        upload_btn.click()
        at.run()

    # Assert
    assert len(at.exception) == 0
    assert any("CSVファイルが指定されていません" in err.value for err in at.error)


def test_populated_database_renders_kpis_and_tabs(populated_temp_db: Path) -> None:
    """Verify that populated database renders KPI metrics and tabbed analysis views."""
    # Arrange & Act
    with patch("db.get_default_db_path", return_value=populated_temp_db):
        at = AppTest.from_file("app.py", default_timeout=15)
        at.run()

    # Assert
    assert len(at.exception) == 0
    assert len(at.metric) >= 6
    labels = [m.label for m in at.metric]
    assert "体重" in labels
    assert "体脂肪率" in labels
    assert "骨格筋率" in labels
    assert "内臓脂肪レベル" in labels
    assert "BMI" in labels
    assert "基礎代謝" in labels

    # Verify filter button exists and is primary
    filter_btn = next(b for b in at.button if "フィルターを適用" in b.label)
    assert filter_btn.proto.type == "primary"

    # Verify reset button exists and is secondary
    reset_btn = next(b for b in at.button if "期間を全期間にリセット" in b.label)
    assert reset_btn.proto.type == "secondary"


def test_populated_database_filter_form_reset(populated_temp_db: Path) -> None:
    """Verify that clicking the filter reset button runs without error."""
    # Arrange
    with patch("db.get_default_db_path", return_value=populated_temp_db):
        at = AppTest.from_file("app.py", default_timeout=15)
        at.run()

        # Act
        reset_btn = next(b for b in at.button if "期間を全期間にリセット" in b.label)
        reset_btn.click()
        at.run()

    # Assert
    assert len(at.exception) == 0
    assert len(at.metric) >= 6


def test_populated_database_incremental_upload_without_file(populated_temp_db: Path) -> None:
    """Verify incremental sync error does not crash or stop the main dashboard."""
    # Arrange
    with patch("db.get_default_db_path", return_value=populated_temp_db):
        at = AppTest.from_file("app.py", default_timeout=15)
        at.run()

        # Act: click incremental upload without selecting file
        sync_btn = next(b for b in at.button if "CSVを取り込んで同期" in b.label)
        sync_btn.click()
        at.run()

    # Assert
    assert len(at.exception) == 0
    assert any("追加するCSVファイルを選択してください" in err.value for err in at.error)
    # Crucial: Metrics and tabs must still be rendered (st.stop was not called)
    assert len(at.metric) >= 6


def test_populated_database_clear_two_step_safety(populated_temp_db: Path) -> None:
    """Verify that database clear button is disabled until 2-step confirmation checkbox is toggled."""
    # Arrange
    with patch("db.get_default_db_path", return_value=populated_temp_db):
        at = AppTest.from_file("app.py", default_timeout=15)
        at.run()

        # Step 1: Initial state - clear button must be disabled
        clear_btn = next(b for b in at.button if "全データを消去して初期化" in b.label)
        assert clear_btn.disabled is True

        # Step 2: Toggle confirmation checkbox
        confirm_cb = next(
            c for c in at.checkbox if "全測定データの完全消去を確認しました" in c.label
        )
        confirm_cb.check()
        at.run()

        # Step 3: Button must now be enabled
        clear_btn_active = next(b for b in at.button if "全データを消去して初期化" in b.label)
        assert clear_btn_active.disabled is False

        # Step 4: Click clear button
        clear_btn_active.click()
        at.run()

    # Assert: after clearing, DB should be empty and empty state is rendered
    assert len(at.exception) == 0
    assert any("測定データが登録されていません" in info.value for info in at.info)
