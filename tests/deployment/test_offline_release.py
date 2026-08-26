import argparse
import json
import subprocess
from pathlib import Path

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

    (output / "models" / "model.gguf").write_bytes(b"tampered")
    tampered = verify_release(output)
    assert tampered["success"] is False
    assert any("mismatch" in error.lower() for error in tampered["errors"])
