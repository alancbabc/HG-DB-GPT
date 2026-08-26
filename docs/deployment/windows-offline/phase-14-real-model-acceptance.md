# Windows 离线产线化：阶段 14 真实模型验收

## 验收对象

- Ollama 0.32.15，监听 `127.0.0.1`，设置 `OLLAMA_NO_CLOUD=1`。
- 主模型：`qwen3.5:27b-q4_K_M`。
- 回退模型：`qwen3.5:9b-q4_K_M`。
- Embedding：`qwen3-embedding:0.6b`。
- 开发验收机：Windows、RTX 5090 32GB、驱动591.86。

真实模型仓库使用 `Prepare-OllamaModelStore.ps1` 生成，三个模型均经过Ollama下载
阶段的摘要校验。随后 `ollama_model_store.py` 验证三个固定manifest标签、8个引用
blob的存在性和大小：总计24,654,046,877字节。模型仓库是本地介质，不提交Git。

## 功能验收

```powershell
.venv\Scripts\python.exe scripts\windows\check_ollama_offline.py `
  --base-url http://127.0.0.1:11435 `
  --llm-model qwen3.5:27b-q4_K_M `
  --fallback-llm-model qwen3.5:9b-q4_K_M `
  --embedding-model qwen3-embedding:0.6b `
  --expected-version 0.32.15 `
  --timeout-seconds 600
```

检查项包括：本地服务可达、版本匹配、三个模型标签存在、27B生成、9B生成、
Embedding生成及向量维度。报告新增模型加载、总耗时、生成token数和生成速度，
便于区分冷加载时间与实际推理时间；不记录用户提示词或模型回答内容。

第一轮冷启动三链路总耗时99.53秒，三个HTTP接口均返回200。Ollama日志确认
Embedding的29/29层全部卸载到CUDA0，8192上下文和Flash Attention生效。27B、9B
及Embedding单次接口（含各自冷加载）的服务端耗时约60.0秒、23.1秒和15.7秒。

第二轮在操作系统文件缓存已经预热、但模型仍以 `keep_alive=0` 逐个卸载重载时，
结构化报告结果如下：

| 链路 | 加载 | 总耗时 | 生成速度/结果 |
| --- | ---: | ---: | --- |
| 27B生成 | 13.556秒 | 16.315秒 | 69.71 token/s |
| 9B生成 | 7.217秒 | 8.455秒 | 175.82 token/s |
| Embedding | 2.088秒 | 2.130秒 | 1024维向量 |

第二轮三链路总计27.08秒。产线验收必须同时记录系统首次启动和重复调用，不能用
文件缓存预热后的结果代替最差冷启动延迟。

## 边界

- 这是RTX 5090开发机验收结果，不能代替最终RTX 3090 24GB上的性能与显存验收。
- `OLLAMA_NO_CLOUD=1`已启用，但当前机器未物理断网；干净测试机的完全断网全新
  安装仍属于后续发布包验收。
- 生产默认保持单模型、单并发和8192上下文，只有RTX 3090实测通过后才调整。
