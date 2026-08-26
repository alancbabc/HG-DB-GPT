import sqlite3
from pathlib import Path

import pytest

from scripts.windows.runtime_data import backup, restore, verify


def _write(root: Path, relative: str, content: bytes) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _metadata_db(root: Path) -> Path:
    path = root / "metadata" / "dbgpt.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE settings(name TEXT PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO settings VALUES ('language', 'zh')")
        connection.commit()
    finally:
        connection.close()
    return path


def test_backup_verify_restore_and_tamper_detection(tmp_path):
    source = tmp_path / "runtime"
    _metadata_db(source)
    _write(source, "vector_store/chroma.bin", b"vectors")
    _write(source, "uploads/report.txt", b"report")
    _write(source, "logs/ignored.log", b"log")
    _write(source, "temp/ignored.tmp", b"temp")
    backup_root = tmp_path / "backup-001"

    report = backup(source, backup_root)

    assert report["success"] is True
    assert report["fileCount"] == 3
    assert report["sqliteQuickCheck"] == "ok"
    assert not (backup_root / "data/logs").exists()

    restored = tmp_path / "restored"
    restore_report = restore(backup_root, restored)
    assert restore_report["success"] is True
    connection = sqlite3.connect(restored / "metadata/dbgpt.db")
    try:
        assert connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
    finally:
        connection.close()

    with pytest.raises(ValueError, match="already exists"):
        restore(backup_root, restored)

    metadata = backup_root / "data/metadata/dbgpt.db"
    metadata.write_bytes(b"x" * metadata.stat().st_size)
    tampered = verify(backup_root)
    assert tampered["success"] is False
    assert any("quick_check" in error.lower() for error in tampered["errors"])


def test_empty_runtime_data_can_be_backed_up_and_restored(tmp_path):
    source = tmp_path / "empty-runtime"
    source.mkdir()
    backup_root = tmp_path / "empty-backup"

    report = backup(source, backup_root)

    assert report == {
        "success": True,
        "fileCount": 0,
        "sqliteQuickCheck": "not_present",
        "errors": [],
    }
    restored = tmp_path / "empty-restored"
    restore(backup_root, restored)
    assert restored.is_dir()
    assert not list(restored.iterdir())


def test_verify_rejects_missing_data_directory(tmp_path):
    source = tmp_path / "runtime"
    source.mkdir()
    backup_root = tmp_path / "backup"
    backup(source, backup_root)
    (backup_root / "data").rmdir()

    report = verify(backup_root)

    assert report["success"] is False
    assert report["errors"] == ["Missing backup data directory"]
