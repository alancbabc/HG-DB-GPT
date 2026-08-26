"""Validate an offline Ollama model store without loading model contents."""

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

DEFAULT_MODELS = (
    "qwen3.5:27b-q4_K_M",
    "qwen3.5:9b-q4_K_M",
    "qwen3-embedding:0.6b",
)


def _model_name(manifests_root: Path, manifest_path: Path) -> str | None:
    parts = manifest_path.relative_to(manifests_root).parts
    if len(parts) < 2:
        return None
    repository, tag = parts[-2:]
    return f"{repository}:{tag}"


def _descriptors(manifest: Dict[str, object]) -> Iterable[Dict[str, object]]:
    config = manifest.get("config")
    if isinstance(config, dict):
        yield config
    layers = manifest.get("layers", [])
    if isinstance(layers, list):
        yield from (layer for layer in layers if isinstance(layer, dict))


def inspect_model_store(
    root: Path, required_models: Sequence[str] = DEFAULT_MODELS
) -> Dict[str, object]:
    """Validate manifest references and sizes without hashing large model blobs."""
    root = root.expanduser().resolve()
    manifests_root = root / "manifests"
    blobs_root = root / "blobs"
    errors: List[str] = []
    models: Dict[str, Path] = {}
    referenced_blobs: Dict[str, int] = {}

    if not manifests_root.is_dir():
        errors.append(f"Missing Ollama manifests directory: {manifests_root}")
    if not blobs_root.is_dir():
        errors.append(f"Missing Ollama blobs directory: {blobs_root}")
    if manifests_root.is_dir():
        for manifest_path in sorted(
            path for path in manifests_root.rglob("*") if path.is_file()
        ):
            model_name = _model_name(manifests_root, manifest_path)
            if model_name is None:
                errors.append(f"Invalid Ollama manifest path: {manifest_path}")
                continue
            models[model_name] = manifest_path
            try:
                manifest = json.loads(manifest_path.read_text("utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                errors.append(f"Invalid manifest for {model_name}: {error}")
                continue
            if not isinstance(manifest, dict):
                errors.append(f"Invalid manifest object for {model_name}")
                continue
            descriptors = list(_descriptors(manifest))
            if not descriptors:
                errors.append(f"Manifest has no blob descriptors: {model_name}")
            for descriptor in descriptors:
                digest = descriptor.get("digest")
                size = descriptor.get("size")
                if (
                    not isinstance(digest, str)
                    or not digest.startswith("sha256:")
                    or not isinstance(size, int)
                    or size < 0
                ):
                    errors.append(f"Invalid blob descriptor in {model_name}")
                    continue
                blob_name = digest.replace(":", "-", 1)
                previous_size = referenced_blobs.setdefault(blob_name, size)
                if previous_size != size:
                    errors.append(f"Conflicting size for shared blob: {blob_name}")

    for required in required_models:
        if required not in models:
            errors.append(f"Missing required Ollama model: {required}")
    for blob_name, expected_size in sorted(referenced_blobs.items()):
        blob_path = blobs_root / blob_name
        if not blob_path.is_file():
            errors.append(f"Missing Ollama blob: {blob_name}")
        elif blob_path.stat().st_size != expected_size:
            errors.append(f"Ollama blob size mismatch: {blob_name}")

    return {
        "success": not errors,
        "modelsRoot": str(root),
        "installedModels": sorted(models),
        "requiredModels": list(required_models),
        "referencedBlobCount": len(referenced_blobs),
        "referencedBlobBytes": sum(referenced_blobs.values()),
        "errors": errors,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("models_root", type=Path)
    parser.add_argument("--required-model", action="append", dest="required_models")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    required_models = args.required_models or DEFAULT_MODELS
    report = inspect_model_store(args.models_root, required_models)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
