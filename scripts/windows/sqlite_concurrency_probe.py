"""Synthetic SQLite writer/read-only DB-GPT concurrency probe.

This tool creates a disposable database. It never opens a user-supplied database and
therefore cannot accidentally modify production data.
"""

import argparse
import json
import platform
import sqlite3
import statistics
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy.exc import OperationalError

from dbgpt_ext.datasource.rdbms.conn_sqlite import SQLiteConnector


def _positive(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return parsed


def _percentile(values: List[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int((len(ordered) - 1) * percentile))
    return ordered[index]


def _initialize_database(path: Path, size_mb: int, journal_mode: str) -> str:
    connection = sqlite3.connect(path)
    try:
        actual_mode = connection.execute(
            f"PRAGMA journal_mode={journal_mode}"
        ).fetchone()[0]
        connection.execute(
            "CREATE TABLE measurements ("
            "id INTEGER PRIMARY KEY, created_at REAL NOT NULL, payload BLOB NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE writer_events ("
            "id INTEGER PRIMARY KEY, created_at REAL NOT NULL, value INTEGER NOT NULL)"
        )
        chunk_bytes = 1024 * 1024
        for _ in range(size_mb):
            connection.execute(
                "INSERT INTO measurements(created_at, payload) "
                "VALUES (?, zeroblob(?))",
                (time.time(), chunk_bytes),
            )
        connection.commit()
        return str(actual_mode)
    finally:
        connection.close()


def _writer(
    path: Path,
    stop: threading.Event,
    interval: float,
    latencies: List[float],
    errors: List[str],
) -> None:
    connection = sqlite3.connect(path, timeout=5)
    try:
        value = 0
        while not stop.is_set():
            started = time.perf_counter()
            try:
                connection.execute(
                    "INSERT INTO writer_events(created_at, value) VALUES (?, ?)",
                    (time.time(), value),
                )
                connection.commit()
                latencies.append((time.perf_counter() - started) * 1000)
                value += 1
            except Exception as err:  # pragma: no cover - diagnostic boundary
                errors.append(f"{type(err).__name__}: {err}")
                connection.rollback()
            stop.wait(interval)
    finally:
        connection.close()


def _reader(
    path: Path,
    stop: threading.Event,
    query_timeout: float,
    counters: Dict[str, int],
    errors: List[str],
    lock: threading.Lock,
) -> None:
    connector = SQLiteConnector.from_file_path(str(path), read_only=True)
    try:
        while not stop.is_set():
            try:
                _, rows = connector.query_ex(
                    "SELECT count(*), max(value) FROM writer_events",
                    timeout=query_timeout,
                    max_rows=2,
                )
                if not rows:
                    raise RuntimeError("reader query returned no row")
                with lock:
                    counters["queries"] += 1
            except Exception as err:  # pragma: no cover - diagnostic boundary
                with lock:
                    errors.append(f"{type(err).__name__}: {err}")
                stop.wait(0.01)
    finally:
        connector.close()


def run_probe(args: argparse.Namespace) -> Dict[str, Any]:
    work_dir_context = None
    if args.work_dir:
        work_dir = Path(args.work_dir).expanduser().resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
    else:
        work_dir_context = tempfile.TemporaryDirectory(prefix="dbgpt-sqlite-probe-")
        work_dir = Path(work_dir_context.name)

    database_path = work_dir / f"probe-{uuid.uuid4().hex}.db"
    writer_latencies: List[float] = []
    writer_errors: List[str] = []
    reader_errors: List[str] = []
    counters = {"queries": 0}
    lock = threading.Lock()
    stop = threading.Event()

    try:
        actual_journal_mode = _initialize_database(
            database_path, args.database_size_mb, args.journal_mode
        )
        writer = threading.Thread(
            target=_writer,
            args=(
                database_path,
                stop,
                args.write_interval_seconds,
                writer_latencies,
                writer_errors,
            ),
            name="sqlite-probe-writer",
        )
        readers = [
            threading.Thread(
                target=_reader,
                args=(
                    database_path,
                    stop,
                    args.query_timeout_seconds,
                    counters,
                    reader_errors,
                    lock,
                ),
                name=f"sqlite-probe-reader-{index}",
            )
            for index in range(args.readers)
        ]
        writer.start()
        for reader in readers:
            reader.start()

        deadline = time.monotonic() + args.duration_seconds
        peak_wal_bytes = 0
        while time.monotonic() < deadline:
            wal_path = Path(f"{database_path}-wal")
            if wal_path.exists():
                peak_wal_bytes = max(peak_wal_bytes, wal_path.stat().st_size)
            time.sleep(min(0.1, max(0.01, args.duration_seconds / 10)))

        stop.set()
        writer.join(timeout=10)
        for reader in readers:
            reader.join(timeout=10)

        read_only_write_blocked = False
        read_only = SQLiteConnector.from_file_path(
            str(database_path), read_only=True
        )
        try:
            try:
                read_only.run("CREATE TABLE forbidden_write(id INTEGER)")
            except OperationalError:
                read_only_write_blocked = True
        finally:
            read_only.close()

        verification = sqlite3.connect(database_path)
        try:
            quick_check = verification.execute("PRAGMA quick_check").fetchone()[0]
            event_count = verification.execute(
                "SELECT count(*) FROM writer_events"
            ).fetchone()[0]
        finally:
            verification.close()

        acceptance = {
            "writerMadeProgress": event_count > 0,
            "readersMadeProgress": counters["queries"] > 0,
            "noWriterErrors": not writer_errors,
            "noReaderErrors": not reader_errors,
            "databaseIntegrityOk": quick_check == "ok",
            "readOnlyWriteBlocked": read_only_write_blocked,
        }
        return {
            "success": all(acceptance.values()),
            "environment": {
                "python": platform.python_version(),
                "sqlite": sqlite3.sqlite_version,
                "operatingSystem": platform.platform(),
            },
            "workload": {
                "databaseSizeTargetMb": args.database_size_mb,
                "durationSeconds": args.duration_seconds,
                "writeIntervalSeconds": args.write_interval_seconds,
                "readers": args.readers,
                "queryTimeoutSeconds": args.query_timeout_seconds,
                "journalMode": actual_journal_mode,
            },
            "metrics": {
                "databaseBytes": database_path.stat().st_size,
                "peakWalBytes": peak_wal_bytes,
                "writes": event_count,
                "queries": counters["queries"],
                "writeLatencyMsMedian": round(
                    statistics.median(writer_latencies), 3
                )
                if writer_latencies
                else 0.0,
                "writeLatencyMsP95": round(
                    _percentile(writer_latencies, 0.95), 3
                ),
            },
            "errors": {
                "writer": writer_errors[:20],
                "reader": reader_errors[:20],
            },
            "acceptance": acceptance,
            "databaseRetainedAt": str(database_path) if args.keep_database else None,
        }
    finally:
        if not args.keep_database:
            for suffix in ("-wal", "-shm", ""):
                candidate = Path(f"{database_path}{suffix}")
                if candidate.exists():
                    candidate.unlink()
        if work_dir_context is not None:
            work_dir_context.cleanup()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir")
    parser.add_argument("--keep-database", action="store_true")
    parser.add_argument("--database-size-mb", type=int, default=8)
    parser.add_argument("--duration-seconds", type=_positive, default=5.0)
    parser.add_argument("--write-interval-seconds", type=_positive, default=0.1)
    parser.add_argument("--readers", type=int, default=1)
    parser.add_argument("--query-timeout-seconds", type=_positive, default=2.0)
    parser.add_argument(
        "--journal-mode", choices=("WAL", "DELETE"), default="WAL"
    )
    args = parser.parse_args()
    if args.database_size_mb <= 0:
        parser.error("--database-size-mb must be greater than zero")
    if args.readers <= 0:
        parser.error("--readers must be greater than zero")
    if args.keep_database and not args.work_dir:
        parser.error("--keep-database requires --work-dir")
    return args


def main() -> int:
    report = run_probe(_parse_args())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
