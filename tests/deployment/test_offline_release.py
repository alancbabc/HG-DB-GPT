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


def _model_store(root: Path) -> None:
    blob = b"blob"
    _file(root / "blobs" / "sha256-test", blob)
    manifest = json.dumps(
        {
            "config": {"digest": "sha256:test", "size": len(blob)},
            "layers": [],
        }
    ).encode()
    for repository, tag in (
        ("qwen3.5", "27b-q4_K_M"),
        ("qwen3.5", "9b-q4_K_M"),
        ("qwen3-embedding", "0.6b"),
    ):
        _file(
            root
            / "manifests"
            / "registry.ollama.ai"
            / "library"
            / repository
            / tag,
            manifest,
        )


def test_build_verify_and_detect_tampering(tmp_path):
    inputs = tmp_path / "inputs"
    python_installer = _file(inputs / "python.exe")
    vc_redist = _file(inputs / "vc-redist.exe")
    nssm = _file(inputs / "nssm.exe")
    wheelhouse = inputs / "wheelhouse"
    app_wheels = inputs / "app-wheels"
    ollama = inputs / "ollama"
    models = inputs / "models"
    _file(wheelhouse / "dependency-1.0-py3-none-any.whl")
    _file(wheelhouse / "ollama-0.6.0-py3-none-any.whl")
    _file(app_wheels / "dbgpt_app-0.8.1-py3-none-any.whl")
    _file(ollama / "ollama.exe")
    _model_store(models)
    output = tmp_path / "release"
    args = argparse.Namespace(
        output=output,
        release_version="test-1",
        python_installer=python_installer,
        vc_redist=vc_redist,
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
    assert "sha256" not in entries["models/blobs/sha256-test"]
    assert "sha256" not in entries["wheelhouse/dependency-1.0-py3-none-any.whl"]
    assert "sha256" in entries["scripts/Install-DBGPTOffline.ps1"]
    assert "sha256" in entries["runtime/vc-redist.x64.exe"]
    for script in (
        "Backup-DBGPTData.ps1",
        "Restore-DBGPTData.ps1",
        "Test-OfflinePythonMedia.ps1",
        "Test-DBGPTOfflineInstallation.ps1",
        "Prepare-WindowsRuntimeMedia.ps1",
        "ollama_model_store.py",
        "runtime_media.py",
        "runtime-media.lock.json",
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
        vc_redist=_file(inputs / "vc-redist.exe"),
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
    assert "vc-redist.x64.exe" in installer
    assert '"/install", "/quiet", "/norestart"' in installer


def test_service_registration_checks_native_failures_and_protects_models():
    registration = Path("scripts/windows/Register-DBGPTServices.ps1").read_text(
        "utf-8"
    )

    assert "function Invoke-NativeCommand" in registration
    assert "$LASTEXITCODE -ne 0" in registration
    assert "Administrator PowerShell is required" in registration
    assert '"*S-1-5-20:(OI)(CI)RX"' in registration
    assert '"/inheritance:r"' in registration


def test_installed_acceptance_checks_services_loopback_and_offline_models():
    acceptance = Path("scripts/windows/Test-DBGPTOfflineInstallation.ps1").read_text(
        "utf-8"
    )

    assert "Get-Service" in acceptance
    assert "Get-NetTCPConnection" in acceptance
    assert "Get-NetAdapter -Physical" in acceptance
    assert 'response.status -eq "ok"' in acceptance
    assert "check_ollama_offline.py" in acceptance
    assert "ollama_model_store.py" in acceptance


def test_installed_acceptance_fails_fast_when_services_are_missing(tmp_path):
    install = tmp_path / "installed"
    models = tmp_path / "models"
    models.mkdir()
    for relative in (
        "python/python.exe",
        "scripts/check_ollama_offline.py",
        "scripts/ollama_model_store.py",
    ):
        _file(install / relative)

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            "scripts/windows/Test-DBGPTOfflineInstallation.ps1",
            "-InstallRoot",
            str(install),
            "-ModelRoot",
            str(models),
            "-TimeoutSeconds",
            "1",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["success"] is False
    assert report["checks"]["HGTechOllamaRunning"] is False
    assert report["checks"]["HGTechDBGPTRunning"] is False
