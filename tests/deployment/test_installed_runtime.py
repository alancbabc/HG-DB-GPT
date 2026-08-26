from pathlib import Path

from scripts.windows.check_installed_runtime import check_runtime


def _static_web(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "index.html").write_text("<html></html>", encoding="utf-8")
    (root / "ui-visibility.json").write_text('{"version": 1}', encoding="utf-8")
    return root


def test_runtime_check_accepts_available_modules_and_static_web(tmp_path):
    cli = tmp_path / "dbgpt.exe"
    cli.write_bytes(b"stub")

    report = check_runtime(
        module_names=("json", "sqlite3"),
        static_root=_static_web(tmp_path / "static"),
        cli_path=cli,
        require_python_311=False,
    )

    assert report["success"] is True
    assert report["errors"] == []


def test_runtime_check_reports_missing_module_cli_and_static_asset(tmp_path):
    static_root = tmp_path / "static"
    static_root.mkdir()
    (static_root / "index.html").write_text("<html></html>", encoding="utf-8")

    report = check_runtime(
        module_names=("module_that_does_not_exist_for_dbgpt_test",),
        static_root=static_root,
        cli_path=tmp_path / "missing-dbgpt.exe",
        require_python_311=False,
    )

    assert report["success"] is False
    assert any("module_that_does_not_exist" in error for error in report["errors"])
    assert any("dbgpt CLI" in error for error in report["errors"])
    assert any("ui-visibility.json" in error for error in report["errors"])
