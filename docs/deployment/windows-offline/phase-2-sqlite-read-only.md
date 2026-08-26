# Windows 离线产线化：阶段 2 SQLite 真实只读连接

## 实现范围

本阶段为 SQLite 数据源增加显式的 `read_only` 参数，默认值为 `false`。默认模式继续保留通用平台原有的建库、建表和写入能力；只有明确启用只读的生产数据源才应用以下约束：

- 连接前验证路径已存在且为文件；不创建目录、空数据库或替代文件。
- 使用 SQLite URI `mode=ro` 从底层只读打开数据库。
- SQLAlchemy 连接池中的每个 DB-API 连接执行 `PRAGMA query_only=ON`。
- 数据源保存到元数据库后，连接管理器从 `ext_config.read_only` 恢复该设置。
- 非布尔值和损坏的 SQLite `ext_config` 会明确失败，不静默降级为可写连接。

本阶段不修改 SQL 工具的语句校验、查询行数、超时或并发策略，这些属于阶段 3。

## 使用方式

通过当前动态数据源接口或页面创建 SQLite 数据源时，参数结构为：

```json
{
  "type": "sqlite",
  "params": {
    "path": "D:\\ProductionData\\production.db",
    "check_same_thread": false,
    "read_only": true
  },
  "description": "生产数据库只读连接"
}
```

页面的数据源表单由连接器参数元数据动态生成，因此不需要增加专用页面或修改主架构。

## 安全边界

`mode=ro` 和 `query_only` 保护通过本连接器建立的连接。生产部署仍必须使用独立低权限 Windows 服务账户，并通过 NTFS ACL 防止 Shell、Python 或其他进程重新以可写方式打开、删除或替换生产数据库。

DB-GPT 不设置 `journal_mode`、不执行 checkpoint，也不使用 `immutable=1`。WAL 数据库对主文件、`-wal`、`-shm` 和目录权限的具体要求必须在目标环境实测。

## 功能验收

```powershell
.venv\Scripts\python.exe -m pytest packages\dbgpt-ext\src\dbgpt_ext\datasource\rdbms\tests\test_conn_sqlite.py -q
.venv\Scripts\python.exe -m pytest packages\dbgpt-serve\src\dbgpt_serve\datasource\tests\test_connector_manager_sqlite.py -q
.venv\Scripts\ruff.exe check packages\dbgpt-ext\src\dbgpt_ext\datasource\rdbms\conn_sqlite.py packages\dbgpt-ext\src\dbgpt_ext\datasource\rdbms\tests\test_conn_sqlite.py packages\dbgpt-serve\src\dbgpt_serve\datasource\tests\test_connector_manager_sqlite.py
```

通过标准：

- 默认连接仍可创建数据库、表和数据，保持向后兼容。
- 只读连接可以反射表结构并执行查询。
- 只读连接的写入和DDL操作由SQLite底层拒绝。
- 只读连接不会创建缺失的文件或父目录。
- `read_only` 经过数据源持久化结构往返后仍为 `true`。
- 所有连接在测试结束后释放，Windows临时文件可正常清理。
