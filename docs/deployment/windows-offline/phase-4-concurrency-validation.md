# Windows 离线产线化：阶段 4 SQLite 并发验证

## 本阶段结果边界

仓库新增一个安全的合成并发探针：它始终创建一次性数据库，用Python标准库 `sqlite3` 写线程模拟外部C++事务，并使用项目的显式只读连接执行并发查询。探针不会接受现有数据库路径，避免误写生产数据。

本机短测只验证工具、只读连接、锁处理和指标采集链路。它不能替代目标电脑上使用真实10 GB数据库与真实C++进程进行的24/72小时联合验收。

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

先用合成10 GB数据库进行24小时测试：

```powershell
.venv\Scripts\python.exe scripts\windows\sqlite_concurrency_probe.py `
  --work-dir D:\DBGPTValidation `
  --database-size-mb 10240 `
  --duration-seconds 86400 `
  --write-interval-seconds 30 `
  --readers 1 `
  --query-timeout-seconds 30
```

然后启动真实C++软件和DB-GPT，使用实际生产数据库做只读联合测试。真实测试不得由探针写入生产库，需要分别采集C++写入日志、DB-GPT查询日志、数据库和WAL大小、CPU、内存、磁盘队列及错误记录。

正式验收要求：

- C++写入零失败，数据库完整性正常。
- DB-GPT只读查询不能修改、删除或替换数据库。
- 查询超时可实际取消，取消后后续查询恢复正常。
- 没有不可恢复的锁等待，WAL不持续无界增长。
- 对比无DB-GPT负载基线，C++写入延迟增量处于产线确认范围。
- 先通过24小时测试，投产前建议再通过72小时稳定性测试。

## 自动化测试

```powershell
.venv\Scripts\python.exe -m pytest tests\deployment\test_sqlite_concurrency_probe.py -q
.venv\Scripts\ruff.exe check scripts\windows\sqlite_concurrency_probe.py tests\deployment\test_sqlite_concurrency_probe.py
```
