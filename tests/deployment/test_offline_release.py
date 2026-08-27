import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts.windows import offline_release
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


def test_build_verify_and_detect_tampering(tmp_path, monkeypatch):
    inputs = tmp_path / "inputs"
    python_installer = _file(inputs / "python.exe")
    vc_redist = _file(inputs / "vc-redist.exe")
    nssm = _file(inputs / "nssm.exe")
    tiktoken_cache = _file(inputs / "cl100k_base.cache", b"offline-cache")
    monkeypatch.setattr(
        offline_release,
        "TIKTOKEN_CACHE_SHA256",
        hashlib.sha256(tiktoken_cache.read_bytes()).hexdigest(),
    )
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
        tiktoken_cache_file=tiktoken_cache,
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
    assert "sha256" in entries[
        f"tiktoken-cache/{offline_release.TIKTOKEN_CACHE_FILENAME}"
    ]
    for relative in (
        "metadata-template/alembic.ini",
        "metadata-template/alembic/README",
        "metadata-template/alembic/env.py",
        f"tiktoken-cache/{offline_release.TIKTOKEN_CACHE_FILENAME}",
        "metadata-template/alembic/script.py.mako",
    ):
        assert "sha256" in entries[relative]
    for script in (
        "Backup-DBGPTData.ps1",
        "Restore-DBGPTData.ps1",
        "Test-OfflinePythonMedia.ps1",
        "Test-DBGPTOfflineInstallation.ps1",
        "Set-DBGPTProcessNetworkIsolation.ps1",
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

    installed = tmp_path / "installed path with spaces"
    for relative in (
        "tools/nssm.exe",
        "ollama/ollama.exe",
        "python/Scripts/dbgpt.exe",
        "config/dbgpt-windows-offline-ollama.toml",
        "metadata-template/alembic/env.py",
        f"tiktoken-cache/{offline_release.TIKTOKEN_CACHE_FILENAME}",
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


def test_build_requires_ollama_python_wheel(tmp_path, monkeypatch):
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
        tiktoken_cache_file=_file(inputs / "cl100k_base.cache"),
    )
    monkeypatch.setattr(
        offline_release,
        "TIKTOKEN_CACHE_SHA256",
        hashlib.sha256(args.tiktoken_cache_file.read_bytes()).hexdigest(),
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
    assert 'Join-Path $release "tiktoken-cache"' in installer
    assert "vc-redist.x64.exe" in installer
    assert '"/install", "/quiet", "/norestart"' in installer
    assert "Windows restart is required before rerunning" in installer
    assert "runtime-media.lock.json" in installer
    assert "$vcProcess.WaitForExit()" in installer
    assert "$process.WaitForExit()" in installer
    assert "-WindowStyle Hidden -Wait -PassThru" not in installer
    assert installer.index("$vcProcess = Start-Process") < installer.index(
        "New-Item -ItemType Directory -Path $InstallRoot"
    )


def test_powershell_validators_set_explicit_success_exit_codes():
    for relative in (
        "Test-OfflineRelease.ps1",
        "Test-OfflinePythonMedia.ps1",
        "Test-DBGPTOfflineInstallation.ps1",
        "Set-DBGPTProcessNetworkIsolation.ps1",
    ):
        script = Path("scripts/windows", relative).read_text("utf-8")
        assert script.rstrip().endswith("exit 0"), relative


def test_service_registration_checks_native_failures_and_protects_models():
    registration = Path("scripts/windows/Register-DBGPTServices.ps1").read_text(
        "utf-8"
    )

    assert "function Invoke-NativeCommand" in registration
    assert "$LASTEXITCODE -ne 0" in registration
    assert "Administrator PowerShell is required" in registration
    assert '"*S-1-5-20:(OI)(CI)RX"' in registration
    assert '"/inheritance:r"' in registration
    assert registration.index('"/inheritance:r"') < registration.index(
        '"/grant:r"'
    )
    assert '"/reset"' in registration
    assert "PYTHONUTF8=1" in registration
    assert "PYTHONIOENCODING=utf-8" in registration
    assert "TIKTOKEN_CACHE_DIR=$tiktokenCache" in registration
    assert "DBGPT_CONTEXT_LENGTH=$ContextLength" in registration
    assert "[int]$ContextLength = 16384" in registration
    assert 'Join-Path $install "metadata-template"' in registration
    assert "Copy-Item -LiteralPath $_.FullName" in registration


def test_installed_acceptance_checks_services_loopback_and_offline_models():
    acceptance = Path("scripts/windows/Test-DBGPTOfflineInstallation.ps1").read_text(
        "utf-8"
    )

    assert "Get-Service" in acceptance
    assert "Get-NetTCPConnection" in acceptance
    assert "netstat.exe" in acceptance
    assert "Get-NetAdapter -Physical" in acceptance
    assert 'response.status -eq "ok"' in acceptance
    assert "check_ollama_offline.py" in acceptance
    assert "check_tiktoken_offline.py" in acceptance
    assert "ollama_model_store.py" in acceptance
    assert "modelStoreProtectedFromOperator" in acceptance
    assert "RequireProcessNetworkIsolation" in acceptance
    assert "Set-DBGPTProcessNetworkIsolation.ps1" in acceptance


def test_process_network_isolation_is_scoped_and_reversible():
    isolation = Path(
        "scripts/windows/Set-DBGPTProcessNetworkIsolation.ps1"
    ).read_text("utf-8")

    assert 'RemoteAddress "Internet"' in isolation
    assert "python\\python.exe" in isolation
    assert "ollama\\ollama.exe" in isolation
    assert "ollama\\lib\\ollama\\llama-server.exe" in isolation
    assert 'ValidateSet("Apply", "Remove", "Status")' in isolation
    assert "Remove-NetFirewallRule -Name" in isolation
    assert "Get-NetFirewallProfile" in isolation


def test_installed_acceptance_fails_fast_when_services_are_missing(tmp_path):
    install = tmp_path / "installed"
    models = tmp_path / "models"
    models.mkdir()
    for relative in (
        "python/python.exe",
        "scripts/check_ollama_offline.py",
        "scripts/check_tiktoken_offline.py",
        "scripts/ollama_model_store.py",
        f"tiktoken-cache/{offline_release.TIKTOKEN_CACHE_FILENAME}",
        "metadata-template/alembic/env.py",
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
            "-OllamaServiceName",
            "HGTechTestMissingOllama",
            "-DBGPTServiceName",
            "HGTechTestMissingDBGPT",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["success"] is False
    assert report["checks"]["HGTechTestMissingOllamaRunning"] is False
    assert report["checks"]["HGTechTestMissingDBGPTRunning"] is False


def test_offline_config_uses_one_context_length_setting():
    config = Path("configs/dbgpt-windows-offline-ollama.example.toml").read_text(
        "utf-8"
    )

    assert '[service.web.agent_context]' in config
    assert 'max_context_tokens = "${env:DBGPT_CONTEXT_LENGTH:-16384}"' in config
    assert config.count('context_length = "${env:DBGPT_CONTEXT_LENGTH:-16384}"') == 2
