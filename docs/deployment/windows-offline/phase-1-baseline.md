# Windows 离线产线化：阶段 1 基线

## 阶段目标

在修改 SQLite 连接层之前，冻结已确认的部署边界、记录当前实现风险，并提供可重复的 Windows 环境采集与基础功能测试方法。本阶段不改变业务行为，不连接或修改生产数据库。

## 已确认边界

- 目标系统为 Windows 10 22H2 及以上或 Windows 11 x64；目标 GPU 为 RTX 3090 24 GB，内存为 16 GB 或 32 GB。
- 目标环境完全断网，只允许部署电脑通过本机浏览器访问；Web 和 Ollama 的产线配置均只监听回环地址。
- 数据源为一份约 10 GB 的 SQLite 数据库，外部 C++ 软件约每 30 秒写入一次。
- 第一方案是直接只读连接实际数据库，不开发快照服务，不依赖修改 C++ 软件或与其进行接口交互。
- 生产连接必须使用 SQLite URI `mode=ro`，并在每个连接上启用 `PRAGMA query_only=ON`；DB-GPT 不改变生产数据库的 journal mode。
- 保留项目现有 Python 和 Shell 能力；生产环境使用独立低权限 Windows 服务账户，并以操作系统 ACL 限制其对生产数据库和无关目录的权限。
- 文档、知识库和定时任务按项目当前能力验收，不在产线化工作中增加新的业务功能。
- 允许通过移动介质导入离线安装包、模型和升级包。

## 当前代码基线

基线提交为 `785b9b6d`，开发分支为 `dev_deploy`。检查得到以下事实：

1. `SQLiteConnector.from_parameters()` 使用普通的 `sqlite:///path` 引擎，未启用底层只读模式。
2. `SQLiteConnector.from_file_path()` 会创建缺失的父目录，并可创建新的 SQLite 文件。
3. SQLite 连接器保留 `_write()`，默认连接仍支持通用平台原有的写入能力。
4. 现有 SQLite 单元测试覆盖默认连接建表、写入、查询和自动创建目录；阶段 2 必须保持默认模式兼容，只为生产数据源增加显式只读模式。
5. 示例 Ollama 配置当前监听 `0.0.0.0`、使用相对运行数据路径，并包含占位加密密钥，不是可直接交付的生产配置。
6. 前端 UI 可见性配置已有独立测试，后续部署改造必须保持其结果不变。

## 开发机采集结果

2026-08-26 的本地基线：

| 项目 | 结果 |
| --- | --- |
| 分支 | `dev_deploy` |
| Python | 3.11.14 |
| Python 架构 | AMD64 |
| Python SQLite | 3.50.4 |
| 操作系统报告 | Windows 10，build 26200，AMD64 |
| GPU | NVIDIA GeForce RTX 5090，32607 MiB，驱动 591.86 |

开发机 GPU 与目标 RTX 3090 不一致，因此本机模型性能结果只能验证功能，不能代替目标机性能验收。当前权限下 CIM 无法读取 CPU 和物理内存，产线安装验收时必须使用有权限的服务安装账户重新采集。

## 可重复采集

在仓库根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\collect-deployment-baseline.ps1
```

脚本仅进行只读检查并将 JSON 输出到标准输出，不修改系统设置。若需要保存结果，由验收人员在仓库外的发布记录目录重定向输出；不得提交机器专用采集结果。

## 阶段 1 功能验收

```powershell
.venv\Scripts\python.exe -m pytest packages\dbgpt-ext\src\dbgpt_ext\datasource\rdbms\tests\test_conn_sqlite.py -q
Set-Location web
npm run test:ui-visibility
```

通过标准：

- SQLite 连接器现有默认读写行为测试全部通过，且 Windows 临时文件不再因未关闭连接而残留。
- UI 可见性测试全部通过，确认产线化基线未改变已完成的 UI 隐藏结果。
- 环境采集脚本成功输出可解析 JSON；无法读取的受限信息以警告记录，不导致脚本修改系统或伪造结果。

## 阶段 2 入口条件

阶段 2 只增加显式、可选的生产只读连接模式。默认 SQLite 数据源仍保持原有通用平台语义。修改前后都必须测试：默认模式可正常读写，只读模式可查询但无法写入、无法创建缺失路径，且所有连接均正确释放。
