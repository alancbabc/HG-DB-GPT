from pathlib import Path

import pytest

from scripts.windows.runtime_data import backup, restore, verify


def _write(root: Path, relative: str, content: bytes) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_backup_verify_restore_and_tamper_detection(tmp_path):
    source = tmp_path / "runtime"
    _write(source, "metadata/dbgpt.db", b"metadata")
    _write(source, "vector_store/chroma.bin", b"vectors")
    _write(source, "uploads/report.txt", b"report")
    _write(source, "logs/ignored.log", b"log")
    _write(source, "temp/ignored.tmp", b"temp")
    backup_root = tmp_path / "backup-001"

    report = backup(source, backup_root)

    assert report["success"] is True
    assert report["fileCount"] == 3
    assert not (backup_root / "data/logs").exists()

    restored = tmp_path / "restored"
    restore_report = restore(backup_root, restored)
    assert restore_report["success"] is True
    assert (restored / "metadata/dbgpt.db").read_bytes() == b"metadata"

    with pytest.raises(ValueError, match="already exists"):
        restore(backup_root, restored)

    (backup_root / "data/metadata/dbgpt.db").write_bytes(b"tampered")
    tampered = verify(backup_root)
    assert tampered["success"] is False
    assert any("mismatch" in error.lower() for error in tampered["errors"])


def test_empty_runtime_data_can_be_backed_up_and_restored(tmp_path):
    source = tmp_path / "empty-runtime"
    source.mkdir()
    backup_root = tmp_path / "empty-backup"

    report = backup(source, backup_root)

    assert report == {"success": True, "fileCount": 0, "errors": []}
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
