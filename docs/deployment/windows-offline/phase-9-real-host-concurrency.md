# Windows 离线产线化：阶段 9 真实宿主并发短测

## 测试边界

- 写入端：`universal_agent/build/verification-release/vi_agent_demo.exe`。
- 场景：五粮液瓶盖，使用宿主的“开始模拟写入”。
- 数据库：`universal_agent/database/runtime_vi_agent.db`，不复制。
- 读取端：DB-GPT `SQLiteConnector`，显式 `read_only=True`。
- 不启动或调用LLM、Embedding及Agent。
- 用户已取消“测试数据库必须达到10 GB”的验收条件，报告记录实际数据库大小。

探针 `scripts/windows/sqlite_live_read_probe.py` 不包含写入实现。数据库写入只来自C++模拟宿主；探针使用SQLite URI `mode=ro`，每个连接启用 `PRAGMA query_only=ON`。

## 2026-08-26 开发机短测结果

| 指标 | 结果 |
| --- | --- |
| 持续时间 | 120秒 |
| 数据库大小 | 40,329,216字节（探测开始时） |
| journal mode | WAL |
| 进度表 | `batch` |
| 开始/结束行数 | 10,684 / 10,688 |
| C++宿主新增批次 | 4 |
| DB-GPT只读查询 | 120次 |
| 查询错误 | 0 |
| 查询延迟中位数 | 0.382毫秒 |
| 查询延迟P95 | 0.783毫秒 |
| 查询延迟最大值 | 1.176毫秒 |
| WAL峰值 | 630,392字节 |
| `PRAGMA quick_check` | `ok` |
| 尝试建表 | 被只读数据库拒绝 |

短测的五项自动判据全部通过：宿主写入取得进展、读取取得进展、无读取错误、数据库完整性正常、只读连接拒绝写入。

## 已发现问题

模拟宿主停止后，写端关闭数据库并移除 `runtime_vi_agent.db-wal` 和 `runtime_vi_agent.db-shm`。在数据库目录只有读取权限的条件下，此时重新创建SQLite `mode=ro` 连接会返回 `unable to open database file`。写端运行且WAL侧文件存在时，DB-GPT只读连接和查询正常。

这说明当前方案已经验证“写端运行期间的真实并发读取”，但尚未验证“写端未运行或先于读端停止时仍可重新连接”。投产前必须确定并测试以下方案之一：

1. 写入宿主先启动并打开数据库，之后再启动DB-GPT；写入宿主不可用时DB-GPT快速失败并明确提示；
2. 设计只允许SQLite管理WAL/SHM侧文件、但仍禁止修改、删除、重命名或替换主数据库的Windows ACL。

本项目不得通过 `immutable=1` 读取仍会变化的数据库，不得由DB-GPT改变journal mode。未经确认，不增加对C++ API的依赖。

## 后续验收

- 在目标电脑执行24小时联合测试，投产前建议执行72小时测试。
- 增加写入宿主先启动、后启动、运行中退出和重启场景。
- 记录宿主写入错误、DB-GPT查询错误、WAL大小、CPU、内存、磁盘队列和查询延迟。
- 对实际Windows服务账户和ACL重复全部场景。

## 命令

```powershell
.venv\Scripts\python.exe scripts\windows\sqlite_live_read_probe.py `
  --database "..\universal_agent\database\runtime_vi_agent.db" `
  --progress-table batch `
  --duration-seconds 120 `
  --query-interval-seconds 1 `
  --query-timeout-seconds 5

.venv\Scripts\python.exe -m pytest tests\deployment\test_sqlite_live_read_probe.py -q
```
