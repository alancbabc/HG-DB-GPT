import hashlib
import json
from pathlib import Path

import pytest

from scripts.windows.runtime_media import (
    REQUIRED_ARTIFACTS,
    load_lock,
    verify_downloads,
)


def _lock(tmp_path, contents):
    artifacts = []
    for artifact_id, content in zip(sorted(REQUIRED_ARTIFACTS), contents):
        artifacts.append(
            {
                "id": artifact_id,
                "version": "test",
                "fileName": f"{artifact_id}.bin",
                "url": f"https://example.invalid/{artifact_id}.bin",
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    path = tmp_path / "runtime-media.lock.json"
    path.write_text(
        json.dumps(
            {"schemaVersion": 1, "target": "windows-x86_64", "artifacts": artifacts}
        ),
        "utf-8",
    )
    return path, artifacts


def test_verify_downloads_accepts_fixed_artifacts_and_detects_tampering(tmp_path):
    contents = [b"python", b"ollama", b"nssm", b"vc-redist"]
    lock_path, artifacts = _lock(tmp_path, contents)
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    for artifact, content in zip(artifacts, contents):
        (downloads / artifact["fileName"]).write_bytes(content)

    report = verify_downloads(lock_path, downloads)
    assert report["success"] is True
    assert len(report["verified"]) == 4

    (downloads / artifacts[0]["fileName"]).write_bytes(b"changed")
    report = verify_downloads(lock_path, downloads)
    assert report["success"] is False
    assert any("mismatch" in error.lower() for error in report["errors"])


def test_runtime_lock_requires_exact_artifact_set(tmp_path):
    lock_path, _ = _lock(tmp_path, [b"1", b"2", b"3", b"4"])
    lock = json.loads(lock_path.read_text("utf-8"))
    lock["artifacts"].pop()
    lock_path.write_text(json.dumps(lock), "utf-8")

    with pytest.raises(ValueError, match="exactly"):
        load_lock(lock_path)


def test_committed_runtime_lock_is_valid():
    lock = load_lock(Path("scripts/windows/runtime-media.lock.json"))
    assert lock["target"] == "windows-x86_64"
