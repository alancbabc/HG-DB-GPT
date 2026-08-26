# Windows 离线产线化：阶段 11 Python 离线介质

## 阶段目标

在联网的 Windows x64 准备机上，从当前提交和 `uv.lock` 生成可供 Python
3.11 目标机安装的完整应用 wheels 与依赖 wheelhouse，并在全新临时虚拟环境中
关闭包索引完成一次真实安装。介质生成不下载模型，不包含生产数据库、机器配置或
运行数据。

## 介质准备

使用 64 位 Python 3.11 执行：

```powershell
python scripts\windows\offline_media.py prepare `
  --output D:\Inputs\dbgpt-python-media
```

工具执行以下动作：

1. 分别构建 `dbgpt`、`dbgpt-acc-auto`、`dbgpt-app`、`dbgpt-client`、
   `dbgpt-ext`、`dbgpt-sandbox` 和 `dbgpt-serve` 七个应用 wheel；
2. 从当前 `uv.lock` 导出 `dbgpt-app` 的外部依赖，并追加同一锁文件中的
   Ollama Python 客户端固定版本；
3. 在联网准备机将依赖统一构建或下载为 wheel；目标机不安装编译器，也不接收
   sdist；
4. 生成只记录路径、大小和目标平台的 `python-media-manifest.json`，不对
   wheelhouse 重复计算哈希；
5. 原子生成输出目录，失败时清理未完成的暂存目录，不覆盖现有介质。

静态复核命令：

```powershell
python scripts\windows\offline_media.py verify D:\Inputs\dbgpt-python-media
```

## 真实断网安装冒烟测试

准备机下载结束后，执行以下命令。测试创建一个全新临时虚拟环境，只允许从本地
wheelhouse 安装，随后执行 `pip check` 和已安装运行环境自检，最后删除临时环境：

```powershell
powershell -ExecutionPolicy Bypass -File `
  scripts\windows\Test-OfflinePythonMedia.ps1 `
  -MediaRoot D:\Inputs\dbgpt-python-media `
  -PythonExe C:\Python311\python.exe
```

## 2026-08-26 验收结果

- 第一次真实生成发现 `pypika==0.48.9` 没有可直接下载的 Windows wheel；现改为
  仅在联网准备机预构建该纯 Python 包，最终 wheelhouse 仍只包含 `.whl`；
- 实际生成 7 个 DB-GPT 应用 wheel 和 217 个依赖 wheel；
- Python 介质共 227 个文件、221,587,318 字节；
- `uv.lock` 中实际固定的 Ollama Python 客户端为 `0.4.7`；
- 使用 Python 3.11.14 x64 创建全新临时环境，`--no-index` 安装成功；
- `ollama`、DB-GPT、Chroma、SQLAlchemy、文档解析等必需模块导入成功，
  DB-GPT CLI 和预构建静态 Web 自检成功。

本阶段证明当前提交的 Python 介质可以在同一台 Windows 准备机上断网安装，不能
替代 RTX 5090 干净 Windows 测试机的全新系统安装。Python 安装程序、Ollama
程序、NSSM、模型文件和系统运行库仍需作为发布包的其他输入准备。
