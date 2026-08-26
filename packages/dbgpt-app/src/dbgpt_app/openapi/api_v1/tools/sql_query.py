"""sql_query tool — read-only SQL query against the selected database."""

import json
import os
import threading
from typing import Any, Dict, Optional

import sqlparse
from sqlparse import tokens as T

from dbgpt.agent.resource.tool.base import tool


def _positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


MAX_SQL_ROWS = _positive_int_env("DBGPT_SQL_QUERY_MAX_ROWS", 50)
MAX_SQL_OUTPUT_CHARS = _positive_int_env("DBGPT_SQL_QUERY_MAX_OUTPUT_CHARS", 20_000)
SQL_QUERY_TIMEOUT_SECONDS = _positive_int_env("DBGPT_SQL_QUERY_TIMEOUT_SECONDS", 30)
SQL_QUERY_ACQUIRE_TIMEOUT_SECONDS = _positive_int_env(
    "DBGPT_SQL_QUERY_ACQUIRE_TIMEOUT_SECONDS", 5
)
SQL_QUERY_CONCURRENCY = _positive_int_env("DBGPT_SQL_QUERY_MAX_CONCURRENCY", 1)
_SQL_QUERY_SEMAPHORE = threading.BoundedSemaphore(SQL_QUERY_CONCURRENCY)

_FORBIDDEN_TOKENS = {
    "ALTER",
    "ANALYZE",
    "ATTACH",
    "CALL",
    "CREATE",
    "DELETE",
    "DETACH",
    "DROP",
    "EXEC",
    "EXECUTE",
    "GRANT",
    "INSERT",
    "INTO",
    "LOAD_EXTENSION",
    "MERGE",
    "PRAGMA",
    "REINDEX",
    "REPLACE",
    "REVOKE",
    "TRUNCATE",
    "UPDATE",
    "VACUUM",
}


def _validate_read_only_sql(sql: str) -> str:
    """Return one normalized SELECT/CTE statement or raise ValueError."""
    statement_text = sql.strip()
    if not statement_text:
        raise ValueError("SQL不能为空。")
    statements = [
        statement
        for statement in sqlparse.parse(statement_text)
        if str(statement).strip().strip(";").strip()
    ]
    if len(statements) != 1:
        raise ValueError("仅允许执行一条SQL语句。")

    statement = statements[0]
    if statement.get_type() != "SELECT":
        raise ValueError("仅允许执行SELECT或只读CTE查询。")

    for token in statement.flatten():
        if token.ttype in T.Whitespace or token.ttype in T.Comment:
            continue
        normalized = token.normalized.upper()
        if token.ttype in T.DML and normalized != "SELECT":
            raise ValueError(f"不允许在查询中使用{normalized}。")
        if normalized in _FORBIDDEN_TOKENS:
            raise ValueError(f"不允许在查询中使用{normalized}。")
    return statement_text.rstrip(";").strip()


def _response(output_type: str, content: str) -> str:
    return json.dumps(
        {"chunks": [{"output_type": output_type, "content": content}]},
        ensure_ascii=False,
    )


def make_sql_query(react_state: Dict[str, Any], database_connector: Optional[Any]):
    @tool(
        description=(
            "对用户选择的数据库执行 SQL 查询（仅支持 SELECT）。"
            '参数: {"sql": "SELECT 语句"}'
        )
    )
    def sql_query(sql: str) -> str:
        """Execute a read-only SQL query against the selected database."""
        if database_connector is None:
            return _response(
                "text", "未选择数据库，请先在左侧面板选择一个数据源。"
            )

        try:
            sql_stripped = _validate_read_only_sql(sql)
        except ValueError as err:
            return _response("text", f"安全限制: {err}")

        if not _SQL_QUERY_SEMAPHORE.acquire(
            timeout=SQL_QUERY_ACQUIRE_TIMEOUT_SECONDS
        ):
            return _response("text", "数据库查询繁忙，请稍后重试。")

        try:
            columns, rows = database_connector.query_ex(
                sql_stripped,
                timeout=SQL_QUERY_TIMEOUT_SECONDS,
                max_rows=MAX_SQL_ROWS + 1,
            )
            if not rows:
                return _response("text", "查询返回空结果。")

            col_names = [str(column) for column in columns]
            truncated_rows = len(rows) > MAX_SQL_ROWS
            rows = rows[:MAX_SQL_ROWS]

            header = "| " + " | ".join(col_names) + " |"
            separator = "| " + " | ".join(["---"] * len(col_names)) + " |"
            md_rows = []
            for row in rows:
                md_rows.append("| " + " | ".join(str(v) for v in row) + " |")
            table = "\n".join([header, separator] + md_rows)
            if truncated_rows:
                table += f"\n\n（结果超过限制，仅显示前 {MAX_SQL_ROWS} 行）"

            # Cap total output size so a single wide query can't blow out the
            # LLM context window. The full result remains available via the
            # ToolResultStorage persistence layer if it exceeds the threshold.
            if len(table) > MAX_SQL_OUTPUT_CHARS:
                table = (
                    table[:MAX_SQL_OUTPUT_CHARS]
                    + f"\n\n... [Output truncated at {MAX_SQL_OUTPUT_CHARS} chars. "
                    f"Displayed rows: {len(rows)}]"
                )

            return _response("markdown", table)
        except TimeoutError:
            return _response(
                "text", f"SQL执行超时（{SQL_QUERY_TIMEOUT_SECONDS}秒），查询已取消。"
            )
        except Exception as e:
            return _response("text", f"SQL执行失败: {str(e)}")
        finally:
            _SQL_QUERY_SEMAPHORE.release()

    return sql_query
