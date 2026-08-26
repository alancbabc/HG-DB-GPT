import json
import subprocess
import sys
from pathlib import Path


def test_sqlite_concurrency_probe_smoke(tmp_path):
    repository_root = Path(__file__).resolve().parents[2]
    script = repository_root / "scripts" / "windows" / "sqlite_concurrency_probe.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--work-dir",
            str(tmp_path),
            "--database-size-mb",
            "2",
            "--duration-seconds",
            "1",
            "--write-interval-seconds",
            "0.05",
            "--readers",
            "2",
        ],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    report = json.loads(result.stdout)
    assert report["success"] is True
    assert all(report["acceptance"].values())
    assert report["metrics"]["writes"] > 0
    assert report["metrics"]["queries"] > 0
    assert report["databaseRetainedAt"] is None
    assert not list(tmp_path.glob("probe-*.db*"))
