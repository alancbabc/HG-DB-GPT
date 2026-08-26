"""Observe an externally written SQLite database through DB-GPT read-only access.

This tool never opens the database in writable mode. An external host program must
perform the writes while the probe records query progress, latency, WAL size, and
database integrity.
"""

import argparse
import json
import platform
import re
import sqlite3
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy.exc import OperationalError

from dbgpt_ext.datasource.rdbms.conn_sqlite import SQLiteConnector

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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


def _read_count(
    connector: SQLiteConnector, table: str, timeout: float
) -> int:
    _, rows = connector.query_ex(
        f'SELECT COUNT(*) FROM "{table}"', timeout=timeout, max_rows=1
    )
    if len(rows) != 1 or len(rows[0]) != 1:
        raise RuntimeError("count query returned an unexpected result")
    return int(rows[0][0])


def run_probe(args: argparse.Namespace) -> Dict[str, Any]:
    database_path = Path(args.database).expanduser().resolve()
    if not database_path.is_file():
        raise ValueError(f"Database does not exist or is not a file: {database_path}")
    if not _IDENTIFIER.fullmatch(args.progress_table):
        raise ValueError("--progress-table must be a simple SQLite identifier")

    connector = SQLiteConnector.from_file_path(
        str(database_path), read_only=True
    )
    query_latencies: List[float] = []
    query_errors: List[str] = []
    wal_path = Path(f"{database_path}-wal")
    peak_wal_bytes = wal_path.stat().st_size if wal_path.exists() else 0
    query_count = 0
    started_at = time.time()
    try:
        start_count = _read_count(
            connector, args.progress_table, args.query_timeout_seconds
        )
        end_count = start_count
        deadline = time.monotonic() + args.duration_seconds
        while time.monotonic() < deadline:
            query_started = time.perf_counter()
            try:
                end_count = _read_count(
                    connector,
                    args.progress_table,
                    args.query_timeout_seconds,
                )
                query_latencies.append(
                    (time.perf_counter() - query_started) * 1000
                )
                query_count += 1
            except Exception as error:  # pragma: no cover - diagnostic boundary
                query_errors.append(f"{type(error).__name__}: {error}")
            if wal_path.exists():
                peak_wal_bytes = max(peak_wal_bytes, wal_path.stat().st_size)
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(args.query_interval_seconds, remaining))

        read_only_write_blocked = False
        try:
            connector.run("CREATE TABLE dbgpt_forbidden_write(id INTEGER)")
        except OperationalError:
            read_only_write_blocked = True

        _, quick_check_rows = connector.query_ex(
            "PRAGMA quick_check", timeout=args.query_timeout_seconds, max_rows=1
        )
        quick_check = str(quick_check_rows[0][0]) if quick_check_rows else ""
        _, journal_rows = connector.query_ex(
            "PRAGMA journal_mode", timeout=args.query_timeout_seconds, max_rows=1
        )
        journal_mode = str(journal_rows[0][0]) if journal_rows else ""
    finally:
        connector.close()

    acceptance = {
        "externalWriterMadeProgress": end_count > start_count,
        "readerMadeProgress": query_count > 0,
        "noReaderErrors": not query_errors,
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
        "database": {
            "path": str(database_path),
            "bytes": database_path.stat().st_size,
            "journalMode": journal_mode,
            "progressTable": args.progress_table,
        },
        "workload": {
            "startedAtUnixSeconds": started_at,
            "durationSeconds": args.duration_seconds,
            "queryIntervalSeconds": args.query_interval_seconds,
            "queryTimeoutSeconds": args.query_timeout_seconds,
        },
        "metrics": {
            "startRows": start_count,
            "endRows": end_count,
            "rowsAddedByExternalWriter": end_count - start_count,
            "queries": query_count,
            "queryLatencyMsMedian": round(statistics.median(query_latencies), 3)
            if query_latencies
            else 0.0,
            "queryLatencyMsP95": round(_percentile(query_latencies, 0.95), 3),
            "queryLatencyMsMax": round(max(query_latencies), 3)
            if query_latencies
            else 0.0,
            "peakWalBytes": peak_wal_bytes,
        },
        "errors": query_errors[:20],
        "acceptance": acceptance,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--progress-table", default="batch")
    parser.add_argument("--duration-seconds", type=_positive, default=120.0)
    parser.add_argument("--query-interval-seconds", type=_positive, default=1.0)
    parser.add_argument("--query-timeout-seconds", type=_positive, default=5.0)
    return parser.parse_args()


def main() -> int:
    try:
        report = run_probe(_parse_args())
    except ValueError as error:
        report = {"success": False, "errors": [str(error)]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
