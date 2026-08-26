import argparse
import json
import subprocess
from pathlib import Path

import pytest

from scripts.windows.offline_release import build_release, verify_release


def _file(path: Path, content: bytes = b"stub") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_build_verify_and_detect_tampering(tmp_path):
    inputs = tmp_path / "inputs"
    python_installer = _file(inputs / "python.exe")
    nssm = _file(inputs / "nssm.exe")
    wheelhouse = inputs / "wheelhouse"
    app_wheels = inputs / "app-wheels"
    ollama = inputs / "ollama"
    models = inputs / "models"
    _file(wheelhouse / "dependency-1.0-py3-none-any.whl")
    _file(wheelhouse / "ollama-0.6.0-py3-none-any.whl")
    _file(app_wheels / "dbgpt_app-0.8.1-py3-none-any.whl")
    _file(ollama / "ollama.exe")
    _file(models / "model.gguf")
    output = tmp_path / "release"
    args = argparse.Namespace(
        output=output,
        release_version="test-1",
        python_installer=python_installer,
        wheelhouse=wheelhouse,
        app_wheels=app_wheels,
        ollama_dir=ollama,
        models_dir=models,
        nssm_exe=nssm,
    )

    build_release(args)

    report = verify_release(output)
    assert report["success"] is True
    assert report["fileCount"] > 6
    manifest = json.loads((output / "release-manifest.json").read_text("utf-8"))
    assert manifest["schemaVersion"] == 2
    entries = {entry["path"]: entry for entry in manifest["files"]}
    assert "sha256" not in entries["models/model.gguf"]
    assert "sha256" not in entries["wheelhouse/dependency-1.0-py3-none-any.whl"]
    assert "sha256" in entries["scripts/Install-DBGPTOffline.ps1"]
    for script in (
        "Backup-DBGPTData.ps1",
        "Restore-DBGPTData.ps1",
        "runtime_data.py",
        "sqlite_live_read_probe.py",
    ):
        assert (output / "scripts" / script).is_file()

    powershell = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(output / "scripts" / "Test-OfflineRelease.ps1"),
            "-ReleaseRoot",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert powershell.returncode == 0, powershell.stderr
    assert json.loads(powershell.stdout)["success"] is True

    installed = tmp_path / "installed"
    for relative in (
        "tools/nssm.exe",
        "ollama/ollama.exe",
        "python/Scripts/dbgpt.exe",
        "config/dbgpt-windows-offline-ollama.toml",
    ):
        _file(installed / relative)
    service_what_if = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(output / "scripts" / "Register-DBGPTServices.ps1"),
            "-InstallRoot",
            str(installed),
            "-DataRoot",
            str(tmp_path / "data"),
            "-ModelRoot",
            str(tmp_path / "models-installed"),
            "-LlmModel",
            "local-llm",
            "-EmbeddingModel",
            "local-embed",
            "-WhatIf",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert service_what_if.returncode == 0, service_what_if.stderr

    _file(output / "local-install-note.txt", b"operator note")
    assert verify_release(output)["success"] is True

    install_script = output / "scripts" / "Install-DBGPTOffline.ps1"
    install_script.write_bytes(b"tampered")
    tampered = verify_release(output)
    assert tampered["success"] is False
    assert any("mismatch" in error.lower() for error in tampered["errors"])


def test_build_requires_ollama_python_wheel(tmp_path):
    inputs = tmp_path / "inputs"
    args = argparse.Namespace(
        output=tmp_path / "release",
        release_version="test-1",
        python_installer=_file(inputs / "python.exe"),
        wheelhouse=inputs / "wheelhouse",
        app_wheels=inputs / "app-wheels",
        ollama_dir=inputs / "ollama",
        models_dir=inputs / "models",
        nssm_exe=_file(inputs / "nssm.exe"),
    )
    _file(args.wheelhouse / "dependency-1.0-py3-none-any.whl")
    _file(args.app_wheels / "dbgpt_app-0.8.1-py3-none-any.whl")
    _file(args.ollama_dir / "ollama.exe")
    _file(args.models_dir / "model.gguf")

    with pytest.raises(ValueError, match="ollama Python wheel"):
        build_release(args)


def test_installer_explicitly_installs_ollama_and_runs_runtime_check():
    installer = Path("scripts/windows/Install-DBGPTOffline.ps1").read_text("utf-8")

    assert "@appWheels ollama" in installer
    assert "check_installed_runtime.py" in installer
