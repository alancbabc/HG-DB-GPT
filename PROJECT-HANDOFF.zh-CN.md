# DB-GPT 二次开发项目交接说明

> 最后更新：2026-09-01  
> 当前集成分支：`dev_deploy`  
> 当前离线发布：`0.8.1-dev-deploy-20260831-stage21.4`  
> 当前离线发布对应提交：`ab38e7ff2a344aed818b4301a2a368cd19cfdf37`  
> 对应标签：`offline-stage21.4`

本文供后续开发、测试和运维人员接手使用，目标是说明项目现状和关键边界，而不是替代源码文档。
接手前应先读本文，再读 [AGENTS.md](AGENTS.md) 和
[技术架构分析](DB-GPT-Technical-Architecture-Analysis.zh-CN.md)。

## 1. 项目是什么

本项目是基于开源 DB-GPT 0.8.1 代码线进行的二次开发。Python 包版本仍为 `0.8.1`，
实际二开起点是上游 `main` 的 `651fc13e`，该起点比 `v0.8.1` 标签多出一批上游提交，
包括多文件上传和分析能力。

仓库关系如下：

- **本项目远程仓库**：<https://github.com/alancbabc/HG-DB-GPT>。这里保存本项目的品牌、
  UI、SQLite、离线部署和工具修复，是后续开发、分支协作、打标签和发布追溯的主仓库。
- **DB-GPT 上游源项目**：<https://github.com/eosphoros-ai/DB-GPT>。这里是原始开源项目，
  用于查看官方实现、Issue、发布版本和后续更新，不是本项目二开代码的推送目标。
- **上游 v0.8.1 版本**：<https://github.com/eosphoros-ai/DB-GPT/releases/tag/v0.8.1>。
  `codex/v0.8.1` 保存该正式版本快照；本项目实际集成基线则是后续的 `651fc13e`。

本项目不是持续自动同步上游的镜像。合并上游更新前必须单独评估与 UI 可见性、Agentic Data、
静态前端、`uv.lock`、SQLite 查询保护和离线介质的冲突，通过回归测试后再进入 `dev_deploy`。

它仍然是一个通用 Agent 平台，不是只读 SQLite 问答工具。主链路是：

```text
Web / API
  -> Agentic Data API
  -> ReAct Agent
  -> SQL、Python、Shell、文件、知识库、Skill 等工具
  -> Ollama / 其他模型服务 + 数据源 + RAG
  -> 流式步骤、表格、图表、HTML 报告和最终回答
```

项目还保留传统 Scene Chat、AWEL 工作流、模型管理、应用管理、Connectors、评测等上游能力。
部分入口在当前生产 UI 中被隐藏，但后端实现并未删除。

当前产品名称和品牌为“华工·筑视 智检助手”。生产方向是完全断网的 Windows 单机部署，
由本机浏览器访问，使用本地 Ollama 提供 LLM 和 Embedding。

## 2. 当前结论

- 当前应以 `dev_deploy` 作为继续开发和制作发布包的基线。
- Stage 21.4 已由项目负责人在 Windows 11 + RTX 5090 机器上完成实际安装验收，并确认可正常使用。
- 最终生产机器是 Windows 10 + RTX 3090 24 GB。换机后仍必须复测驱动兼容、显存占用、
  冷启动、16K 上下文、响应时间和长时间稳定性，不能直接套用 5090 的性能结论。
- 外部 C++ 程序持续写入的真实 SQLite 数据库仍需要在最终环境完成一小时联合读写测试。
- 代码、模型、wheelhouse 和安装脚本已经具备完整离线交付链路；大型离线包不进入 Git。

### 2.1 接手人实际得到的交付物

后续接手人只依赖以下三项交付物，不应依赖当前开发者电脑上的源码目录、临时构建目录或个人盘符：

| 交付物 | 内容 | 接手时的用途 |
| --- | --- | --- |
| 本项目远程仓库 | <https://github.com/alancbabc/HG-DB-GPT> | 获取全部源码、提交历史、分支、标签、测试和维护文档 |
| 最新离线包 | Stage 21.4 完整发布目录 | 在断网 Windows 目标机安装；先校验 `release-manifest.json`，再运行 `Install-DBGPT.cmd` |
| `测试数据库` 文件夹 | `五粮液`、`光模块` 两套 SQLite 样例及结构说明 | 验证数据源连接、自然语言查询、只读保护、业务 SQL、图表和报告 |

远程仓库是源码和版本历史的唯一交接事实来源。本文必须随 `dev_deploy` 推送到远程；离线包和测试数据库
不进入 Git，应通过移动硬盘或受控文件介质单独交付。

`测试数据库` 文件夹应保持原目录结构整体交付：

```text
测试数据库/
├── 五粮液/
│   ├── runtime_vi_agent.db
│   ├── runtime_vi_agent.db-wal
│   ├── runtime_vi_agent.db-shm
│   └── wuliangye.md
└── 光模块/
    ├── om_inspection_simulation.db
    ├── om_inspection_simulation.db-wal
    ├── om_inspection_simulation.db-shm
    └── om_inspection_db.md
```

- 五粮液样例为 `user_version=7`，包含相机、缺陷目录、批次、扫描轮次、检测结果和缺陷六张基础表；
  其业务约定是一个完整检测批次在同一个事务中写入，适合验证原子批次查询。
- 光模块样例为 `user_version=1`，记录 PLC 条码请求、四位置 YOLO 推理和下料结果；生产链路分阶段提交，
  查询时可能看到“请求已存在、推理或下料尚未完成”的合法中间状态，适合验证完成状态判断。
- 两个目录中的 Markdown 是表结构和业务语义说明，接手人写 SQL 或让模型理解字段前应先阅读。
- 复制活动 SQLite 数据库前应停止写入并关闭连接；如果不能停止，必须把 `.db`、`-wal`、`-shm`
  作为同一时点的一组文件处理，不能只复制 `.db`。

这两套文件是测试数据库快照，**不包含 C++ 写入程序或模拟写入宿主**。仅凭当前三项交付物，可以完成
静态查询、业务分析和安装功能验收，但不能复现真实 C++ 持续写入负载。后续若要完成产线一小时并发
验收，必须另行取得实际 C++ 软件或能够产生等价事务行为的模拟写入程序及运行说明。

## 3. 主要功能

### 3.1 上游平台能力

- Agentic 数据分析：任务规划、ReAct、多步工具调用、子 Agent、上下文管理和流式状态。
- 多源数据：关系型数据库、CSV/Excel、多文件、文档、知识库和外部 Connector。
- SQL、Python、Shell：查询、数据处理、统计、绘图、脚本和 CLI 工作流。
- RAG：文档解析、切分、Embedding、向量/全文/图检索和引用。
- 报告：Markdown、代码、表格、图表、图片和自包含 HTML 报告。
- 模型层：本地模型和多种代理模型 Provider，Controller/Worker 统一管理。
- AWEL：适合步骤固定的确定性 DAG 工作流。
- 定时任务：Cron 对话重放、任务状态和运行历史。
- 管理能力：数据源、模型、知识库、Prompt、应用、Skills、Connectors 和评测。

### 3.2 本项目二开内容

1. **品牌与精简 UI**
   - 替换产品名称、Logo、favicon 和报告署名。
   - 用 `web/public/ui-visibility.json` 集中控制桌面端入口。
   - 当前保留 Agent 工作台、文件上传、数据源、知识库、模型和定时任务等主要入口。
   - 当前隐藏 Skills、应用、AWEL、Prompt、Connectors、社区、模型评测、用户信息等入口。
   - 隐藏只影响显示；直接 URL、API 和后端能力仍可能可用，不是权限控制。

2. **SQLite 生产查询能力**
   - 保留原有普通 SQLite 连接，默认仍可读写。
   - 数据源显式选择 `read_only` 时，使用 SQLite `mode=ro` 和 `PRAGMA query_only=ON`。
   - SQL 工具只允许单条只读 `SELECT` 或只读 CTE，拒绝 DML、DDL、`PRAGMA`、
     `ATTACH`、多语句等状态变更形式。
   - 默认限制返回行数、输出字符数、执行时间和进程内查询并发，并可实际取消 SQLite 长查询。
   - 提供合成读写探针和真实 C++ 宿主只读探针。

3. **完全离线 Windows 部署**
   - 固定 Python、Ollama、VC++、NSSM、Python wheels、模型和 tokenizer 缓存。
   - 提供发布构建、介质校验、一键安装、服务注册、桌面快捷方式、健康检查、备份恢复和验收脚本。
   - 运行时不依赖 PyPI、npm、模型下载、CDN、在线字体或云模型 fallback。
   - HTML 报告会拒绝需要联网加载的外部资源。

4. **工具失败语义修复**
   - Python 子进程超时、非零退出或异常会被 Agent 标记为工具失败，不再把 traceback 文本误当成成功结果。
   - 每次 Python 工具调用都是新进程，变量和 import 不跨调用保留；生成代码必须自包含。

## 4. 当前 UI 状态

当前配置文件是 [web/public/ui-visibility.json](web/public/ui-visibility.json)，规则说明见
[web/config/ui-visibility.md](web/config/ui-visibility.md)。缺失或非法配置默认按“可见”处理，
避免升级后误隐藏功能。

修改后必须在 `web` 目录执行：

```powershell
npm run sync:ui-visibility
npm run test:ui-visibility
```

同步命令会把配置复制到 Python 包内的预构建静态 Web 目录。只改源文件但不同步，离线包中不会生效。
是否隐藏新入口应由产品负责人确认；不要通过删除路由、API、模型或数据结构来实现隐藏。

## 5. 代码结构和优先阅读位置

| 目录/文件 | 作用 |
| --- | --- |
| `packages/dbgpt-core` | Agent、AWEL、组件、模型和数据源核心抽象 |
| `packages/dbgpt-ext` | SQLite 等数据源、模型、存储和 RAG 具体适配 |
| `packages/dbgpt-serve` | 数据源、知识库、模型、任务等领域服务和 DAO/API |
| `packages/dbgpt-app` | 应用装配、Agentic Data 主链路、工具和静态 Web |
| `packages/dbgpt-client` | Python SDK |
| `packages/dbgpt-sandbox` | 可选执行运行时；不要据此假定当前工具已经容器隔离 |
| `web` | Next.js/React 前端源码 |
| `skills` | 内置领域 Skill、脚本和模板 |
| `configs` | 开发配置和 Windows 离线部署配置 |
| `scripts/windows` | 离线介质、安装、启动、验收、备份和 SQLite 探针 |
| `tests/deployment` | Windows 离线部署自动化测试 |
| `docs/deployment/windows-offline` | 离线产线化阶段记录 |

处理主业务链时，优先阅读：

- `packages/dbgpt-app/src/dbgpt_app/openapi/api_v1/agentic_data_api.py`
- `packages/dbgpt-app/src/dbgpt_app/openapi/api_v1/tools/`
- `packages/dbgpt-core/src/dbgpt/agent/`
- `packages/dbgpt-ext/src/dbgpt_ext/datasource/rdbms/conn_sqlite.py`
- `web/hooks/use-react-agent-chat.ts`
- `web/pages/index.tsx`

架构分析文档的基线早于后续 SQLite 和部署改造。涉及运行身份、SQL 保护或部署时，
以当前代码、[AGENTS.md](AGENTS.md)、[阶段 19](docs/deployment/windows-offline/phase-19-current-user-launch.md)
和 [阶段 20](docs/deployment/windows-offline/phase-20-one-click-bootstrap.md) 为准。

## 6. Git 仓库、分支和标签

### 6.1 远程仓库

| 名称 | 地址 | 用途 |
| --- | --- | --- |
| `origin` | [eosphoros-ai/DB-GPT](https://github.com/eosphoros-ai/DB-GPT) | DB-GPT 上游，只用于获取和比较上游更新 |
| `hg-github` | [alancbabc/HG-DB-GPT](https://github.com/alancbabc/HG-DB-GPT) | 本项目远程仓库，二开分支和标签推送到这里 |

避免误把公司二开提交推送到 `origin`。

### 6.2 本项目分支

| 分支 | 发布/基准提交 | 内容和用途 |
| --- | --- | --- |
| `main` | `651fc13e` | 上游开发基线；用于对照上游，不直接承载本项目新功能 |
| `codex/v0.8.1` | `177bfc84` | 上游正式 `v0.8.1` 快照；用于版本差异和回归定位 |
| `project-architecture-20260821` | `ae01dbf7` | 技术架构分析、核心功能分级、UI 配置化边界文档 |
| `ui_hidden` | `785b9b6d` | “华工·筑视”品牌、集中 UI 可见性配置和已构建静态前端 |
| `dev_deploy` | `offline-stage21.4` → `ab38e7ff` | 当前完整集成分支：包含以上内容及 SQLite、离线模型、安装部署和工具修复；发布后的文档提交会继续向前 |

五个分支均已同步到 `hg-github`。远程默认分支当前指向 `dev_deploy`。

分支演进关系可以简化理解为：

```text
main
  -> project-architecture-20260821
  -> ui_hidden
  -> dev_deploy

v0.8.1 tag
  -> codex/v0.8.1  （独立上游版本快照）
```

重要标签：

- `project-analysis-v1.0.0`：架构分析文档基线。
- `offline-stage21.4`：当前离线发布源代码，必须保持不可变。

后续日常开发建议从 `dev_deploy` 新建短期功能/修复分支，验证后再合回。不要继续在历史里程碑分支
`project-architecture-20260821` 或 `ui_hidden` 上叠加部署功能。

## 7. 最新运行时代码做到了什么

当前离线包对应的最新运行时代码提交 `ab38e7ff`，主题是 Stage 21.4 Windows 离线一键安装。
交接文档在该发布点之后提交，不改变已经交付的程序和模型介质。Stage 21.4 的主要结果：

- 离线介质根目录提供 `Install-DBGPT.cmd`，普通双击或管理员终端启动都可继续。
- 安装过程收敛为路径/端口检查、介质校验、Python/应用/模型安装、Ollama 服务、三模型实测五步。
- 修复包含空格的 `C:\Program Files\...` Python 安装路径传参问题。
- 支持识别并恢复本发布留下的未完成安装，不覆盖无法识别的现有目录。
- 不再因网卡连接或启动终端是否提权而阻止安装。
- 安装完成后创建当前安装用户的“启动 DB-GPT”和“停止 DB-GPT”桌面快捷方式。
- DB-GPT 不作为 Windows 服务自动启动；Ollama 继续作为 `HGTechOllama` 服务运行。
- 发布清单记录 `sourceCommit` 和 `sourceTag`，便于从介质追溯源码。

其前两个直接相关提交还完成了 Python 工具失败状态传播和离线 HTML 报告外部资源拦截，
因此制作新离线包时不能只摘取安装器提交而遗漏这两个运行时修复。

## 8. 离线发布物和固定运行环境

当前 Stage 21.4 候选包约 25.02 GiB，发布清单记录 340 个文件、47 个关键哈希项，
总记录大小为 26,865,983,508 字节。包内主要包含：

- 7 个 DB-GPT 应用 wheel 和完整 Windows x64 wheelhouse；
- Python 3.11.9 x64 安装器；
- Microsoft Visual C++ x64 14.50.35719.0；
- Ollama 0.32.15 Windows amd64 及 GPU 运行库；
- NSSM 2.24-101-g897c7ad；
- `qwen3.5:27b-q4_K_M` 主模型；
- `qwen3.5:9b-q4_K_M` 备用模型；
- `qwen3-embedding:0.6b` Embedding 模型；
- `cl100k_base` tokenizer 离线缓存；
- 配置、安装、启动、验收和备份恢复脚本。

部署上下文固定为 16384，Ollama 默认单模型、单路推理，并设置 `OLLAMA_NO_CLOUD=1`。
当前 Python 依赖不负责 GPU 推理，不要求目标机安装 CUDA Toolkit；GPU 由 Ollama 和 NVIDIA 驱动使用。

发布准备过程中产生的 `.stage*`、模型、wheelhouse、安装器、日志、数据库和用户数据不应提交 Git。
它们是可重新生成或单独交付的介质，不是源码仓库的一部分。

## 9. 一键安装和运行

### 9.1 目标机默认目录

```text
程序：C:\Program Files\HGTech\DB-GPT
运行数据：C:\ProgramData\HGTech\DB-GPT
模型：C:\ProgramData\HGTech\OllamaModels
Web：http://127.0.0.1:5670
Ollama：http://127.0.0.1:11434
```

第一次安装前，如需改到其他本地固定磁盘，可将介质中的 `deployment-config.json` 复制为
`deployment-config.local.json` 后修改。不要把应用、模型或运行数据长期留在移动硬盘上。

### 9.2 安装步骤

1. 把完整发布目录复制到目标机本地磁盘，或从可靠移动介质运行。
2. 双击介质根目录的 `Install-DBGPT.cmd`，按需确认 UAC。
3. 安装结束后双击桌面的“启动 DB-GPT”。
4. 浏览器访问 `http://127.0.0.1:5670`。
5. 运行 `Test-DBGPTOfflineInstallation.ps1` 留存正式验收报告。

安装器可以重试，但升级前仍必须备份。不得手工复制开发机 `.venv` 到生产机，也不得在断网目标机
临时执行 `pip install`、`npm install` 或 `ollama pull`。

### 9.3 日志和结果

```text
%LOCALAPPDATA%\HGTech\DB-GPT\Installer\setup-*.log
%ProgramData%\HGTech\DB-GPT\install\preflight.json
%ProgramData%\HGTech\DB-GPT\install\release-verification.json
%ProgramData%\HGTech\DB-GPT\install\model-validation.json
%ProgramData%\HGTech\DB-GPT\install\system-result.json
```

排障时先保存这些文件，再看 DB-GPT 和 Ollama 运行日志。不要只根据 CMD 最后一行判断根因。

## 10. 如何制作新离线版本

可直接执行的完整命令、两种组包方式和失败排查见
[从远程仓库制作 Windows 离线包](OFFLINE-RELEASE-BUILD.zh-CN.md)。接手人应以该手册为实际操作入口，
本节只保留流程摘要。

新版本必须在联网 Windows x64 准备机完成，目标机只负责安装和验收。标准顺序是：

1. 从干净、已提交的 `dev_deploy` 或发布分支确定源码提交。
2. 使用 `scripts/windows/offline_media.py` 从当前源码和 `uv.lock` 生成应用 wheels 与 wheelhouse。
3. 用 `Test-OfflinePythonMedia.ps1` 在全新临时环境执行 `--no-index` 安装、`pip check` 和运行时自检。
4. 用 `Prepare-WindowsRuntimeMedia.ps1` 准备并校验固定 Python、VC++、Ollama 和 NSSM。
5. 用 `Prepare-OllamaModelStore.ps1` 准备三个固定模型的原生 `manifests`/`blobs` 仓库。
6. 用 `offline_release.py build` 组装一个不存在的新输出目录。
7. 同时用 Python 和 `Test-OfflineRelease.ps1` 校验发布清单。
8. 复制到移动介质后再次校验；不要仅比较资源管理器显示的目录大小。
9. 在目标机完成真实安装和功能验收后再标记发布标签。

详细命令和历史原因见 [Windows 离线部署文档](docs/deployment/windows-offline/phase-20-one-click-bootstrap.md)。
每次升级 Python、Ollama、NSSM、VC++、模型标签、`uv.lock` 或前端静态资源，都必须重新制作和验收，
不能直接替换离线包中的单个文件后沿用旧清单。

## 11. SQLite 与外部 C++ 写入程序

生产数据库由外部 C++ 程序持续写入，DB-GPT 负责查询。接手人必须遵守以下边界：

- 默认普通 SQLite 连接保持上游语义；只有数据源显式选择 `read_only` 才启用底层只读。
- SQL 工具的只读校验不等于整个进程只读。Python、Shell 和文件工具仍能使用当前 Windows 用户权限。
- DB-GPT 不得修改生产库的 `journal_mode`，不得使用 `immutable=1` 读取变化中的数据库。
- 主数据库、`-wal`、`-shm` 应在同一台机器的可靠本地磁盘上。
- WAL、事务长度、busy timeout 和 checkpoint 主要由写入端评估和管理。
- 任何数据库迁移、清库、journal mode 修改或 C++ 写入逻辑调整，都必须先确认真实路径和影响。
- 正式投产前执行一小时 C++ 写入 + DB-GPT 查询联合测试，确认写入零失败、读取可恢复、
  数据库完整、WAL 不无界增长，且写入延迟增量可接受。

### 11.1 是否需要与 C++ 软件直接交互

正常查询场景下，DB-GPT **不需要调用 C++ 软件的接口，也不需要通知 C++ 暂停写入**。
双方的协作边界就是 SQLite 数据库文件：C++ 使用正常事务写入并提交，DB-GPT 使用独立连接查询。

原因是 SQLite 自身提供事务、文件锁和一致性快照。特别是在 WAL 模式下，读连接通常读取一个稳定的
已提交快照，写连接继续向 WAL 追加；正常的读操作和单写操作可以并行，不需要两个进程相互发消息。
当前已经检查过的示例数据库处于 WAL 模式，但每个实际生产数据库仍应在验收时记录其 journal mode。

这里的“不需要交互”不等于“没有要求”。至少要满足：

- C++ 必须使用 SQLite 正常事务并正确提交，不能绕过 SQLite 直接修改数据库文件。
- DB-GPT 只能看到已经提交的数据，看不到 C++ 尚未提交的中间状态；这属于正确行为。
- 数据库主文件和可能存在的 `-wal`、`-shm` 必须保持在同一个可靠本地目录，不能只复制主 `.db` 后
  把它当作实时数据，也不能把活动 WAL 数据库放在不可靠网络共享中。
- C++ 运行期间不应整体删除、替换或周期性覆盖数据库文件，也应避免在线修改表结构；否则既有连接
  可能失败或读到旧文件句柄，需要重新连接并专项处理。
- DB-GPT 查询应短小、可取消，避免长时间持有读快照导致 WAL checkpoint 无法回收。
- 如果数据库不是 WAL 模式，读写更容易发生锁等待；DB-GPT 不自行切换模式，只能通过实测和写入端
  配置解决。

### 11.2 当前查询要求和限制

当前 SQL 工具的默认生产保护如下：

| 限制 | 默认值 | 目的 |
| --- | ---: | --- |
| SQL 类型 | 单条只读 `SELECT`/只读 CTE | 防止查询工具改变生产库 |
| 返回行数 | 50 行 | 防止无界读取和模型上下文膨胀 |
| 输出字符数 | 20,000 | 控制内存、SSE 和模型输入大小 |
| SQLite 执行时间 | 30 秒 | 实际中断异常长查询 |
| 单进程查询并发 | 1 | 降低磁盘、内存和写入端压力 |
| 并发等待时间 | 5 秒 | 忙碌时快速失败，不无限排队 |

这些值可以通过 `DBGPT_SQL_QUERY_*` 环境变量调整，但必须在 3090/Win10 和真实数据库负载下重新验证，
不能因为普通查询“能运行”就取消限制。查询应尽量命中索引，避免无条件全表扫描、大排序、超大聚合
和一次返回大字段。

`read_only=true` 不是查询功能的必要条件，普通 SQLite 连接同样可以读取实时提交数据；它的作用是为
指定数据源增加数据库连接层的拒写保护。生产数据源建议选择它，但它仍不能限制当前用户权限下的
Python、Shell 或其他程序。

### 11.3 “实时数据”的业务含义

在当前无直接交互方案中，“实时”应定义为 **查询开始时 SQLite 已提交的最新状态**，而不是 C++
内存中正在处理、尚未提交的数据。单条 SQL 会看到一致快照；前后执行的两条 SQL 可能因为中间发生了
新提交而看到不同版本，这是正常现象。

如果业务要求“某个批次全部写完后才能分析”或“多张表必须属于同一个完整批次”，则需要满足以下
至少一种条件：

- C++ 把一个业务批次的相关写入放在同一个事务中原子提交；或
- C++ 在同一数据库中维护批次状态/完成标记，DB-GPT 只查询已完成批次；或
- 新增明确的 C++ 完成事件/API，再触发查询。

前两种仍不要求两个进程直接通信。只有在数据库中没有事务级完整性或完成标记、但又要求精确知道
业务处理完成时，才必须增加与 C++ 的交互。否则 DB-GPT 只能保证 SQLite 层面的一致性，不能推断
C++ 内部业务流程是否完成。

相关实现和测试见 [阶段 2](docs/deployment/windows-offline/phase-2-sqlite-read-only.md)、
[阶段 3](docs/deployment/windows-offline/phase-3-query-guards.md) 和
[阶段 4](docs/deployment/windows-offline/phase-4-concurrency-validation.md)。这些早期文档中的服务账号/ACL建议
已经被当前用户启动方案取代，读取时不要忽略后续决策。

## 12. 安全和产品边界

以下限制需要明确告知维护人员和使用方：

- DB-GPT 由安装用户启动，Python、Shell 和文件工具继承该用户权限；当前方案不是安全沙箱。
- SQLite `read_only` 只约束通过该连接器建立的连接，无法阻止 Python/Shell 重新打开用户有权修改的文件。
- 文档、数据库内容和模型输出都可能包含提示注入，不能把模型生成命令当作可信输入。
- 当前默认只监听回环地址，定位是本机单用户。若改为局域网访问，必须另行设计认证、授权、TLS、
  防火墙和审计，不能只把监听地址改成 `0.0.0.0`。
- UI 隐藏不是鉴权，隐藏页面仍可能通过 URL 或 API 访问。
- 云模型、URL 知识库、在线下载、CDN 和市场类功能不能作为离线生产链路的隐式 fallback。
- HTML 报告虽然已拒绝明显远程资源，仍应把模型生成 HTML 视为不可信内容，关注脚本注入和资源消耗。
- DB-GPT 不开机自启；电脑重启后需要用户再次双击桌面快捷方式。Ollama 服务会独立运行。

## 13. 已知技术债和局限

- `agentic_data_api.py` 和 `web/pages/index.tsx` 都是大型聚合文件，修改容易产生跨功能回归；
  后续可按会话、资源、上传、工具和渲染逐步拆分，但不要在部署修复中夹带大规模重构。
- Agent Chat、传统 Scene Chat 和 AWEL Chat 多套协议并存，历史消息和前端渲染兼容成本较高。
- Python/Shell 的超时、路径检查和子进程并不等于容器隔离。
- SQL 返回行数和输出大小已限制，但超大单字段仍可能先进入驱动内存，需要用真实大字段继续压测。
- 当前 SQL 并发限制是单 DB-GPT 进程内限制；未来若改多进程，需要外部统一并发控制。
- 前端 `next.config.js` 允许忽略部分 TypeScript 构建错误，不能仅以构建成功判断类型安全。
- 上游 Provider、数据库和可选依赖很多，离线包只保证已经纳入介质并经过验收的组合。
- 定时任务需要继续关注进程重启恢复、错过触发、全局队列/并发、真实中断和日志保留。
- 5090/Win11 验收证明当前介质和功能链可用，不代表 3090/Win10 性能已经达标。

## 14. 开发和测试建议

源码开发推荐使用 Python 3.11 和 `uv`，以 `uv.lock` 为依赖事实来源。通用安装和启动方式参考
[源码安装文档](docs/docs/installation/sourcecode.md)；离线生产环境不要套用在线快速安装说明。

后端改动至少运行受影响模块测试、Ruff 和部署测试：

```powershell
uv run pytest <受影响测试路径> -q
uv run pytest tests/deployment -q
uv run ruff check <受影响源码和测试>
```

前端改动至少运行：

```powershell
npm --prefix web run test
npm --prefix web run build
```

若改了可见性配置，再运行同步检查。若改了 SQL、代码执行、HTML 报告、安装脚本或数据恢复，
必须补复现测试，并同时验证失败路径和正常路径。PowerShell 脚本还要在包含空格、中文和不同盘符的路径下测试。

任何开发工作区存在未跟踪的大型发布目录时，提交前使用 `git status` 和 `git diff` 精确确认范围，
不要使用会删除全部未跟踪文件的清理命令。

## 15. 升级、备份和回滚

升级前停止 DB-GPT 并使用 `Backup-DBGPTData.ps1` 备份运行数据。备份范围应包含：

- DB-GPT 元数据库；
- 向量数据和知识库索引；
- 定时任务和会话；
- 上传文件和生成结果；
- 安装生成的加密密钥。

外部 C++ 生产数据库不属于 DB-GPT 备份脚本范围，应由业务系统单独负责。

恢复脚本应恢复到一个新的 DataRoot，不直接覆盖当前数据目录。升级完成前保留旧程序、旧数据和旧离线包；
验证 Web、模型、Embedding、SQLite、知识库和任务后再切换。详细流程见
[阶段 8](docs/deployment/windows-offline/phase-8-acceptance-and-rollback.md)，其中旧的 DB-GPT 服务表述
应替换为当前用户桌面进程理解。

## 16. 上游同步与长期维护建议

1. `main` 只跟踪/对比上游，二开从 `dev_deploy` 或其发布分支继续。
2. 上游升级先在临时分支分析差异，不要直接把新 `main` 强推或大范围 rebase 到当前发布分支。
3. 优先挑选安全修复和明确依赖的功能，再处理 Agentic API、前端聚合页、静态资源和 `uv.lock` 冲突。
4. 保持 UI 隐藏为集中配置，不删除后端业务实现。
5. 基础设施、SQLite、Agent 工具和前端修改分开提交，便于回滚和定位。
6. 每个离线发布必须对应一个已推送提交和不可变标签，清单写入完整 commit/tag。
7. 不提交密钥、机器路径、模型、数据库、日志、`.venv`、wheelhouse 或 `.stage*`。
8. 固定第三方版本发生变化时，更新锁文件、构建脚本、文档和验收记录，不能只更新说明文字。
9. 生产问题先保留日志和失败介质，修复后在新版本目录重新组包，不在已标记发布包上原地改文件。

## 17. 接手后的第一轮检查清单

- 确认当前分支为 `dev_deploy`，并确认 `offline-stage21.4` 仍指向 `ab38e7ff`；分支 HEAD
  可以包含该发布点之后的文档或新开发提交。
- 从 `hg-github` 克隆仓库，查看远程分支和标签，不依赖原开发机的本地分支状态。
- 查看 `git status`，确认新克隆工作区干净；离线包和测试数据库放在仓库外。
- 确认 `origin` 与 `hg-github` 的角色，避免推错远程。
- 阅读 `AGENTS.md`、架构分析、UI 可见性说明和离线阶段 19/20。
- 在开发环境跑部署测试和 UI 可见性测试。
- 用清单校验收到的 Stage 21.4 离线包；复制到新介质后再校验一次。
- 阅读两套测试数据库的 Markdown，分别验证完整批次和分阶段提交数据的查询语义。
- 在最终 Win10 + RTX 3090 上记录系统版本、GPU/驱动、CPU、内存、磁盘和模型测试结果。
- 取得真实 C++ 软件或等价模拟写入程序后，再完成一小时并发测试；在此之前明确记录该项不可复现。
- 完成备份恢复演练和重启恢复检查。
- 任何“已经投产可用”的结论都应附环境信息、版本、日志和验收报告，不只依赖口头结论。

## 18. 文档优先级

出现冲突时按以下顺序判断：

1. 当前代码和自动化测试；
2. [AGENTS.md](AGENTS.md) 中的最新产品与工程决策；
3. 本交接说明；
4. 阶段 19/20 及较新的离线部署文档；
5. 更早的阶段文档和架构分析中的历史描述；
6. 上游 README 和通用安装文档。

早期阶段文档保留是为了说明问题如何演进，并不意味着其中的 `LocalService`、双服务、强制断网拦截、
额外数据库 ACL 或 8192 上下文仍是当前方案。
