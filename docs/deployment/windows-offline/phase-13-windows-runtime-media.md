# Windows 离线产线化：阶段 13 第三方运行时介质

## 固定版本

| 组件 | 固定版本 | 用途 |
| --- | --- | --- |
| Python x64 | 3.11.9 | DB-GPT离线运行时；Python 3.11最后一个传统Windows安装器版本 |
| Ollama Windows amd64 | 0.32.15 | 本地LLM与Embedding服务，独立ZIP包含GPU运行库 |
| NSSM win64 | 2.24-101-g897c7ad | 将DB-GPT和Ollama注册为Windows服务 |
| Microsoft Visual C++ x64 | 14.50.35719.0 | Windows本机依赖运行库 |

版本、官方URL、文件大小和SHA-256集中记录在
`scripts/windows/runtime-media.lock.json`。只校验这四个关键下载介质；不对模型、
wheelhouse、日志、缓存和运行数据增加逐文件哈希。

NSSM官网明确提示Windows 10 Creators Update及更新系统使用2.24-101或更新构建，
因此不采用存在服务启动问题的2.24稳定版。NSSM ZIP的SHA-1同时与官网公布的
`ca2f6782a05af85facf9b620e047b01271edd11d`一致。

## 联网准备机

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\Prepare-WindowsRuntimeMedia.ps1 `
  -DownloadsRoot D:\DBGPT-Build\runtime-downloads `
  -OutputRoot D:\DBGPT-Build\runtime-media `
  -PythonExe .venv\Scripts\python.exe
```

脚本只下载缺失文件，随后验证固定大小与SHA-256，解压64位NSSM和Ollama，检查
Python、VC++与Ollama的Authenticode签名，并检查Ollama/NSSM版本。已有但错误的
文件不会被静默覆盖，输出目录已存在时也会失败。

已提前下载介质时增加 `-SkipDownload`，可以在不联网的准备环境重复组装和验证。

## 发布与安装变化

- 发布构建新增必填参数 `--vc-redist`，并将其保存为
  `runtime/vc-redist.x64.exe`。
- 离线安装先静默安装VC++运行库，再安装Python和DB-GPT wheels。
- VC++返回0、1638（已有兼容版本）或3010（成功但需重启）时继续；其他退出码失败。
- Python、VC++、NSSM、Ollama文件仍由发布清单作为关键文件校验；没有扩大哈希范围。

## 真实介质验收（2026-08-27）

- Ollama ZIP：1,460,302,386字节；解压66个文件、1,943,414,544字节；
  `ollama.exe --version`报告0.32.15。
- Python安装器：26,216,840字节；产品版本3.11.9150.0；PSF签名有效。
- VC++安装器：18,558,944字节；产品版本14.50.35719.0；Microsoft签名有效。
- NSSM ZIP：415,458字节；官网SHA-1匹配；win64程序报告
  `2.24-101-g897c7ad`。

本阶段不在开发机安装系统级Python、VC++或注册Windows服务。最终的管理员安装、
服务启动、GPU驱动兼容和完全断网启动必须在干净RTX 5090 Windows测试机验收。
