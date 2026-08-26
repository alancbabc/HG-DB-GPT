# Windows 离线产线化：阶段 4 SQLite 并发验证

## 本阶段结果边界

仓库新增一个安全的合成并发探针：它始终创建一次性数据库，用Python标准库 `sqlite3` 写线程模拟外部C++事务，并使用项目的显式只读连接执行并发查询。探针不会接受现有数据库路径，避免误写生产数据。

本机短测只验证工具、只读连接、锁处理和指标采集链路。最终联合验收使用 `universal_agent` 的模拟宿主程序持续写入五粮液数据库，DB-GPT 对同一文件执行显式只读查询。数据库不再要求必须达到10 GB，报告必须记录实际大小。

## 本机短时验收

```powershell
.venv\Scripts\python.exe scripts\windows\sqlite_concurrency_probe.py `
  --database-size-mb 8 `
  --duration-seconds 5 `
  --write-interval-seconds 0.1 `
  --readers 2
```

报告必须满足：写入和读取均取得进展、无读写错误、`PRAGMA quick_check`正常、只读连接写入被拒绝。报告还记录数据库大小、WAL峰值、写入延迟中位数和P95。

## 目标环境联合验收

合成数据库探针继续作为快速回归工具，但不是最终的真实宿主验收依据。真实宿主短测命令如下：

```powershell
.venv\Scripts\python.exe scripts\windows\sqlite_live_read_probe.py `
  --database "..\universal_agent\database\runtime_vi_agent.db" `
  --progress-table batch `
  --duration-seconds 120 `
  --query-interval-seconds 1 `
  --query-timeout-seconds 5
```

运行探针前，在 `universal_agent` 模拟宿主选择“五粮液瓶盖”并点击“开始模拟写入”。探针只使用 DB-GPT 的 `mode=ro` 和 `query_only=ON` 连接，不写数据库；写入完全来自 C++ 模拟宿主。报告记录 `batch` 增量、查询延迟、查询错误、数据库完整性、只读拒写和WAL峰值。

短测通过后，在目标电脑使用相同组合执行一小时联合测试，并分别采集模拟宿主日志、DB-GPT查询报告、数据库和WAL大小、CPU、内存、磁盘队列及错误记录。用户已确认不再设置24/72小时验收门槛。

正式验收要求：

- C++写入零失败，数据库完整性正常。
- DB-GPT只读查询不能修改、删除或替换数据库。
- 查询超时可实际取消，取消后后续查询恢复正常。
- 没有不可恢复的锁等待，WAL不持续无界增长。
- 对比无DB-GPT负载基线，C++写入延迟增量处于产线确认范围。
- 通过一小时真实宿主联合测试。

## 自动化测试

```powershell
.venv\Scripts\python.exe -m pytest tests\deployment\test_sqlite_concurrency_probe.py -q
.venv\Scripts\python.exe -m pytest tests\deployment\test_sqlite_live_read_probe.py -q
.venv\Scripts\ruff.exe check scripts\windows\sqlite_concurrency_probe.py scripts\windows\sqlite_live_read_probe.py tests\deployment\test_sqlite_concurrency_probe.py tests\deployment\test_sqlite_live_read_probe.py
```
