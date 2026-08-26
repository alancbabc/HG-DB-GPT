# Windows 离线产线化：阶段 3 查询保护

## 实现范围

本阶段只收敛数据分析助手使用的 `sql_query` 工具，不改变通用连接器的默认读写语义：

- 使用 `sqlparse` 验证仅有一条 SELECT 或只读 CTE。
- 拒绝多语句、DML、DDL、PRAGMA、ATTACH、DETACH、`SELECT INTO` 和扩展加载。
- SQL 工具改用 `query_ex()`，不再调用可路由到写入分支的 `run()`。
- 驱动层最多读取默认 51 行，只展示前 50 行，不再先 `fetchall()` 全部结果。
- Spark 的独立 `query_ex()` 实现同步接受通用行数参数，避免影响原有可选数据源。
- 默认输出限制为 20,000 字符。
- SQLite 默认执行超时为 30 秒，并通过 SQLite progress handler 实际中断查询。
- SQL 工具进程内默认只允许 1 个查询执行，等待 5 秒仍繁忙则快速失败。

可通过环境变量调整：

| 变量 | 默认值 |
| --- | --- |
| `DBGPT_SQL_QUERY_MAX_ROWS` | `50` |
| `DBGPT_SQL_QUERY_MAX_OUTPUT_CHARS` | `20000` |
| `DBGPT_SQL_QUERY_TIMEOUT_SECONDS` | `30` |
| `DBGPT_SQL_QUERY_MAX_CONCURRENCY` | `1` |
| `DBGPT_SQL_QUERY_ACQUIRE_TIMEOUT_SECONDS` | `5` |

环境变量只在进程启动时读取。产线调整后需要重启 DB-GPT 服务。

## 边界

- SQL解析是工具层纵深保护，不替代阶段2的SQLite `mode=ro`、`query_only` 和Windows ACL。
- 字符限制约束返回给模型的内容；单个数据库字段仍由驱动读取到进程内存。目标10 GB数据库仍需在阶段4用真实大字段和复杂查询验证。
- 当前并发限制是单个DB-GPT进程内的工具级限制。多进程部署需要外部统一并发控制，第一版Windows服务应保持单进程。

## 功能验收

```powershell
.venv\Scripts\python.exe -m pytest packages\dbgpt-app\src\dbgpt_app\openapi\api_v1\tools\tests\test_sql_query.py packages\dbgpt-ext\src\dbgpt_ext\datasource\rdbms\tests\test_conn_sqlite.py -q
.venv\Scripts\ruff.exe check packages\dbgpt-app\src\dbgpt_app\openapi\api_v1\tools\sql_query.py packages\dbgpt-app\src\dbgpt_app\openapi\api_v1\tools\tests\test_sql_query.py packages\dbgpt-ext\src\dbgpt_ext\datasource\rdbms\tests\test_conn_sqlite.py
```

通过标准：

- 正常 SELECT 和只读 CTE 可执行。
- 多语句和状态变更形式在调用连接器前被拒绝。
- 查询只从驱动读取规定数量的行，并明确提示截断。
- SQLite长查询超时后被实际中断，同一连接随后仍可查询。
- 阶段2的默认可写和显式只读连接测试继续通过。
