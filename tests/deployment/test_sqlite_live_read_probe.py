import argparse
import sqlite3
import threading
import time

import pytest

from scripts.windows.sqlite_live_read_probe import run_probe


def test_live_probe_observes_external_writer_and_never_writes(tmp_path):
    database = tmp_path / "live.db"
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE batch(id INTEGER PRIMARY KEY)")
    connection.commit()
    connection.close()

    writer_errors = []

    def write_once():
        try:
            time.sleep(0.1)
            writer = sqlite3.connect(database)
            writer.execute("INSERT INTO batch DEFAULT VALUES")
            writer.commit()
            writer.close()
        except Exception as error:  # pragma: no cover - test diagnostic boundary
            writer_errors.append(error)

    writer = threading.Thread(target=write_once)
    writer.start()
    report = run_probe(
        argparse.Namespace(
            database=str(database),
            progress_table="batch",
            duration_seconds=0.5,
            query_interval_seconds=0.02,
            query_timeout_seconds=1.0,
        )
    )
    writer.join(timeout=2)

    assert not writer_errors
    assert report["success"] is True
    assert report["metrics"]["rowsAddedByExternalWriter"] == 1
    assert report["acceptance"]["readOnlyWriteBlocked"] is True
    check = sqlite3.connect(database)
    try:
        assert check.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE name='dbgpt_forbidden_write'"
        ).fetchone()[0] == 0
    finally:
        check.close()


def test_live_probe_rejects_unsafe_table_identifier(tmp_path):
    database = tmp_path / "live.db"
    sqlite3.connect(database).close()

    with pytest.raises(ValueError, match="simple SQLite identifier"):
        run_probe(
            argparse.Namespace(
                database=str(database),
                progress_table="batch; DELETE FROM batch",
                duration_seconds=0.1,
                query_interval_seconds=0.1,
                query_timeout_seconds=1.0,
            )
        )
