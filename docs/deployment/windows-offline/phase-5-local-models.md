# Windows 离线产线化：阶段 5 本地模型链路

## 当前状态

本阶段已提供只监听本机的生产配置模板和不访问互联网的Ollama健康检查工具。当前开发机没有Ollama可执行程序、Python `ollama` 包或运行在11434端口的服务，因此只能通过本地模拟服务完成接口自动化测试，不能将真实LLM与Embedding标记为已验收。

## 配置模板

`configs/dbgpt-windows-offline-ollama.example.toml`要求安装时提供：

- `DBGPT_ENCRYPT_KEY`：每台设备单独生成，不提交仓库。
- `DBGPT_DATA_DIR`：DB-GPT可写运行数据绝对路径。
- `DBGPT_LLM_MODEL`：Ollama已注册的本地LLM名称。
- `DBGPT_EMBEDDING_MODEL`：Ollama已注册的本地Embedding名称。

Web和Ollama API均使用回环地址。模板没有云模型fallback，也不包含机器专用密钥、模型文件或生产路径。

离线Python wheelhouse必须包含 `dbgpt` 的 `proxy_ollama` 可选依赖；目标机不得使用 `pip install ollama` 联网补装。

## 健康检查

```powershell
.venv\Scripts\python.exe scripts\windows\check_ollama_offline.py `
  --llm-model $env:DBGPT_LLM_MODEL `
  --embedding-model $env:DBGPT_EMBEDDING_MODEL
```

工具只允许访问HTTP回环地址，并依次验证：

1. Ollama版本接口可达；
2. LLM和Embedding名称均存在于本地模型列表；
3. LLM非流式生成返回有效文本；
4. Embedding返回至少一个非空向量。

任一检查失败均返回非零退出码，不尝试下载模型或切换云服务。

## 自动化验收

```powershell
.venv\Scripts\python.exe -m pytest tests\deployment\test_ollama_offline_check.py -q
.venv\Scripts\ruff.exe check scripts\windows\check_ollama_offline.py tests\deployment\test_ollama_offline_check.py
```

模拟测试通过后，本阶段仍保留以下目标机验收项：离线导入7B至14B量化LLM和本地Embedding、运行本工具、验证中文SQL生成、工具调用、知识库检索、定时任务、显存和失败恢复。模型介质和3090目标机到位前不能关闭这些验收项。
