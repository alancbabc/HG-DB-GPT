"""Prepare and verify DB-GPT Python media for Windows offline installation."""

import argparse
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

import tomllib

APP_PACKAGES = (
    ("dbgpt", "dbgpt"),
    ("dbgpt-acc-auto", "dbgpt_acc_auto"),
    ("dbgpt-app", "dbgpt_app"),
    ("dbgpt-client", "dbgpt_client"),
    ("dbgpt-ext", "dbgpt_ext"),
    ("dbgpt-sandbox", "dbgpt_sandbox"),
    ("dbgpt-serve", "dbgpt_serve"),
)
MANIFEST_NAME = "python-media-manifest.json"
REQUIREMENTS_NAME = "requirements-windows-x64-py311.txt"


def _wheels(root: Path) -> List[Path]:
    return sorted(root.glob("*.whl")) if root.is_dir() else []


def _locked_version(lock_path: Path, package_name: str) -> str:
    with lock_path.open("rb") as stream:
        lock = tomllib.load(stream)
    versions = {
        package["version"]
        for package in lock.get("package", [])
        if package.get("name") == package_name and package.get("version")
    }
    if len(versions) != 1:
        raise ValueError(
            f"Expected one locked version for {package_name}, found {sorted(versions)}"
        )
    return versions.pop()


def inspect_media(app_wheels: Path, wheelhouse: Path) -> Dict[str, object]:
    """Check that prepared media contains all application and Ollama wheels."""
    errors = []
    app_files = _wheels(app_wheels)
    dependency_files = _wheels(wheelhouse)
    app_names = [path.name.lower().replace("-", "_") for path in app_files]
    dependency_names = [
        path.name.lower().replace("-", "_") for path in dependency_files
    ]

    if not app_wheels.is_dir():
        errors.append(f"Missing app-wheels directory: {app_wheels}")
    if not wheelhouse.is_dir():
        errors.append(f"Missing wheelhouse directory: {wheelhouse}")
    for package_name, wheel_prefix in APP_PACKAGES:
        prefix = f"{wheel_prefix}_"
        if not any(name.startswith(prefix) for name in app_names):
            errors.append(f"Missing application wheel: {package_name}")
    if not any(name.startswith("ollama_") for name in dependency_names):
        errors.append("Missing ollama Python wheel in wheelhouse")

    source_archives = []
    if wheelhouse.is_dir():
        source_archives = sorted(
            path.name
            for path in wheelhouse.iterdir()
            if path.is_file() and path.suffix.lower() != ".whl"
        )
    if source_archives:
        errors.append(
            "Wheelhouse contains non-wheel files: " + ", ".join(source_archives)
        )

    return {
        "success": not errors,
        "appWheelCount": len(app_files),
        "dependencyWheelCount": len(dependency_files),
        "appWheels": [path.name for path in app_files],
        "errors": errors,
    }


def _file_entries(paths: Iterable[Path], root: Path) -> List[Dict[str, object]]:
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "size": path.stat().st_size,
        }
        for path in sorted(paths)
    ]


def write_manifest(root: Path, ollama_version: str) -> Path:
    files = [
        path
        for directory in (root / "app-wheels", root / "wheelhouse")
        for path in _wheels(directory)
    ]
    requirements = root / REQUIREMENTS_NAME
    if requirements.is_file():
        files.append(requirements)
    manifest = {
        "schemaVersion": 1,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "target": "windows-x86_64-cpython-3.11",
        "ollamaPythonVersion": ollama_version,
        "files": _file_entries(files, root),
    }
    path = root / MANIFEST_NAME
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    return path


def verify_media(root: Path) -> Dict[str, object]:
    root = root.expanduser().resolve()
    inspection = inspect_media(root / "app-wheels", root / "wheelhouse")
    errors = list(inspection["errors"])
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        errors.append(f"Missing {MANIFEST_NAME}")
        manifest = {}
    else:
        try:
            manifest = json.loads(manifest_path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"Invalid media manifest: {error}")
            manifest = {}
    if manifest and manifest.get("schemaVersion") != 1:
        errors.append("Unsupported Python media manifest schema")
    for entry in manifest.get("files", []):
        relative = entry.get("path")
        if not isinstance(relative, str):
            errors.append("Invalid Python media manifest entry")
            continue
        path = (root / relative).resolve()
        if root != path and root not in path.parents:
            errors.append(f"Invalid manifest path: {relative}")
        elif not path.is_file():
            errors.append(f"Missing file: {relative}")
        elif path.stat().st_size != entry.get("size"):
            errors.append(f"Size mismatch: {relative}")
    return {
        **inspection,
        "success": not errors,
        "target": manifest.get("target"),
        "ollamaPythonVersion": manifest.get("ollamaPythonVersion"),
        "errors": errors,
    }


def _run(command: Sequence[str], cwd: Path) -> None:
    subprocess.run(list(command), cwd=cwd, check=True)


def _require_build_host() -> None:
    if platform.system() != "Windows":
        raise ValueError("Python media must be prepared on Windows")
    if sys.version_info[:2] != (3, 11) or struct.calcsize("P") * 8 != 64:
        raise ValueError("Python media preparation requires 64-bit Python 3.11")


def prepare_media(output: Path, uv_executable: str = "uv") -> Path:
    """Build workspace wheels and download locked Windows dependencies."""
    _require_build_host()
    repository_root = Path(__file__).resolve().parents[2]
    lock_path = repository_root / "uv.lock"
    if output.exists():
        raise ValueError(f"Output path already exists: {output}")
    ollama_version = _locked_version(lock_path, "ollama")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent.resolve())
    )
    try:
        app_wheels = staging / "app-wheels"
        wheelhouse = staging / "wheelhouse"
        cache = staging / ".uv-cache"
        app_wheels.mkdir()
        wheelhouse.mkdir()
        for package_name, _ in APP_PACKAGES:
            _run(
                (
                    uv_executable,
                    "build",
                    "--package",
                    package_name,
                    "--wheel",
                    "--out-dir",
                    str(app_wheels),
                    "--cache-dir",
                    str(cache),
                    "--no-python-downloads",
                ),
                repository_root,
            )

        requirements = staging / REQUIREMENTS_NAME
        _run(
            (
                uv_executable,
                "export",
                "--package",
                "dbgpt-app",
                "--frozen",
                "--no-dev",
                "--no-emit-workspace",
                "--no-annotate",
                "--no-header",
                "--no-hashes",
                "--output-file",
                str(requirements),
                "--cache-dir",
                str(cache),
            ),
            repository_root,
        )
        with requirements.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(f"ollama=={ollama_version}\n")
        _run(
            (
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--wheel-dir",
                str(wheelhouse),
                "--requirement",
                str(requirements),
            ),
            repository_root,
        )
        shutil.rmtree(cache, ignore_errors=True)
        inspection = inspect_media(app_wheels, wheelhouse)
        if not inspection["success"]:
            raise ValueError("; ".join(inspection["errors"]))
        write_manifest(staging, ollama_version)
        os.replace(staging, output)
        return output
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--uv-executable", default="uv")
    verify = commands.add_parser("verify")
    verify.add_argument("media_root", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        if args.command == "prepare":
            root = prepare_media(args.output, args.uv_executable)
            report = verify_media(root)
            report["mediaRoot"] = str(root)
        else:
            report = verify_media(args.media_root)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        report = {"success": False, "errors": [str(error)]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
