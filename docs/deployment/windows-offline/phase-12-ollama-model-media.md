# Windows 离线产线化：阶段 12 Ollama 与模型介质

## 阶段目标

把模型交付格式固定为Ollama原生模型仓库，而不是任意非空目录或零散GGUF文件。
发布包必须同时包含 `manifests`、`blobs` 和以下三个精确标签：

- 主LLM：`qwen3.5:27b-q4_K_M`；
- 备用LLM：`qwen3.5:9b-q4_K_M`；
- Embedding：`qwen3-embedding:0.6b`。

官方Windows文档说明，服务集成应使用独立的
[`ollama-windows-amd64.zip`](https://docs.ollama.com/windows)，模型位置通过
`OLLAMA_MODELS` 指定。模型标签及当前大小以
[qwen3.5](https://ollama.com/library/qwen3.5/tags) 和
[qwen3-embedding](https://ollama.com/library/qwen3-embedding/tags) 官方页面为准。

## 联网准备机生成模型仓库

先将固定版本的Ollama Windows独立程序解压到准备目录，再执行：

```powershell
powershell -ExecutionPolicy Bypass -File `
  scripts\windows\Prepare-OllamaModelStore.ps1 `
  -OllamaExe D:\Inputs\ollama\ollama.exe `
  -ModelsRoot D:\Inputs\ollama-models `
  -PythonExe C:\Python311\python.exe
```

脚本使用独立回环端口和全新的模型根目录依次拉取三个模型，不复用用户现有Ollama
仓库。输出目录已存在时拒绝覆盖。准备完成后，`ollama_model_store.py`读取manifest，
验证必需标签、所有引用blob是否存在以及大小是否一致；不对约24 GB模型重复哈希。

也可独立复核已有介质：

```powershell
python scripts\windows\ollama_model_store.py D:\Inputs\ollama-models
```

## 安装和运行约束

- 发布组包和目标机复制完成后都会再次执行模型仓库验证；
- Ollama只监听 `127.0.0.1:11434`，使用 `NetworkService` 和专用模型目录；
- 设置 `OLLAMA_NO_CLOUD=1`，禁止云模型和Web搜索回退；
- 默认只加载一个模型、单路推理，避免主LLM与Embedding同时占满3090显存；
- 初始上下文固定为8192，待3090实测后才能上调；
- 健康检查依次生成主LLM、备用LLM和Embedding结果，并使用 `keep_alive=0`
  及时卸载，避免健康检查自身长期占用显存。

## 本阶段边界

代码侧已能拒绝缺标签、缺blob、截断blob和无效manifest，配置已注册主、备用和
Embedding三条链路。真实约24 GB模型尚未下载，本阶段不能代替RTX 5090干净机和
RTX 3090产线机上的实际推理、显存及性能验收。
