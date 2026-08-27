"""Verify a Windows DB-GPT installation without accessing the network."""

import argparse
import importlib
import importlib.util
import json
import struct
import sys
from pathlib import Path
from typing import Dict, Iterable, Optional

REQUIRED_MODULES = (
    "ollama",
    "dbgpt",
    "dbgpt_app",
    "dbgpt_ext",
    "dbgpt_serve",
    "chromadb",
    "sqlalchemy",
    "apscheduler",
    "pandas",
    "openpyxl",
    "docx",
    "pypdf",
    "pdfplumber",
    "tiktoken",
)
REQUIRED_STATIC_FILES = ("index.html", "ui-visibility.json")


def _installed_static_root() -> Optional[Path]:
    try:
        spec = importlib.util.find_spec("dbgpt_app")
    except (ImportError, ModuleNotFoundError):
        return None
    if not spec or not spec.submodule_search_locations:
        return None
    package_root = Path(next(iter(spec.submodule_search_locations)))
    return package_root / "static" / "web"


def _installed_cli() -> Path:
    python_dir = Path(sys.executable).resolve().parent
    candidates = (python_dir / "Scripts" / "dbgpt.exe", python_dir / "dbgpt.exe")
    return next((path for path in candidates if path.is_file()), candidates[0])


def check_runtime(
    module_names: Iterable[str] = REQUIRED_MODULES,
    static_root: Optional[Path] = None,
    cli_path: Optional[Path] = None,
    require_python_311: bool = True,
) -> Dict[str, object]:
    """Check installed modules, CLI and prebuilt UI without network calls."""
    errors = []
    architecture = struct.calcsize("P") * 8
    if architecture != 64:
        errors.append(f"Python must be 64-bit, found {architecture}-bit")
    if require_python_311 and sys.version_info[:2] != (3, 11):
        errors.append(
            "Python 3.11 is required, found "
            f"{sys.version_info.major}.{sys.version_info.minor}"
        )

    imported = []
    for module_name in module_names:
        try:
            importlib.import_module(module_name)
            imported.append(module_name)
        except Exception as error:
            errors.append(f"Cannot import required module {module_name}: {error}")

    cli = Path(cli_path) if cli_path is not None else _installed_cli()
    if not cli.is_file():
        errors.append(f"Missing dbgpt CLI: {cli}")

    web_root = (
        Path(static_root) if static_root is not None else _installed_static_root()
    )
    if web_root is None:
        errors.append("Cannot locate installed dbgpt_app static web directory")
    else:
        for relative in REQUIRED_STATIC_FILES:
            if not (web_root / relative).is_file():
                errors.append(f"Missing static web file: {web_root / relative}")

    return {
        "success": not errors,
        "pythonVersion": sys.version.split()[0],
        "pythonArchitectureBits": architecture,
        "importedModules": imported,
        "errors": errors,
    }


def _parse_args() -> argparse.Namespace:
    return argparse.ArgumentParser(description=__doc__).parse_args()


def main() -> int:
    _parse_args()
    report = check_runtime()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
