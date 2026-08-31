"""Build and verify a versioned DB-GPT Windows offline release directory."""

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List

try:
    from scripts.windows.ollama_model_store import inspect_model_store
except ModuleNotFoundError:
    from ollama_model_store import inspect_model_store

MANIFEST_NAME = "release-manifest.json"
REQUIRED_REPOSITORY_FILES = (
    "configs/dbgpt-windows-offline-ollama.example.toml",
    "scripts/windows/check_installed_runtime.py",
    "scripts/windows/check_ollama_offline.py",
    "scripts/windows/check_tiktoken_offline.py",
    "scripts/windows/ollama_model_store.py",
    "scripts/windows/collect-deployment-baseline.ps1",
    "scripts/windows/sqlite_concurrency_probe.py",
    "scripts/windows/sqlite_live_read_probe.py",
    "scripts/windows/Test-OfflineRelease.ps1",
    "scripts/windows/Test-OfflinePythonMedia.ps1",
    "scripts/windows/Test-DBGPTOfflineInstallation.ps1",
    "scripts/windows/Set-DBGPTProcessNetworkIsolation.ps1",
    "scripts/windows/Prepare-WindowsRuntimeMedia.ps1",
    "scripts/windows/Install-DBGPTOffline.ps1",
    "scripts/windows/Register-DBGPTServices.ps1",
    "scripts/windows/Start-DBGPT.ps1",
    "scripts/windows/Stop-DBGPT.ps1",
    "scripts/windows/Get-DBGPTStatus.ps1",
    "scripts/windows/Install-DBGPTDesktopShortcuts.ps1",
    "scripts/windows/DBGPTOfflineSetup.Common.ps1",
    "scripts/windows/Test-DBGPTPreflight.ps1",
    "scripts/windows/Install-DBGPTSystem.ps1",
    "scripts/windows/Invoke-DBGPTOfflineSetup.ps1",
    "scripts/windows/runtime_data.py",
    "scripts/windows/Backup-DBGPTData.ps1",
    "scripts/windows/Restore-DBGPTData.ps1",
    "scripts/windows/runtime_media.py",
    "scripts/windows/runtime-media.lock.json",
)

ROOT_RELEASE_FILES = {
    "scripts/windows/Install-DBGPT.cmd": "Install-DBGPT.cmd",
    "configs/dbgpt-windows-offline-deployment.json": "deployment-config.json",
}

HASHED_FILES = {
    "Install-DBGPT.cmd",
    "deployment-config.json",
    "runtime/python-installer.exe",
    "runtime/vc-redist.x64.exe",
    "tools/nssm.exe",
    "ollama/ollama.exe",
}
HASHED_PREFIXES = (
    "app-wheels/",
    "config/",
    "metadata-template/",
    "scripts/",
    "tiktoken-cache/",
)

TIKTOKEN_CACHE_FILENAME = "9b5ad71b2ce5302211f9c61530b329a4922fc6a4"
TIKTOKEN_CACHE_SHA256 = (
    "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
)

METADATA_TEMPLATE_FILES = (
    "alembic.ini",
    "alembic/README",
    "alembic/env.py",
    "alembic/script.py.mako",
)


def _files(root: Path) -> Iterable[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _should_hash(relative: str) -> bool:
    """Return whether a release file needs content-level verification."""
    return relative in HASHED_FILES or relative.startswith(HASHED_PREFIXES)


def _copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise ValueError(f"Required directory does not exist: {source}")
    shutil.copytree(source, destination)


def _validate_inputs(args: argparse.Namespace) -> None:
    for path in (
        args.python_installer,
        args.vc_redist,
        args.nssm_exe,
        args.tiktoken_cache_file,
    ):
        if not path.is_file():
            raise ValueError(f"Required file does not exist: {path}")
    for path in (
        args.wheelhouse,
        args.app_wheels,
        args.ollama_dir,
        args.models_dir,
    ):
        if not path.is_dir():
            raise ValueError(f"Required directory does not exist: {path}")
    if not list(args.wheelhouse.glob("*.whl")):
        raise ValueError("wheelhouse must contain at least one .whl file")
    if not any(
        path.name.lower().startswith("ollama-")
        for path in args.wheelhouse.glob("*.whl")
    ):
        raise ValueError("wheelhouse must contain the ollama Python wheel")
    if not list(args.app_wheels.glob("*.whl")):
        raise ValueError("app-wheels must contain DB-GPT wheel files")
    if not (args.ollama_dir / "ollama.exe").is_file():
        raise ValueError("ollama directory must contain ollama.exe")
    if _sha256(args.tiktoken_cache_file) != TIKTOKEN_CACHE_SHA256:
        raise ValueError(
            "tiktoken cl100k_base cache file does not match the required artifact"
        )
    model_report = inspect_model_store(args.models_dir)
    if not model_report["success"]:
        raise ValueError("; ".join(model_report["errors"]))
    if args.output.exists():
        raise ValueError(f"Output path already exists: {args.output}")


def build_release(args: argparse.Namespace) -> Path:
    _validate_inputs(args)
    repository_root = Path(__file__).resolve().parents[2]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{args.output.name}-", dir=args.output.parent)
    )
    try:
        (staging / "runtime").mkdir()
        (staging / "tools").mkdir()
        (staging / "config").mkdir()
        (staging / "scripts").mkdir()
        (staging / "metadata-template").mkdir()
        (staging / "tiktoken-cache").mkdir()
        shutil.copy2(
            args.python_installer, staging / "runtime" / "python-installer.exe"
        )
        shutil.copy2(args.vc_redist, staging / "runtime" / "vc-redist.x64.exe")
        shutil.copy2(args.nssm_exe, staging / "tools" / "nssm.exe")
        _copy_tree(args.wheelhouse, staging / "wheelhouse")
        _copy_tree(args.app_wheels, staging / "app-wheels")
        _copy_tree(args.ollama_dir, staging / "ollama")
        _copy_tree(args.models_dir, staging / "models")
        shutil.copy2(
            args.tiktoken_cache_file,
            staging / "tiktoken-cache" / TIKTOKEN_CACHE_FILENAME,
        )

        for relative in REQUIRED_REPOSITORY_FILES:
            source = repository_root / relative
            if not source.is_file():
                raise ValueError(f"Repository release file is missing: {source}")
            target_parent = (
                staging / "config" if source.suffix == ".toml" else staging / "scripts"
            )
            shutil.copy2(source, target_parent / source.name)

        for source_relative, target_relative in ROOT_RELEASE_FILES.items():
            source = repository_root / source_relative
            if not source.is_file():
                raise ValueError(f"Repository release file is missing: {source}")
            shutil.copy2(source, staging / target_relative)

        metadata_source = repository_root / "pilot" / "meta_data"
        for relative in METADATA_TEMPLATE_FILES:
            source = metadata_source / relative
            if not source.is_file():
                raise ValueError(f"Metadata template file is missing: {source}")
            destination = staging / "metadata-template" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        entries: List[Dict[str, object]] = []
        for path in _files(staging):
            relative = path.relative_to(staging).as_posix()
            entry: Dict[str, object] = {
                "path": relative,
                "size": path.stat().st_size,
            }
            if _should_hash(relative):
                entry["sha256"] = _sha256(path)
            entries.append(entry)
        manifest = {
            "schemaVersion": 2,
            "releaseVersion": args.release_version,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "target": "windows-x86_64-offline",
            "files": entries,
        }
        source_commit = getattr(args, "source_commit", None)
        source_tag = getattr(args, "source_tag", None)
        if source_commit:
            manifest["sourceCommit"] = source_commit
        if source_tag:
            manifest["sourceTag"] = source_tag
        (staging / MANIFEST_NAME).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(staging, args.output)
        return args.output
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def verify_release(root: Path) -> Dict[str, object]:
    root = root.expanduser().resolve()
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        return {"success": False, "errors": [f"Missing {MANIFEST_NAME}"]}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {"success": False, "errors": [f"Invalid manifest: {error}"]}

    if manifest.get("schemaVersion") not in (1, 2):
        return {"success": False, "errors": ["Unsupported release manifest schema"]}
    try:
        expected = {entry["path"]: entry for entry in manifest.get("files", [])}
    except (KeyError, TypeError):
        return {"success": False, "errors": ["Invalid release manifest entries"]}
    errors = []
    for relative, entry in sorted(expected.items()):
        path = (root / relative).resolve()
        if root != path and root not in path.parents:
            errors.append(f"Invalid manifest path: {relative}")
            continue
        if not path.is_file():
            errors.append(f"Missing file: {relative}")
            continue
        entry = expected[relative]
        if path.stat().st_size != entry["size"]:
            errors.append(f"Size mismatch: {relative}")
        elif entry.get("sha256") and _sha256(path) != entry["sha256"]:
            errors.append(f"SHA-256 mismatch: {relative}")
    return {
        "success": not errors,
        "releaseVersion": manifest.get("releaseVersion"),
        "fileCount": len(expected),
        "errors": errors,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--release-version", required=True)
    build.add_argument("--source-commit")
    build.add_argument("--source-tag")
    build.add_argument("--python-installer", type=Path, required=True)
    build.add_argument("--vc-redist", type=Path, required=True)
    build.add_argument("--wheelhouse", type=Path, required=True)
    build.add_argument("--app-wheels", type=Path, required=True)
    build.add_argument("--ollama-dir", type=Path, required=True)
    build.add_argument("--models-dir", type=Path, required=True)
    build.add_argument("--nssm-exe", type=Path, required=True)
    build.add_argument("--tiktoken-cache-file", type=Path, required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("release_root", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        if args.command == "build":
            root = build_release(args)
            report = verify_release(root)
            report["releaseRoot"] = str(root)
        else:
            report = verify_release(args.release_root)
    except ValueError as error:
        report = {"success": False, "errors": [str(error)]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
