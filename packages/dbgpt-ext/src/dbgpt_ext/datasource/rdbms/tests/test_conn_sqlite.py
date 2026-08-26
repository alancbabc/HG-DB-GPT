"""
Run unit test with command: pytest dbgpt/datasource/rdbms/tests/test_conn_sqlite.py
"""

import os
import sqlite3
import tempfile
from unittest.mock import patch

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

from dbgpt_ext.datasource.rdbms.conn_sqlite import (
    SQLiteConnector,
    SQLiteConnectorParameters,
    SQLiteReadOnlyUnavailableError,
)


@pytest.fixture
def db():
    temp_db_file = tempfile.NamedTemporaryFile(delete=False)
    temp_db_file.close()
    conn = SQLiteConnector.from_file_path(temp_db_file.name)
    try:
        yield conn
    finally:
        conn.close()
        os.unlink(temp_db_file.name)


def test_get_table_names(db):
    assert list(db.get_table_names()) == []


def test_get_table_info(db):
    assert db.get_table_info() == ""


def test_get_table_info_with_table(db):
    db.run("CREATE TABLE test (id INTEGER);")
    print(db._sync_tables_from_db())
    table_info = db.get_table_info()
    assert "CREATE TABLE test" in table_info


def test_run_sql(db):
    result = db.run("CREATE TABLE test(id INTEGER);")
    assert result[0] == ("id", "INTEGER", 0, None, 0)


def test_run_no_throw(db):
    assert db.run_no_throw("this is a error sql") == []


def test_get_indexes(db):
    db.run("CREATE TABLE test (name TEXT);")
    db.run("CREATE INDEX idx_name ON test(name);")
    indexes = db.get_indexes("test")
    assert indexes == [{"name": "idx_name", "column_names": ["name"]}]


def test_get_indexes_empty(db):
    db.run("CREATE TABLE test (id INTEGER PRIMARY KEY);")
    assert db.get_indexes("test") == []


def test_get_show_create_table(db):
    db.run("CREATE TABLE test (id INTEGER PRIMARY KEY);")
    assert (
        db.get_show_create_table("test") == "CREATE TABLE test (id INTEGER PRIMARY KEY)"
    )


def test_get_fields(db):
    db.run("CREATE TABLE test (id INTEGER PRIMARY KEY);")
    assert db.get_fields("test") == [("id", "INTEGER", 0, None, 1)]


def test_get_charset(db):
    assert db.get_charset() == "UTF-8"


def test_get_collation(db):
    assert db.get_collation() == "UTF-8"


def test_table_simple_info(db):
    db.run("CREATE TABLE test (id INTEGER PRIMARY KEY);")
    assert db.table_simple_info() == ["test(id);"]


def test_get_table_info_no_throw(db):
    db.run("CREATE TABLE test (id INTEGER PRIMARY KEY);")
    assert db.get_table_info_no_throw("xxxx_table").startswith("Error:")


def test_query_ex(db):
    db.run("CREATE TABLE test (id INTEGER PRIMARY KEY);")
    db.run("insert into test(id) values (1)")
    db.run("insert into test(id) values (2)")
    field_names, result = db.query_ex("select * from test")
    assert field_names == ["id"]
    assert result == [(1,), (2,)]

    field_names, result = db.query_ex("select * from test", fetch="one")
    assert field_names == ["id"]
    assert result == [(1,)]


def test_convert_sql_write_to_select(db):
    # TODO
    pass


def test_get_grants(db):
    assert db.get_grants() == []


def test_get_users(db):
    assert db.get_users() == []


def test_get_table_comments(db):
    assert db.get_table_comments() == []
    db.run("CREATE TABLE test (id INTEGER PRIMARY KEY);")
    assert db.get_table_comments() == [
        ("test", "CREATE TABLE test (id INTEGER PRIMARY KEY)")
    ]


def test_get_database_names(db):
    db.get_database_names() == []


def test_db_dir_exist_dir():
    with tempfile.TemporaryDirectory() as temp_dir:
        new_dir = os.path.join(temp_dir, "new_dir")
        file_path = os.path.join(new_dir, "sqlite.db")
        db = SQLiteConnector.from_file_path(file_path)
        try:
            assert os.path.exists(new_dir) is True
            assert list(db.get_table_names()) == []
        finally:
            db.close()
    with tempfile.TemporaryDirectory() as existing_dir:
        file_path = os.path.join(existing_dir, "sqlite.db")
        db = SQLiteConnector.from_file_path(file_path)
        try:
            assert os.path.exists(existing_dir) is True
            assert list(db.get_table_names()) == []
        finally:
            db.close()


def test_read_only_connector_can_query_but_cannot_write(tmp_path):
    file_path = tmp_path / "production.db"
    writable = SQLiteConnector.from_file_path(str(file_path))
    try:
        writable.run("CREATE TABLE production_data (id INTEGER PRIMARY KEY);")
        writable.run("INSERT INTO production_data(id) VALUES (1)")
    finally:
        writable.close()

    read_only = SQLiteConnector.from_file_path(str(file_path), read_only=True)
    try:
        assert isinstance(read_only._engine.pool, NullPool)
        fields, rows = read_only.query_ex("SELECT id FROM production_data")
        assert fields == ["id"]
        assert rows == [(1,)]
        assert read_only.query_ex("PRAGMA query_only", fetch="one")[1] == [(1,)]
        with pytest.raises(OperationalError, match="readonly"):
            read_only.run("INSERT INTO production_data(id) VALUES (2)")
    finally:
        read_only.close()


def test_read_only_connector_reports_host_unavailable_and_recovers(tmp_path):
    file_path = tmp_path / "production.db"
    writable = SQLiteConnector.from_file_path(str(file_path))
    try:
        writable.run("CREATE TABLE production_data (id INTEGER PRIMARY KEY);")
        writable.run("INSERT INTO production_data(id) VALUES (1)")
    finally:
        writable.close()

    read_only = SQLiteConnector.from_file_path(str(file_path), read_only=True)
    original_connect = read_only._engine.dialect.dbapi.connect
    attempts = 0

    def fail_once(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise sqlite3.OperationalError("unable to open database file")
        return original_connect(*args, **kwargs)

    try:
        with patch.object(read_only._engine.dialect.dbapi, "connect", fail_once):
            with pytest.raises(
                SQLiteReadOnlyUnavailableError, match="SQLITE_HOST_NOT_READY"
            ) as exc_info:
                read_only.query_ex("SELECT id FROM production_data")

            assert "请先启动写入宿主" in str(exc_info.value)
            assert str(file_path.resolve()) in str(exc_info.value)
            assert read_only.query_ex("SELECT id FROM production_data")[1] == [(1,)]
    finally:
        read_only.close()


def test_writable_connector_does_not_translate_open_failure(tmp_path):
    file_path = tmp_path / "development.db"
    writable = SQLiteConnector.from_file_path(str(file_path))
    writable._engine.dispose()

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("unable to open database file")

    try:
        with patch.object(writable._engine.dialect.dbapi, "connect", fail):
            with pytest.raises(OperationalError, match="unable to open database file"):
                writable.query_ex("SELECT 1")
    finally:
        writable.close()


def test_read_only_connector_does_not_create_missing_path(tmp_path):
    file_path = tmp_path / "missing" / "production.db"

    with pytest.raises(FileNotFoundError, match="does not exist or is not a file"):
        SQLiteConnector.from_file_path(str(file_path), read_only=True)

    assert not file_path.exists()
    assert not file_path.parent.exists()


def test_read_only_parameter_round_trip_and_default_compatibility(tmp_path):
    file_path = tmp_path / "production.db"
    writable_params = SQLiteConnectorParameters(path=str(file_path))
    assert writable_params.read_only is False

    writable = writable_params.create_connector()
    try:
        writable.run("CREATE TABLE production_data (id INTEGER PRIMARY KEY);")
    finally:
        writable.close()

    params = SQLiteConnectorParameters(path=str(file_path), read_only=True)
    restored = SQLiteConnectorParameters.from_persisted_state(params.persisted_state())
    assert restored.read_only is True

    read_only = restored.create_connector()
    try:
        with pytest.raises(OperationalError, match="readonly"):
            read_only.run("DROP TABLE production_data")
    finally:
        read_only.close()


def test_query_ex_limits_rows_before_fetching_all(db):
    db.run("CREATE TABLE test (id INTEGER PRIMARY KEY);")
    for value in range(10):
        db.run(f"INSERT INTO test(id) VALUES ({value})")

    fields, rows = db.query_ex("SELECT id FROM test ORDER BY id", max_rows=3)

    assert fields == ["id"]
    assert rows == [(0,), (1,), (2,)]


def test_sqlite_query_timeout_interrupts_execution(db):
    expensive_query = """
        WITH RECURSIVE counter(value) AS (
            SELECT 1
            UNION ALL
            SELECT value + 1 FROM counter WHERE value < 100000000
        )
        SELECT sum(value) FROM counter
    """

    with pytest.raises(TimeoutError, match="exceeded timeout"):
        db.query_ex(expensive_query, timeout=0.001)

    assert db.query_ex("SELECT 1", timeout=1, fetch="one")[1] == [(1,)]
