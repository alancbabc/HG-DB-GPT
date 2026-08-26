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

MANIFEST_NAME = "release-manifest.json"
REQUIRED_REPOSITORY_FILES = (
    "configs/dbgpt-windows-offline-ollama.example.toml",
    "scripts/windows/check_ollama_offline.py",
    "scripts/windows/collect-deployment-baseline.ps1",
    "scripts/windows/sqlite_concurrency_probe.py",
    "scripts/windows/Test-OfflineRelease.ps1",
    "scripts/windows/Install-DBGPTOffline.ps1",
    "scripts/windows/Register-DBGPTServices.ps1",
    "scripts/windows/runtime_data.py",
    "scripts/windows/Backup-DBGPTData.ps1",
    "scripts/windows/Restore-DBGPTData.ps1",
)


def _files(root: Path) -> Iterable[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise ValueError(f"Required directory does not exist: {source}")
    shutil.copytree(source, destination)


def _validate_inputs(args: argparse.Namespace) -> None:
    for path in (args.python_installer, args.nssm_exe):
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
    if not list(args.app_wheels.glob("*.whl")):
        raise ValueError("app-wheels must contain DB-GPT wheel files")
    if not (args.ollama_dir / "ollama.exe").is_file():
        raise ValueError("ollama directory must contain ollama.exe")
    if not any(path.is_file() for path in args.models_dir.rglob("*")):
        raise ValueError("models directory must not be empty")
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
        shutil.copy2(
            args.python_installer, staging / "runtime" / "python-installer.exe"
        )
        shutil.copy2(args.nssm_exe, staging / "tools" / "nssm.exe")
        _copy_tree(args.wheelhouse, staging / "wheelhouse")
        _copy_tree(args.app_wheels, staging / "app-wheels")
        _copy_tree(args.ollama_dir, staging / "ollama")
        _copy_tree(args.models_dir, staging / "models")

        for relative in REQUIRED_REPOSITORY_FILES:
            source = repository_root / relative
            if not source.is_file():
                raise ValueError(f"Repository release file is missing: {source}")
            target_parent = (
                staging / "config" if source.suffix == ".toml" else staging / "scripts"
            )
            shutil.copy2(source, target_parent / source.name)

        entries: List[Dict[str, object]] = []
        for path in _files(staging):
            relative = path.relative_to(staging).as_posix()
            entries.append(
                {"path": relative, "size": path.stat().st_size, "sha256": _sha256(path)}
            )
        manifest = {
            "schemaVersion": 1,
            "releaseVersion": args.release_version,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "target": "windows-x86_64-offline",
            "files": entries,
        }
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

    expected = {entry["path"]: entry for entry in manifest.get("files", [])}
    actual = {
        path.relative_to(root).as_posix(): path
        for path in _files(root)
        if path.name != MANIFEST_NAME
    }
    errors = []
    for missing in sorted(set(expected) - set(actual)):
        errors.append(f"Missing file: {missing}")
    for unexpected in sorted(set(actual) - set(expected)):
        errors.append(f"Unexpected file: {unexpected}")
    for relative in sorted(set(expected) & set(actual)):
        path = actual[relative]
        entry = expected[relative]
        if path.stat().st_size != entry["size"]:
            errors.append(f"Size mismatch: {relative}")
        elif _sha256(path) != entry["sha256"]:
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
    build.add_argument("--python-installer", type=Path, required=True)
    build.add_argument("--wheelhouse", type=Path, required=True)
    build.add_argument("--app-wheels", type=Path, required=True)
    build.add_argument("--ollama-dir", type=Path, required=True)
    build.add_argument("--models-dir", type=Path, required=True)
    build.add_argument("--nssm-exe", type=Path, required=True)
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
