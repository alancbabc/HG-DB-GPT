# Windows 离线产线化：阶段 18 Tokenizer 缓存与上下文统一

## 问题

本机进程级断网安装后，数据分析请求在模型生成前失败。Ollama模型标签不在
`tiktoken`内置名称映射中，DB-GPT回退到 `cl100k_base`；服务账号没有构建用户的
临时缓存，因此尝试从Azure Blob下载编码文件，并被出站隔离规则正确阻止。

该问题与Ollama模型、SQLite数据源和网络隔离规则本身无关，根因是发布包漏掉了
运行时必须的tokenizer资源。不能通过允许联网或复制到某个用户的 `%TEMP%` 解决，
因为产线服务使用 `LocalService`，且用户目录与临时目录在不同Windows机器上不稳定。

## 固化方案

- 组包命令新增必填 `--tiktoken-cache-file`，只接受已确认的 `cl100k_base` 缓存；
- 缓存安装到 `<InstallRoot>\tiktoken-cache`，不依赖源码路径、用户名、盘符或 `%TEMP%`；
- `HGTechDBGPT`服务环境使用从实际安装目录计算出的绝对 `TIKTOKEN_CACHE_DIR`；
- tokenizer缓存体积约1.6 MB，作为关键运行文件做一次SHA-256校验；大模型和wheelhouse
  仍不做重复全量哈希；
- 安装运行时自检显式导入`tiktoken`，安装验收实际从缓存加载`cl100k_base`并编码中文；
- DB-GPT Agent预算、两个LLM provider和Ollama服务统一使用
  `DBGPT_CONTEXT_LENGTH`/`OLLAMA_CONTEXT_LENGTH`，默认16384，避免一侧120000、一侧8192
  的配置漂移；
- 服务注册和测试使用 `Join-Path`及解析后的安装绝对路径，覆盖包含空格的安装目录。

## Windows权限与验收脚本

模型目录保持Administrators、SYSTEM和NetworkService受保护ACL。普通操作员无法直接
扫描模型目录时，安装验收不再误报模型损坏，而是通过回环Ollama API检查固定标签、
27B与9B真实生成以及Embedding。管理员运行验收时仍会执行模型仓库文件结构检查。

普通用户无法调用 `Get-NetTCPConnection` 的系统上，监听地址检查回退到Windows自带
`netstat.exe`，避免把权限不足误判为外网监听。防火墙规则状态检查仍需管理员权限。

## 本机复验结果

2026-08-27在当前Windows 11、RTX 5090安装实例完成复验：

- DB-GPT与Ollama服务均运行，Web健康接口正常且两个端口仅监听回环；
- 服务环境中的tokenizer路径为
  `C:\HGTechOfflineAcceptance\DB-GPT\tiktoken-cache`，离线中文编码成功；
- DB-GPT与Ollama上下文均为16384；
- `qwen3.5:27b-q4_K_M`、`qwen3.5:9b-q4_K_M`生成成功；
- `qwen3-embedding:0.6b`返回1024维向量；
- 模型目录对普通操作员保持不可读，功能验收通过Ollama API完成；
- 部署单元测试9项通过，包括带空格安装路径的服务注册预检。
- Stage 18候选包约25.02 GiB、清单330项，两种清单校验、tokenizer加载及
  `--no-index`全新Python环境安装、`pip check`和运行时自检全部通过；包内配置与脚本
  未发现构建用户名、源码路径或本机验收路径硬编码。

本阶段仍不能替代干净Windows机器的物理断网全新安装，也不能替代RTX 3090产线机
上的16K上下文显存、延迟和一小时业务链路验收。
