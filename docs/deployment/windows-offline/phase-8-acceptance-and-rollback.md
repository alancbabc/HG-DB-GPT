# Windows 离线产线化：阶段 8 验收、升级与回滚

## 备份与恢复策略

升级前必须停止 `HGTechDBGPT`，再备份运行数据。备份包括元数据库、向量库、上传文件和生成结果；默认排除可再生成的日志、临时文件和备份目录，避免递归复制。

```powershell
powershell -ExecutionPolicy Bypass -File `
  "C:\Program Files\HGTech\DB-GPT\scripts\Backup-DBGPTData.ps1" `
  -InstallRoot "C:\Program Files\HGTech\DB-GPT" `
  -DataRoot "C:\ProgramData\HGTech\DB-GPT" `
  -BackupRoot "D:\HGTechBackups\before-upgrade-001"
```

备份记录文件路径和大小，并对复制后的DB-GPT SQLite元数据库执行 `PRAGMA quick_check`；不再逐个哈希普通运行文件。恢复始终写入一个不存在的新目录，绝不覆盖、删除或重命名当前数据目录：

```powershell
powershell -ExecutionPolicy Bypass -File `
  "C:\Program Files\HGTech\DB-GPT\scripts\Restore-DBGPTData.ps1" `
  -InstallRoot "C:\Program Files\HGTech\DB-GPT" `
  -BackupRoot "D:\HGTechBackups\before-upgrade-001" `
  -NewDataRoot "C:\ProgramData\HGTech\DB-GPT-rollback-001"
```

验证新版本后再切换服务的 `DBGPT_DATA_DIR`。升级失败时停止新服务，将程序路径和数据路径切回旧版本。旧程序目录和旧数据目录在回滚验收前不得删除。

普通文件复制不能保证运行中SQLite元数据库和Chroma的一致性，因此正式备份必须在DB-GPT服务停止后执行。外部C++生产数据库不属于DB-GPT备份范围，脚本不会读取或复制它。

## 当前整体验收状态

| 验收项 | 当前状态 |
| --- | --- |
| UI隐藏和品牌结果 | 自动化测试通过 |
| SQLite底层只读 | 单元与集成测试通过 |
| SQL单条只读、行数、输出、超时、并发 | 自动化测试通过 |
| 合成SQLite并发读写 | 本机短测通过 |
| 文档解析与定时任务代码链路 | 自动化测试通过 |
| Python应用wheels、完整wheelhouse和断网安装 | 当前Windows准备机真实介质及全新临时环境通过；干净目标机待验收 |
| Ollama模型仓库结构、三个固定标签和blob完整性 | 24.65GB真实仓库通过，RTX 5090生成与Embedding接口通过 |
| 离线发布组包、关键文件校验和运行时自检 | 26.86GB完整候选发布目录及发布副本 `--no-index` 安装通过 |
| 运行数据备份、校验、恢复到新目录 | 临时数据测试通过 |
| 五粮液数据库与C++模拟宿主一小时联合测试 | 120秒并发短测通过；宿主不可用提示及恢复重连单测通过；一小时测试待目标环境 |
| Windows服务实际安装、自启动、恢复 | 待目标环境 |
| RTX 5090断网模型功能、RTX 3090产线性能复测 | RTX 5090联网准备机接口通过；物理断网全新安装和RTX 3090仍待验收 |
| 完全断网全新安装 | 完整发布介质已就绪；待干净目标机执行 |
| 实际文档、知识库问答和模型定时任务 | 待本地模型 |
| 升级切换和真实回滚演练 | 待目标环境 |

## 投产门禁

当前版本仍不能标记为已通过产线验收。只有表格中所有“待目标环境/待模型”的项目完成并留存环境信息、测试报告和日志后，才能进入生产。

目标机验收至少记录Windows版本、CPU、内存、GPU和驱动、Python、SQLite、journal mode、模型与量化、数据库大小、C++写入负载、查询配置、测试起止时间和异常记录。

## 自动化验收

```powershell
.venv\Scripts\python.exe -m pytest tests\deployment -q
.venv\Scripts\ruff.exe check scripts\windows tests\deployment
npm --prefix web run test:ui-visibility
```
