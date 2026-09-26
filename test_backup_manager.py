from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from backup_manager import get_backup_dir, run_backup, set_backup_dir


def test_get_backup_dir_from_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify get_backup_dir reads destination from persisted JSON configuration."""
    # Arrange
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / "data" / "backup_config.json"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    custom_target = tmp_path / "google_drive_sync"
    config_file.write_text(json.dumps({"backup_dir": str(custom_target)}), encoding="utf-8")

    # Act
    resolved = get_backup_dir()

    # Assert
    assert resolved == custom_target.resolve()


def test_get_backup_dir_corrupt_config_fallback_to_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify corrupted JSON config falls back gracefully to BACKUP_DIR env var."""
    # Arrange
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / "data" / "backup_config.json"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text("{invalid_json_format", encoding="utf-8")

    env_target = tmp_path / "env_backup"
    monkeypatch.setenv("BACKUP_DIR", str(env_target))

    # Act
    resolved = get_backup_dir()

    # Assert
    assert resolved == env_target.resolve()


def test_get_backup_dir_empty_key_fallback_to_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify config missing backup_dir key falls back to default ./backups."""
    # Arrange
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / "data" / "backup_config.json"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps({"unrelated": "key"}), encoding="utf-8")
    monkeypatch.delenv("BACKUP_DIR", raising=False)

    # Act
    resolved = get_backup_dir()

    # Assert
    assert resolved == (tmp_path / "backups").resolve()


def test_get_backup_dir_default_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify default fallback when config does not exist and env var is unset."""
    # Arrange
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BACKUP_DIR", raising=False)

    # Act
    resolved = get_backup_dir()

    # Assert
    assert resolved == (tmp_path / "backups").resolve()


def test_set_backup_dir_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify set_backup_dir creates directory and persists config JSON."""
    # Arrange
    monkeypatch.chdir(tmp_path)
    target_dir = tmp_path / "my_drive" / "backups"

    # Act
    res = set_backup_dir(str(target_dir))

    # Assert
    assert res["success"] is True
    assert "バックアップ先を設定しました:" in str(res["message"])
    assert target_dir.exists()

    config_file = tmp_path / "data" / "backup_config.json"
    assert config_file.exists()
    data = json.loads(config_file.read_text(encoding="utf-8"))
    assert data["backup_dir"] == str(target_dir.resolve())


def test_set_backup_dir_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify set_backup_dir reports failure when directory creation raises OSError."""
    # Arrange
    monkeypatch.chdir(tmp_path)
    with patch.object(Path, "mkdir", side_effect=OSError("Read-only file system")):
        # Act
        res = set_backup_dir("/read_only_path")

    # Assert
    assert res["success"] is False
    assert "保存先パスが無効、または書き込み権限がありません: Read-only file system" in str(
        res["message"]
    )


def test_backup_source_dir_not_exists(tmp_path: Path) -> None:
    """Verify backup failure when source directory does not exist."""
    # Arrange
    non_existent = tmp_path / "non_existent_data"

    # Act
    res = run_backup(app_name="test_app", source_dir=str(non_existent))

    # Assert
    assert res["success"] is False
    assert "バックアップ対象が存在しないか空欄です" in str(res["message"])


def test_backup_source_dir_empty(tmp_path: Path) -> None:
    """Verify backup failure when source directory is empty."""
    # Arrange
    empty_dir = tmp_path / "empty_data"
    empty_dir.mkdir(parents=True, exist_ok=True)

    # Act
    res = run_backup(app_name="test_app", source_dir=str(empty_dir))

    # Assert
    assert res["success"] is False
    assert "バックアップ対象が存在しないか空欄です" in str(res["message"])


def test_backup_success_with_default_backups_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify successful backup creation and ensure backup_config.json is excluded."""
    # Arrange
    monkeypatch.chdir(tmp_path)
    source_dir = tmp_path / "data"
    source_dir.mkdir(parents=True, exist_ok=True)

    sample_file = source_dir / "sample.txt"
    sample_file.write_text("body composition persistent data payload", encoding="utf-8")

    config_file = source_dir / "backup_config.json"
    config_file.write_text(json.dumps({"backup_dir": str(tmp_path / "backups")}), encoding="utf-8")

    sub_dir = source_dir / "nested"
    sub_dir.mkdir(parents=True, exist_ok=True)
    nested_file = sub_dir / "nested.db"
    nested_file.write_bytes(b"SQLite format 3\x00")

    monkeypatch.delenv("BACKUP_DIR", raising=False)

    # Act
    res = run_backup(app_name="krd703t", source_dir=str(source_dir))

    # Assert
    assert res["success"] is True
    assert "krd703t_backup_" in str(res["filename"])
    assert "KB" in str(res["size"])
    assert "バックアップ完了:" in str(res["message"])

    destination = Path(str(res["destination"]))
    assert destination.exists()
    assert destination.is_file()

    with zipfile.ZipFile(destination, "r") as zf:
        assert zf.testzip() is None
        names = zf.namelist()
        assert "sample.txt" in names
        assert "nested/nested.db" in names or "nested\\nested.db" in names
        # Verify backup_config.json is excluded from archive
        assert "backup_config.json" not in names


def test_backup_success_with_large_payload_mb(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify size formatting as MB when payload exceeds 1MB."""
    # Arrange
    monkeypatch.chdir(tmp_path)
    source_dir = tmp_path / "data"
    source_dir.mkdir(parents=True, exist_ok=True)
    large_file = source_dir / "large.dat"
    # Write slightly over 1MB of random bytes so compressed zip exceeds 1MB
    large_file.write_bytes(os.urandom(1024 * 1024 + 50 * 1024))

    monkeypatch.delenv("BACKUP_DIR", raising=False)

    # Act
    res = run_backup(app_name="krd703t", source_dir=str(source_dir))

    # Assert
    assert res["success"] is True
    assert "MB" in str(res["size"])
    assert "バックアップ完了:" in str(res["message"])


def test_backup_target_dir_creation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify graceful error handling when destination directory cannot be created."""
    # Arrange
    monkeypatch.chdir(tmp_path)
    source_dir = tmp_path / "data"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "file.txt").write_text("data", encoding="utf-8")

    with patch.object(Path, "mkdir", side_effect=OSError("Permission denied")):
        # Act
        res = run_backup(app_name="err_app", source_dir=str(source_dir))

    # Assert
    assert res["success"] is False
    assert "保存先フォルダの作成に失敗しました: Permission denied" in str(res["message"])


def test_backup_integrity_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify failure report when testzip integrity check detects corruption."""
    # Arrange
    monkeypatch.chdir(tmp_path)
    source_dir = tmp_path / "data"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "file.txt").write_text("data", encoding="utf-8")

    monkeypatch.delenv("BACKUP_DIR", raising=False)

    # Patch testzip on ZipFile to simulate corrupted archive member
    with patch.object(zipfile.ZipFile, "testzip", return_value="corrupted_file.txt"):
        # Act
        res = run_backup(app_name="corrupt_app", source_dir=str(source_dir))

    # Assert
    assert res["success"] is False
    assert "整合性チェック失敗（破損検知）: corrupted_file.txt" in str(res["message"])


def test_backup_finalize_move_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify graceful error reporting when final shutil.move encounters an OSError."""
    # Arrange
    monkeypatch.chdir(tmp_path)
    source_dir = tmp_path / "data"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "file.txt").write_text("data", encoding="utf-8")

    monkeypatch.delenv("BACKUP_DIR", raising=False)

    with patch("shutil.move", side_effect=OSError("Disk full or lock contention")):
        # Act
        res = run_backup(app_name="move_fail_app", source_dir=str(source_dir))

    # Assert
    assert res["success"] is False
    assert "バックアップファイルの確定移動に失敗しました: Disk full or lock contention" in str(
        res["message"]
    )
