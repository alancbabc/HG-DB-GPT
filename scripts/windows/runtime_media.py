"""Verify fixed third-party runtime downloads for the Windows offline release."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Dict, List

REQUIRED_ARTIFACTS = {"python", "ollama", "nssm", "vcRedist"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_lock(lock_path: Path) -> Dict[str, object]:
    try:
        lock = json.loads(lock_path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid runtime media lock: {error}") from error
    if lock.get("schemaVersion") != 1:
        raise ValueError("Unsupported runtime media lock schema")
    artifacts = lock.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("Runtime media lock must contain an artifacts list")
    ids = [item.get("id") for item in artifacts if isinstance(item, dict)]
    if len(ids) != len(artifacts) or set(ids) != REQUIRED_ARTIFACTS:
        raise ValueError(
            "Runtime media lock must contain exactly: "
            + ", ".join(sorted(REQUIRED_ARTIFACTS))
        )
    return lock


def verify_downloads(lock_path: Path, downloads_root: Path) -> Dict[str, object]:
    lock = load_lock(lock_path)
    root = downloads_root.expanduser().resolve()
    errors: List[str] = []
    verified = []
    for artifact in lock["artifacts"]:
        file_name = artifact.get("fileName")
        expected_size = artifact.get("size")
        expected_hash = artifact.get("sha256")
        if not isinstance(file_name, str) or Path(file_name).name != file_name:
            errors.append(f"Invalid fileName for artifact {artifact.get('id')}")
            continue
        if not isinstance(expected_size, int) or expected_size <= 0:
            errors.append(f"Invalid size for artifact {artifact.get('id')}")
            continue
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            errors.append(f"Invalid SHA-256 for artifact {artifact.get('id')}")
            continue
        path = root / file_name
        if not path.is_file():
            errors.append(f"Missing runtime artifact: {file_name}")
            continue
        if path.stat().st_size != expected_size:
            errors.append(f"Size mismatch: {file_name}")
            continue
        if _sha256(path) != expected_hash.lower():
            errors.append(f"SHA-256 mismatch: {file_name}")
            continue
        verified.append(
            {
                "id": artifact["id"],
                "version": artifact.get("version"),
                "fileName": file_name,
                "size": expected_size,
            }
        )
    return {
        "success": not errors,
        "target": lock.get("target"),
        "verified": verified,
        "errors": errors,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("downloads_root", type=Path)
    parser.add_argument(
        "--lock",
        type=Path,
        default=Path(__file__).with_name("runtime-media.lock.json"),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        report = verify_downloads(args.lock, args.downloads_root)
    except ValueError as error:
        report = {"success": False, "errors": [str(error)]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
