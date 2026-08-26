import json
from pathlib import Path

from scripts.windows.offline_media import (
    APP_PACKAGES,
    _locked_version,
    inspect_media,
    verify_media,
    write_manifest,
)


def _file(path: Path, content: bytes = b"wheel") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _valid_media(root: Path) -> None:
    for _, wheel_prefix in APP_PACKAGES:
        _file(root / "app-wheels" / f"{wheel_prefix}-0.8.1-py3-none-any.whl")
    _file(root / "wheelhouse" / "dependency-1.0-py3-none-any.whl")
    _file(root / "wheelhouse" / "ollama-0.6.0-py3-none-any.whl")
    _file(root / "requirements-windows-x64-py311.txt", b"ollama==0.6.0\n")


def test_inspect_and_verify_complete_python_media(tmp_path):
    _valid_media(tmp_path)
    inspection = inspect_media(tmp_path / "app-wheels", tmp_path / "wheelhouse")
    assert inspection["success"] is True

    write_manifest(tmp_path, "0.6.0")
    report = verify_media(tmp_path)
    assert report["success"] is True
    assert report["appWheelCount"] == len(APP_PACKAGES)
    assert report["ollamaPythonVersion"] == "0.6.0"
    manifest = json.loads(
        (tmp_path / "python-media-manifest.json").read_text("utf-8")
    )
    assert all("sha256" not in entry for entry in manifest["files"])


def test_verify_detects_missing_wheel_and_size_change(tmp_path):
    _valid_media(tmp_path)
    write_manifest(tmp_path, "0.6.0")
    (tmp_path / "app-wheels" / "dbgpt_app-0.8.1-py3-none-any.whl").unlink()
    report = verify_media(tmp_path)
    assert report["success"] is False
    assert any("dbgpt-app" in error for error in report["errors"])
    assert any("Missing file" in error for error in report["errors"])


def test_inspect_rejects_source_archives(tmp_path):
    _valid_media(tmp_path)
    _file(tmp_path / "wheelhouse" / "source-package.tar.gz")
    report = inspect_media(tmp_path / "app-wheels", tmp_path / "wheelhouse")
    assert report["success"] is False
    assert any("non-wheel" in error for error in report["errors"])


def test_locked_ollama_version_is_read_from_uv_lock(tmp_path):
    lock = tmp_path / "uv.lock"
    lock.write_text(
        'version = 1\n[[package]]\nname = "ollama"\nversion = "0.6.0"\n',
        "utf-8",
    )
    assert _locked_version(lock, "ollama") == "0.6.0"


def test_offline_smoke_script_never_uses_package_index():
    script = Path("scripts/windows/Test-OfflinePythonMedia.ps1").read_text("utf-8")
    assert "--no-index" in script
    assert "-m pip check" in script
    assert "check_installed_runtime.py" in script


def test_preparation_builds_dependency_wheels_on_connected_host():
    script = Path("scripts/windows/offline_media.py").read_text("utf-8")
    assert '"wheel",' in script
    assert '"--wheel-dir",' in script
    assert '"download",' not in script
