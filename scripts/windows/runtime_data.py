"""Create, verify, and restore non-destructive DB-GPT runtime-data backups."""

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Set

MANIFEST_NAME = "backup-manifest.json"
DEFAULT_EXCLUDES = {"backups", "logs", "temp"}


def _safe_directory(path: Path, *, must_exist: bool) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == Path(resolved.anchor):
        raise ValueError(f"Refusing to use a filesystem root: {resolved}")
    if must_exist and not resolved.is_dir():
        raise ValueError(f"Directory does not exist: {resolved}")
    return resolved


def _files(root: Path, excludes: Set[str] | None = None) -> Iterable[Path]:
    excludes = excludes or set()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] in excludes:
            continue
        if path.is_symlink():
            raise ValueError(f"Symbolic links are not allowed in runtime data: {path}")
        if path.is_file():
            yield path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup(source: Path, destination: Path) -> Dict[str, object]:
    source = _safe_directory(source, must_exist=True)
    destination = _safe_directory(destination, must_exist=False)
    if destination.exists():
        raise ValueError(f"Backup destination already exists: {destination}")
    if source == destination or source in destination.parents:
        raise ValueError("Backup destination cannot be inside the runtime data root")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent)
    )
    try:
        data_root = staging / "data"
        data_root.mkdir()
        entries: List[Dict[str, object]] = []
        for source_file in _files(source, DEFAULT_EXCLUDES):
            relative = source_file.relative_to(source)
            target = data_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target)
            entries.append(
                {
                    "path": relative.as_posix(),
                    "size": target.stat().st_size,
                    "sha256": _sha256(target),
                }
            )
        manifest = {
            "schemaVersion": 1,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "sourceName": source.name,
            "excludedTopLevelDirectories": sorted(DEFAULT_EXCLUDES),
            "files": entries,
        }
        (staging / MANIFEST_NAME).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(staging, destination)
        return verify(destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def verify(backup_root: Path) -> Dict[str, object]:
    backup_root = _safe_directory(backup_root, must_exist=True)
    manifest_path = backup_root / MANIFEST_NAME
    if not manifest_path.is_file():
        return {"success": False, "errors": [f"Missing {MANIFEST_NAME}"]}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {"success": False, "errors": [f"Invalid manifest: {error}"]}
    data_root = backup_root / "data"
    if not data_root.is_dir():
        return {"success": False, "errors": ["Missing backup data directory"]}
    entries = manifest.get("files")
    if manifest.get("schemaVersion") != 1 or not isinstance(entries, list):
        return {"success": False, "errors": ["Unsupported backup manifest schema"]}
    try:
        expected = {entry["path"]: entry for entry in entries}
    except (KeyError, TypeError):
        return {"success": False, "errors": ["Invalid backup manifest entries"]}
    try:
        actual = {
            path.relative_to(data_root).as_posix(): path for path in _files(data_root)
        }
    except ValueError as error:
        return {"success": False, "errors": [str(error)]}
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
    return {"success": not errors, "fileCount": len(expected), "errors": errors}


def restore(backup_root: Path, destination: Path) -> Dict[str, object]:
    report = verify(backup_root)
    if not report["success"]:
        raise ValueError("Backup verification failed: " + "; ".join(report["errors"]))
    destination = _safe_directory(destination, must_exist=False)
    if destination.exists():
        raise ValueError(f"Restore destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent)
    )
    try:
        shutil.rmtree(staging)
        shutil.copytree(_safe_directory(backup_root, must_exist=True) / "data", staging)
        os.replace(staging, destination)
        return {"success": True, "destination": str(destination), **report}
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("backup")
    create.add_argument("source", type=Path)
    create.add_argument("destination", type=Path)
    check = commands.add_parser("verify")
    check.add_argument("backup_root", type=Path)
    restore_parser = commands.add_parser("restore")
    restore_parser.add_argument("backup_root", type=Path)
    restore_parser.add_argument("destination", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        if args.command == "backup":
            report = backup(args.source, args.destination)
        elif args.command == "verify":
            report = verify(args.backup_root)
        else:
            report = restore(args.backup_root, args.destination)
    except ValueError as error:
        report = {"success": False, "errors": [str(error)]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
