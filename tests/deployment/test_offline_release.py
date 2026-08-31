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
        source_commit="0123456789abcdef",
        source_tag="offline-test-1",
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
    assert manifest["sourceCommit"] == "0123456789abcdef"
    assert manifest["sourceTag"] == "offline-test-1"
    entries = {entry["path"]: entry for entry in manifest["files"]}
    assert "sha256" not in entries["models/blobs/sha256-test"]
    assert "sha256" not in entries["wheelhouse/dependency-1.0-py3-none-any.whl"]
    assert "sha256" in entries["scripts/Install-DBGPTOffline.ps1"]
    assert "sha256" in entries["Install-DBGPT.cmd"]
    assert "sha256" in entries["deployment-config.json"]
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
        "Start-DBGPT.ps1",
        "Stop-DBGPT.ps1",
        "Get-DBGPTStatus.ps1",
        "Install-DBGPTDesktopShortcuts.ps1",
        "DBGPTOfflineSetup.Common.ps1",
        "Test-DBGPTPreflight.ps1",
        "Install-DBGPTSystem.ps1",
        "Invoke-DBGPTOfflineSetup.ps1",
        "Prepare-WindowsRuntimeMedia.ps1",
        "ollama_model_store.py",
        "runtime_media.py",
        "runtime-media.lock.json",
        "runtime_data.py",
        "sqlite_live_read_probe.py",
    ):
        assert (output / "scripts" / script).is_file()
    assert (output / "Install-DBGPT.cmd").is_file()
    assert (output / "deployment-config.json").is_file()

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
        "python/python.exe",
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
    assert '"ollama", "tools", "scripts", "metadata-template", "tiktoken-cache"' in installer
    assert "vc-redist.x64.exe" in installer
    assert '"TargetDir=`"$pythonRoot`""' in installer
    assert "Python installer did not create the expected executable" in installer
    assert '"`"$pythonInstallLog`""' in installer
    assert '"Include_launcher=0"' in installer
    assert '"AssociateFiles=0"' in installer
    assert '$legacyBrokenRoot = "C:\\Program"' in installer
    assert 'resumeVersion -eq "0.8.1-dev-deploy-20260831-stage21.3"' in installer
    assert '@("/uninstall", "/quiet")' in installer
    assert '"/install", "/quiet", "/norestart"' in installer
    assert "Windows restart is required before rerunning" in installer
    assert "runtime-media.lock.json" in installer
    assert "$vcProcess.WaitForExit()" in installer
    assert "$process.WaitForExit()" in installer
    assert "-WindowStyle Hidden -Wait -PassThru" not in installer
    assert installer.index("$vcProcess = Start-Process") < installer.index(
        "New-Item -ItemType Directory -Force -Path $InstallRoot"
    )
    assert "[switch]$Resume" in installer
    assert "Resuming incomplete release" in installer
    assert "Refusing to overwrite a completed installation" in installer
    assert "Refusing to overwrite an unrecognized existing directory" in installer
    assert ".dbgpt-offline-installing.json" in installer


def test_powershell_validators_set_explicit_success_exit_codes():
    for relative in (
        "Test-OfflineRelease.ps1",
        "Test-OfflinePythonMedia.ps1",
        "Test-DBGPTOfflineInstallation.ps1",
        "Set-DBGPTProcessNetworkIsolation.ps1",
    ):
        script = Path("scripts/windows", relative).read_text("utf-8")
        assert script.rstrip().endswith("exit 0"), relative


def test_registration_uses_ollama_service_and_current_user_shortcuts():
    registration = Path("scripts/windows/Register-DBGPTServices.ps1").read_text(
        "utf-8"
    )

    assert "function Invoke-NativeCommand" in registration
    assert "$LASTEXITCODE -ne 0" in registration
    assert "Administrator PowerShell is required" in registration
    assert '"install", "HGTechOllama"' in registration
    assert '"install", "HGTechDBGPT"' not in registration
    assert r"NT AUTHORITY\LocalService" not in registration
    assert "S-1-5-19" not in registration
    assert '"*S-1-5-20:(OI)(CI)RX"' in registration
    assert '"/inheritance:r"' in registration
    assert registration.index('"/inheritance:r"') < registration.index(
        '"/grant:r"'
    )
    assert '"/reset"' in registration
    assert "Install-DBGPTDesktopShortcuts.ps1" in registration
    assert "RuntimeUserSid" in registration
    assert "SkipDesktopShortcuts" in registration
    assert "RepairExisting" in registration
    assert "[int]$ContextLength = 16384" in registration
    assert 'Join-Path $install "metadata-template"' in registration
    assert "Copy-Item -LiteralPath $_.FullName" in registration


def test_installed_acceptance_checks_user_process_loopback_and_offline_models():
    acceptance = Path("scripts/windows/Test-DBGPTOfflineInstallation.ps1").read_text(
        "utf-8"
    )

    assert "Get-Service" in acceptance
    assert "dbgptProcessRunning" in acceptance
    assert "dbgptRunsAsCurrentUser" in acceptance
    assert "dbgptRunsNonElevated" in acceptance
    assert "legacyDBGPTServiceInactive" in acceptance
    assert "dbgptOwnerVerification" in acceptance
    assert r"NT AUTHORITY\LOCAL SERVICE" in acceptance
    assert "startShortcutInstalled" in acceptance
    assert "stopShortcutInstalled" in acceptance
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
    data = tmp_path / "data"
    models = tmp_path / "models"
    data.mkdir()
    models.mkdir()
    for relative in (
        "python/python.exe",
        "scripts/check_ollama_offline.py",
        "scripts/check_tiktoken_offline.py",
        "scripts/ollama_model_store.py",
        "scripts/Start-DBGPT.ps1",
        "scripts/Stop-DBGPT.ps1",
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
            "-DataRoot",
            str(data),
            "-TimeoutSeconds",
            "1",
            "-OllamaServiceName",
            "HGTechTestMissingOllama",
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
    assert report["checks"]["dbgptProcessRunning"] is False


def test_current_user_launch_scripts_preserve_original_file_permissions():
    start = Path("scripts/windows/Start-DBGPT.ps1").read_text("utf-8")
    stop = Path("scripts/windows/Stop-DBGPT.ps1").read_text("utf-8")
    shortcuts = Path(
        "scripts/windows/Install-DBGPTDesktopShortcuts.ps1"
    ).read_text("utf-8")
    backup = Path("scripts/windows/Backup-DBGPTData.ps1").read_text("utf-8")
    restore = Path("scripts/windows/Restore-DBGPTData.ps1").read_text("utf-8")

    assert "WindowsIdentity]::GetCurrent" in start
    assert "elevated = $isElevated" in start
    assert 'Join-Path $configRoot "encrypt.key"' in start
    assert "DBGPT_ENCRYPT_KEY" in start
    assert '"dbgpt.cli.cli_scripts"' in start
    assert "TIKTOKEN_CACHE_DIR" in start
    assert "PYTHONUTF8" in start
    assert "dbgpt.pid" in start
    assert "dbgpt.pid" in stop
    assert "[char]0x542f" in shortcuts
    assert "[char]0x52a8" in shortcuts
    assert "[char]0x505c" in shortcuts
    assert "[char]0x6b62" in shortcuts
    assert "Start-DBGPT.ps1" in backup
    assert "Stop-DBGPT.ps1" in backup
    assert "refusing an inconsistent backup" in backup
    assert "S-1-5-19" not in restore
    assert "LocalService" not in restore


def test_desktop_shortcuts_are_created_in_requested_directory(tmp_path):
    install = tmp_path / "installed path"
    data = tmp_path / "data path"
    desktop = tmp_path / "desktop path"
    data.mkdir()
    desktop.mkdir()
    _file(install / "scripts" / "Start-DBGPT.ps1")
    _file(install / "scripts" / "Stop-DBGPT.ps1")

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            "scripts/windows/Install-DBGPTDesktopShortcuts.ps1",
            "-InstallRoot",
            str(install),
            "-DataRoot",
            str(data),
            "-DesktopPath",
            str(desktop),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert (desktop / "启动 DB-GPT.lnk").is_file()
    assert (desktop / "停止 DB-GPT.lnk").is_file()


def test_offline_config_uses_one_context_length_setting():
    config = Path("configs/dbgpt-windows-offline-ollama.example.toml").read_text(
        "utf-8"
    )

    assert '[service.web.agent_context]' in config
    assert 'max_context_tokens = "${env:DBGPT_CONTEXT_LENGTH:-16384}"' in config
    assert config.count('context_length = "${env:DBGPT_CONTEXT_LENGTH:-16384}"') == 2


def test_one_click_setup_keeps_a_small_installation_path():
    entry = Path("scripts/windows/Install-DBGPT.cmd").read_text("utf-8")
    orchestrator = Path(
        "scripts/windows/Invoke-DBGPTOfflineSetup.ps1"
    ).read_text("utf-8")
    system = Path("scripts/windows/Install-DBGPTSystem.ps1").read_text("utf-8")
    preflight = Path("scripts/windows/Test-DBGPTPreflight.ps1").read_text("utf-8")

    assert "Invoke-DBGPTOfflineSetup.ps1" in entry
    assert '$processArguments["Verb"] = "RunAs"' in orchestrator
    assert "do not start it from an elevated terminal" not in orchestrator
    assert "Write-DBGPTSetupState" not in orchestrator
    assert "Start-DBGPT.ps1" not in orchestrator
    assert "Test-DBGPTOfflineInstallation.ps1" not in orchestrator
    assert "deployment-config.local.json" in orchestrator
    assert orchestrator.index("deployment-config.local.json") < orchestrator.index(
        'Join-Path $release "deployment-config.json"'
    )
    assert "RuntimeUserSid" in system
    assert "-SkipDesktopShortcuts -RepairExisting" in system
    assert "Start-Service -Name \"HGTechOllama\"" in system
    assert "check_ollama_offline.py" in system
    assert "Write-DBGPTSetupState" not in system
    assert "Get-NetAdapter -Physical" not in preflight
    assert "RequirePhysicalOffline" not in preflight
    assert "diskSpaceSufficient" in preflight
    assert "Runtime destination must not be inside the release media" in preflight


def test_one_click_cmd_passes_release_root_without_a_trailing_quote(tmp_path):
    release = tmp_path / "offline media with spaces"
    scripts = release / "scripts"
    scripts.mkdir(parents=True)
    (release / "Install-DBGPT.cmd").write_text(
        Path("scripts/windows/Install-DBGPT.cmd").read_text("utf-8"),
        encoding="utf-8",
    )
    (scripts / "Invoke-DBGPTOfflineSetup.ps1").write_text(
        "param([string]$ReleaseRoot)\n"
        "[Console]::Write((Resolve-Path -LiteralPath $ReleaseRoot).Path)\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        ["cmd.exe", "/d", "/c", str(release / "Install-DBGPT.cmd")],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(release.resolve())
    assert '"' not in result.stdout


def test_target_machine_scripts_do_not_embed_preparation_machine_paths():
    target_scripts = (
        "Install-DBGPTOffline.ps1",
        "Register-DBGPTServices.ps1",
        "Install-DBGPTDesktopShortcuts.ps1",
        "Start-DBGPT.ps1",
        "Stop-DBGPT.ps1",
        "Invoke-DBGPTOfflineSetup.ps1",
        "Install-DBGPTSystem.ps1",
        "Test-DBGPTPreflight.ps1",
    )
    for name in target_scripts:
        content = Path("scripts/windows", name).read_text("utf-8").lower()
        assert "c:\\users\\" not in content, name
        assert "15712" not in content, name
        assert "desktop\\hgtech" not in content, name


def test_one_click_deployment_defaults_are_minimal_and_loopback_only():
    config = json.loads(
        Path("configs/dbgpt-windows-offline-deployment.json").read_text("utf-8")
    )

    assert "requirePhysicalOffline" not in config
    assert "startAfterInstall" not in config
    assert "openBrowserAfterInstall" not in config
    assert config["webPort"] == 5670
    assert config["ollamaPort"] == 11434
    assert config["contextLength"] == 16384
    assert config["mainLlmModel"] == "qwen3.5:27b-q4_K_M"
    assert config["fallbackLlmModel"] == "qwen3.5:9b-q4_K_M"
    assert config["embeddingModel"] == "qwen3-embedding:0.6b"
