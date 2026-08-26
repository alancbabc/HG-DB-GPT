import json
from pathlib import Path

from scripts.windows.ollama_model_store import DEFAULT_MODELS, inspect_model_store


def _store(root: Path) -> Path:
    blob = b"model-data"
    blob_path = root / "blobs" / "sha256-shared"
    blob_path.parent.mkdir(parents=True)
    blob_path.write_bytes(blob)
    manifest = {
        "config": {"digest": "sha256:shared", "size": len(blob)},
        "layers": [],
    }
    for model in DEFAULT_MODELS:
        repository, tag = model.split(":", 1)
        path = (
            root
            / "manifests"
            / "registry.ollama.ai"
            / "library"
            / repository
            / tag
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest), "utf-8")
    return blob_path


def test_complete_model_store_passes_without_hashing(tmp_path):
    _store(tmp_path)
    report = inspect_model_store(tmp_path)

    assert report["success"] is True
    assert report["installedModels"] == sorted(DEFAULT_MODELS)
    assert report["referencedBlobCount"] == 1
    assert report["referencedBlobBytes"] == len(b"model-data")


def test_missing_required_model_is_rejected(tmp_path):
    _store(tmp_path)
    missing = DEFAULT_MODELS[0]
    repository, tag = missing.split(":", 1)
    (
        tmp_path
        / "manifests"
        / "registry.ollama.ai"
        / "library"
        / repository
        / tag
    ).unlink()

    report = inspect_model_store(tmp_path)
    assert report["success"] is False
    assert any(missing in error for error in report["errors"])


def test_missing_or_truncated_blob_is_rejected(tmp_path):
    blob_path = _store(tmp_path)
    blob_path.write_bytes(b"short")
    report = inspect_model_store(tmp_path)
    assert report["success"] is False
    assert any("size mismatch" in error for error in report["errors"])

    blob_path.unlink()
    report = inspect_model_store(tmp_path)
    assert report["success"] is False
    assert any("Missing Ollama blob" in error for error in report["errors"])


def test_invalid_manifest_is_rejected(tmp_path):
    _store(tmp_path)
    manifest = next((tmp_path / "manifests").rglob("*q4_K_M"))
    manifest.write_text("not-json", "utf-8")
    report = inspect_model_store(tmp_path)
    assert report["success"] is False
    assert any("Invalid manifest" in error for error in report["errors"])


def test_windows_service_and_config_include_all_offline_models():
    service = Path("scripts/windows/Register-DBGPTServices.ps1").read_text("utf-8")
    config = Path("configs/dbgpt-windows-offline-ollama.example.toml").read_text(
        "utf-8"
    )
    preparation = Path("scripts/windows/Prepare-OllamaModelStore.ps1").read_text(
        "utf-8"
    )

    for model in DEFAULT_MODELS:
        assert model in service
        assert model in preparation
    assert "DBGPT_FALLBACK_LLM_MODEL" in service
    assert "DBGPT_FALLBACK_LLM_MODEL" in config
    assert "OLLAMA_NO_CLOUD=1" in service
    assert "OLLAMA_MAX_LOADED_MODELS=1" in service
    assert "OLLAMA_NUM_PARALLEL=1" in service
