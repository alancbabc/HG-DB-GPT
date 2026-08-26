# Windows 离线产线化：阶段 5 本地模型链路

## 当前状态

本阶段已提供只监听本机的生产配置模板和不访问互联网的Ollama健康检查工具。Python离线介质已包含并真实安装验证 `ollama` 客户端；三个固定模型已在RTX 5090开发机完成真实下载、LLM生成和Embedding调用验收，详细结果见阶段14文档。

已确认后续真实模型为：主 LLM `qwen3.5:27b-q4_K_M`、备用 LLM `qwen3.5:9b-q4_K_M`、Embedding `qwen3-embedding:0.6b`。三个标签已在Ollama官方模型库确认存在；当前页面标示的介质规模约为17 GB、6.6 GB和639 MB。先在 RTX 5090 干净断网测试机完成安装和功能验证，最终在 RTX 3090 24 GB 产线机复测显存与响应时间。

- [qwen3.5 标签列表](https://ollama.com/library/qwen3.5/tags)
- [qwen3-embedding 标签列表](https://ollama.com/library/qwen3-embedding/tags)

## 配置模板

`configs/dbgpt-windows-offline-ollama.example.toml`要求安装时提供：

- `DBGPT_ENCRYPT_KEY`：每台设备单独生成，不提交仓库。
- `DBGPT_DATA_DIR`：DB-GPT可写运行数据绝对路径。
- `DBGPT_LLM_MODEL`：Ollama已注册的本地LLM名称。
- `DBGPT_FALLBACK_LLM_MODEL`：主模型不可用或性能不足时人工切换的备用LLM。
- `DBGPT_EMBEDDING_MODEL`：Ollama已注册的本地Embedding名称。

Web和Ollama API均使用回环地址。模板没有云模型fallback，也不包含机器专用密钥、模型文件或生产路径。

离线Python wheelhouse必须包含 `dbgpt` 的 `proxy_ollama` 可选依赖；目标机不得使用 `pip install ollama` 联网补装。

## 健康检查

```powershell
.venv\Scripts\python.exe scripts\windows\check_ollama_offline.py `
  --llm-model qwen3.5:27b-q4_K_M `
  --fallback-llm-model qwen3.5:9b-q4_K_M `
  --embedding-model qwen3-embedding:0.6b `
  --expected-version 0.32.15
```

工具只允许访问HTTP回环地址，并依次验证：

1. Ollama版本接口可达；
2. 主LLM、备用LLM和Embedding名称均存在于本地模型列表；
3. 两个LLM分别完成非流式生成并立即卸载；
4. Embedding返回至少一个非空向量。

任一检查失败均返回非零退出码，不尝试下载模型或切换云服务。

## 自动化验收

```powershell
.venv\Scripts\python.exe -m pytest tests\deployment\test_ollama_offline_check.py -q
.venv\Scripts\ruff.exe check scripts\windows\check_ollama_offline.py tests\deployment\test_ollama_offline_check.py
```

开发机真实接口和模拟测试通过后，仍保留以下目标机验收项：在完全断网的干净Windows测试机导入同一模型仓库，验证中文SQL生成、工具调用、知识库检索、定时任务和失败恢复；最终在RTX 3090 24GB产线机复测显存、冷启动和响应时间。完成这些验收前不能判断模型链路已达到产线交付条件。
