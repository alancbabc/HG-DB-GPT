import json
from unittest.mock import Mock

import pytest

from dbgpt_app.openapi.api_v1.tools.sql_query import (
    MAX_SQL_ROWS,
    _validate_read_only_sql,
    make_sql_query,
)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM production_data",
        "WITH recent AS (SELECT * FROM production_data) SELECT * FROM recent",
        "-- comment\nSELECT 1;",
    ],
)
def test_validate_read_only_sql_accepts_select_and_cte(sql):
    assert _validate_read_only_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "PRAGMA query_only",
        "ATTACH DATABASE 'other.db' AS other",
        "SELECT 1; DELETE FROM production_data",
        "WITH changed AS (DELETE FROM production_data RETURNING *) "
        "SELECT * FROM changed",
        "UPDATE production_data SET value = 1",
        "SELECT load_extension('extension.dll')",
        "SELECT value INTO copied_data FROM production_data",
    ],
)
def test_validate_read_only_sql_rejects_state_changing_forms(sql):
    with pytest.raises(ValueError):
        _validate_read_only_sql(sql)


def test_sql_query_uses_bounded_query_api_and_reports_truncation():
    connector = Mock()
    connector.query_ex.return_value = (
        ["id"],
        [(value,) for value in range(MAX_SQL_ROWS + 1)],
    )
    sql_query = make_sql_query({}, connector)

    payload = json.loads(sql_query("SELECT id FROM production_data"))

    connector.query_ex.assert_called_once_with(
        "SELECT id FROM production_data", timeout=30, max_rows=MAX_SQL_ROWS + 1
    )
    content = payload["chunks"][0]["content"]
    assert f"前 {MAX_SQL_ROWS} 行" in content
    assert f"| {MAX_SQL_ROWS - 1} |" in content
    assert f"| {MAX_SQL_ROWS} |" not in content


def test_sql_query_does_not_call_connector_for_rejected_sql():
    connector = Mock()
    sql_query = make_sql_query({}, connector)

    payload = json.loads(sql_query("SELECT 1; DROP TABLE production_data"))

    connector.query_ex.assert_not_called()
    assert "安全限制" in payload["chunks"][0]["content"]


def test_sql_query_reports_timeout_without_leaking_exception():
    connector = Mock()
    connector.query_ex.side_effect = TimeoutError("driver details")
    sql_query = make_sql_query({}, connector)

    payload = json.loads(sql_query("SELECT * FROM production_data"))

    assert "查询已取消" in payload["chunks"][0]["content"]
