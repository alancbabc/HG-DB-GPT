# 从远程仓库制作 Windows 离线包

> 适用仓库：<https://github.com/alancbabc/HG-DB-GPT>  
> 当前基线：`dev_deploy`  
> 当前已验收发布：`offline-stage21.4` / `ab38e7ff`

## 1. 先说明结论

只拿到 Git 仓库地址，**不能单独生成完整离线包**。仓库包含应用源码、构建脚本、依赖锁和安装脚本，
但不会保存约 25 GiB 的模型、Python/VC++/Ollama/NSSM 安装介质、wheelhouse 和 tokenizer 缓存。

接手人制作新包时需要：

1. 本项目远程仓库；
2. 一台可以联网的 Windows x64 准备机；
3. 64 位 Python 3.11 和 `uv`；
4. 当前已验收的 Stage 21.4 离线包，优先复用其中固定运行时、模型和 tokenizer；
5. 足够磁盘空间，建议准备至少 80 GiB 临时空间。

生产目标机不负责组包，也不应联网下载依赖。所有下载、前端构建、wheel 构建和模型准备都在联网准备机完成。

## 2. 两种制作方式

### 2.1 推荐：复用 Stage 21.4 的大文件介质

适用于大多数应用代码、SQL、Agent、前端或安装脚本更新：

- 从仓库构建新的 DB-GPT 应用 wheels 和依赖 wheelhouse；
- 复用 Stage 21.4 中已经验收的 `runtime`、`ollama`、`models`、`tools/nssm.exe` 和
  `tiktoken-cache`；
- 组装到一个全新的版本目录，再执行完整校验和目标机验收。

优点是不用重复下载约 24.65 GB 模型，也不会因为同名 Ollama 标签后来变化而无意更换已验收模型。

### 2.2 完全重建

仅在以下情况需要：

- Python、VC++、Ollama 或 NSSM 固定版本发生变化；
- 三个模型标签或实际模型内容需要升级；
- Stage 21.4 原始离线包已经丢失或损坏；
- 需要从零验证整个供应链。

完全重建仍建议从 Stage 21.4 复用那个约 1.6 MB 的 `cl100k_base` tokenizer 缓存；当前仓库会校验它，
但没有把该缓存提交到 Git。

## 3. 准备机要求

- Windows 10/11 x64；
- Git；
- Python 3.11 x64，用于执行介质构建脚本；
- `uv` 已安装并在 `PATH` 中；
- 能访问 GitHub、Python 包索引、Ollama 模型库和运行时下载地址；
- PowerShell 5.1 或更新版本；
- 如果修改了前端：还需要 Node.js、Yarn 和 Git Bash；
- 构建期间不要使用生产数据库、生产密钥或生产运行数据。

目标包安装的 Python 固定为 3.11.9。准备机执行构建脚本的 Python 可以是其他 3.11.x，
但必须是 64 位 Windows Python，不能使用 3.10、3.12 或 32 位解释器。

## 4. 获取源码并确定构建点

在联网准备机执行：

```powershell
git clone https://github.com/alancbabc/HG-DB-GPT.git
Set-Location HG-DB-GPT
git checkout dev_deploy
git pull --ff-only origin dev_deploy
git status --short
```

制作新版本时，`git status --short` 应为空。记录源码提交：

```powershell
$BuildSourceCommit = git rev-parse HEAD
$BuildSourceCommit
```

如果目的是重新制作 Stage 21.4 的同功能版本，而不是包含后续改动的新版本，则使用：

```powershell
git checkout offline-stage21.4
git rev-parse HEAD
```

输出必须是：

```text
ab38e7ff2a344aed818b4301a2a368cd19cfdf37
```

重新构建只能保证功能和输入版本一致，不保证整个目录逐字节一致。wheel 构建时间、上游下载响应和同名
模型标签都可能影响二进制结果；因此新生成目录必须使用新版本号并重新验收，不能冒充原 Stage 21.4。

## 5. 前端改动时先重建静态资源

生产目标机不安装 Node.js。前端静态文件必须在准备机提前构建，并随 `dbgpt-app` wheel 交付。

如果本次没有修改 `web`，可以直接使用仓库已经提交的
`packages/dbgpt-app/src/dbgpt_app/static/web`，跳过本节。

如果修改了前端或 `web/public/ui-visibility.json`：

```powershell
npm --prefix web run sync:ui-visibility
npm --prefix web run test
```

然后在 Git Bash 中从仓库根目录运行：

```bash
bash scripts/build_web_static.sh
```

该脚本构建 `web/out`，并替换 `packages/dbgpt-app/src/dbgpt_app/static/web`。构建结束后检查 Git diff，
将前端源码和对应静态文件一起提交。不要只提交 `web` 源码而遗漏 Python 包中的静态资源。

## 6. 设置本次构建目录

以下路径只是示例，可以换成准备机上的其他本地固定磁盘。所有输出路径必须是不存在的新目录：

```powershell
$DBGPTBuildRoot = "D:\DBGPT-Build\stage22"
$DBGPTPythonMedia = Join-Path $DBGPTBuildRoot "python-media"
$DBGPTDownloads = Join-Path $DBGPTBuildRoot "runtime-downloads"
$DBGPTRuntimeMedia = Join-Path $DBGPTBuildRoot "runtime-media"
$DBGPTModels = Join-Path $DBGPTBuildRoot "ollama-models"
$DBGPTReleaseRoot = "D:\DBGPT-Releases\DBGPT-Offline-Stage22"
$DBGPTBuilderPython = (Get-Command python).Source
```

先确认准备机 Python：

```powershell
& $DBGPTBuilderPython -c "import platform,sys; print(sys.version); print(platform.architecture())"
uv --version
```

## 7. 构建 Python 离线介质

在仓库根目录执行：

```powershell
& $DBGPTBuilderPython scripts\windows\offline_media.py prepare `
  --output $DBGPTPythonMedia `
  --uv-executable uv
```

该命令会：

- 构建 7 个 DB-GPT workspace wheel；
- 从当前 `uv.lock` 导出锁定依赖；
- 下载或在准备机预构建 Windows CPython 3.11 wheels；
- 显式加入锁定版本的 Ollama Python 客户端；
- 拒绝把 sdist 留给断网目标机现场编译。

完成后先做静态校验：

```powershell
& $DBGPTBuilderPython scripts\windows\offline_media.py verify $DBGPTPythonMedia
```

再创建一个全新临时环境进行真实 `--no-index` 安装：

```powershell
powershell -ExecutionPolicy Bypass -File `
  scripts\windows\Test-OfflinePythonMedia.ps1 `
  -MediaRoot $DBGPTPythonMedia `
  -PythonExe $DBGPTBuilderPython
```

只有看到 `Offline Python media installation passed.` 才能进入组包步骤。

## 8. 准备固定运行时和模型

### 8.1 推荐复用已验收 Stage 21.4

假设收到的旧离线包位于：

```powershell
$DBGPTBaselineRelease = "D:\Received\DBGPT-Offline-Stage21"
```

先使用当前仓库脚本校验旧包：

```powershell
powershell -ExecutionPolicy Bypass -File `
  scripts\windows\Test-OfflineRelease.ps1 `
  -ReleaseRoot $DBGPTBaselineRelease
```

校验通过后，后续组包直接使用这些输入：

```text
<旧包>\runtime\python-installer.exe
<旧包>\runtime\vc-redist.x64.exe
<旧包>\ollama\
<旧包>\models\
<旧包>\tools\nssm.exe
<旧包>\tiktoken-cache\9b5ad71b2ce5302211f9c61530b329a4922fc6a4
```

tokenizer 文件的预期 SHA-256 是：

```text
223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7
```

可以独立核对：

```powershell
Get-FileHash -Algorithm SHA256 `
  (Join-Path $DBGPTBaselineRelease `
    "tiktoken-cache\9b5ad71b2ce5302211f9c61530b329a4922fc6a4")
```

### 8.2 完全重建固定运行时

如果不能复用旧包，执行：

```powershell
powershell -ExecutionPolicy Bypass -File `
  scripts\windows\Prepare-WindowsRuntimeMedia.ps1 `
  -DownloadsRoot $DBGPTDownloads `
  -OutputRoot $DBGPTRuntimeMedia `
  -PythonExe $DBGPTBuilderPython
```

脚本根据 `scripts/windows/runtime-media.lock.json` 下载并校验固定版本、文件大小、SHA-256、
Authenticode 签名和程序版本。`OutputRoot` 已存在时会拒绝覆盖。

随后下载三个固定 Ollama 模型：

```powershell
powershell -ExecutionPolicy Bypass -File `
  scripts\windows\Prepare-OllamaModelStore.ps1 `
  -OllamaExe (Join-Path $DBGPTRuntimeMedia "ollama\ollama.exe") `
  -ModelsRoot $DBGPTModels `
  -PythonExe $DBGPTBuilderPython
```

脚本在独立回环端口启动临时 Ollama，下载以下模型并验证原生 `manifests`/`blobs`：

- `qwen3.5:27b-q4_K_M`
- `qwen3.5:9b-q4_K_M`
- `qwen3-embedding:0.6b`

准备目录必须不存在，端口 11435 必须可用。模型约 24.65 GB，下载时间取决于网络。

## 9. 组装新离线包

先确定新版本号。示例：

```powershell
$DBGPTReleaseVersion = "0.8.1-dev-deploy-20260901-stage22.0"
```

版本号必须是新的，不要复用 `stage21.4`。如果当前提交已有且仅有一个准备发布的 Git 标签，可以把它
写入 `sourceTag`；没有标签时先只记录 `sourceCommit`，不要填写不存在的标签。

### 9.1 使用 Stage 21.4 固定介质组包

```powershell
& $DBGPTBuilderPython scripts\windows\offline_release.py build `
  --output $DBGPTReleaseRoot `
  --release-version $DBGPTReleaseVersion `
  --source-commit $BuildSourceCommit `
  --python-installer (Join-Path $DBGPTBaselineRelease "runtime\python-installer.exe") `
  --vc-redist (Join-Path $DBGPTBaselineRelease "runtime\vc-redist.x64.exe") `
  --wheelhouse (Join-Path $DBGPTPythonMedia "wheelhouse") `
  --app-wheels (Join-Path $DBGPTPythonMedia "app-wheels") `
  --ollama-dir (Join-Path $DBGPTBaselineRelease "ollama") `
  --models-dir (Join-Path $DBGPTBaselineRelease "models") `
  --nssm-exe (Join-Path $DBGPTBaselineRelease "tools\nssm.exe") `
  --tiktoken-cache-file (Join-Path $DBGPTBaselineRelease `
    "tiktoken-cache\9b5ad71b2ce5302211f9c61530b329a4922fc6a4")
```

### 9.2 使用完全重建介质组包

```powershell
& $DBGPTBuilderPython scripts\windows\offline_release.py build `
  --output $DBGPTReleaseRoot `
  --release-version $DBGPTReleaseVersion `
  --source-commit $BuildSourceCommit `
  --python-installer (Join-Path $DBGPTRuntimeMedia "runtime\python-installer.exe") `
  --vc-redist (Join-Path $DBGPTRuntimeMedia "runtime\vc-redist.x64.exe") `
  --wheelhouse (Join-Path $DBGPTPythonMedia "wheelhouse") `
  --app-wheels (Join-Path $DBGPTPythonMedia "app-wheels") `
  --ollama-dir (Join-Path $DBGPTRuntimeMedia "ollama") `
  --models-dir $DBGPTModels `
  --nssm-exe (Join-Path $DBGPTRuntimeMedia "tools\nssm.exe") `
  --tiktoken-cache-file (Join-Path $DBGPTBaselineRelease `
    "tiktoken-cache\9b5ad71b2ce5302211f9c61530b329a4922fc6a4")
```

`offline_release.py` 要求输出目录不存在。它不会覆盖旧包，也不会自动删除失败前已有的正式目录。

## 10. 组包后必须完成的三层校验

### 10.1 Python 清单校验

```powershell
& $DBGPTBuilderPython scripts\windows\offline_release.py verify $DBGPTReleaseRoot
```

### 10.2 Windows PowerShell 清单校验

```powershell
powershell -ExecutionPolicy Bypass -File `
  scripts\windows\Test-OfflineRelease.ps1 `
  -ReleaseRoot $DBGPTReleaseRoot
```

### 10.3 从最终发布目录重新安装 Python

```powershell
powershell -ExecutionPolicy Bypass -File `
  scripts\windows\Test-OfflinePythonMedia.ps1 `
  -MediaRoot $DBGPTReleaseRoot `
  -PythonExe $DBGPTBuilderPython
```

三项都必须返回成功。随后检查：

```powershell
Get-Content (Join-Path $DBGPTReleaseRoot "release-manifest.json") -TotalCount 15
Get-ChildItem $DBGPTReleaseRoot
```

确认至少存在：

```text
Install-DBGPT.cmd
deployment-config.json
release-manifest.json
app-wheels/
wheelhouse/
runtime/
ollama/
models/
tiktoken-cache/
scripts/
```

## 11. 复制到移动硬盘后再次校验

把整个 `$DBGPTReleaseRoot` 复制到移动硬盘的新目录。复制完成后，不要只比较资源管理器中的文件夹大小，
应在移动硬盘副本上再次运行：

```powershell
powershell -ExecutionPolicy Bypass -File `
  scripts\windows\Test-OfflineRelease.ps1 `
  -ReleaseRoot "E:\DBGPT-Offline-Stage22"
```

盘符只是示例。验证成功后正常弹出移动硬盘，避免再次出现 Windows 扫描修复或文件未写完的问题。

## 12. 目标机验收和发布标签

移动介质校验通过不等于发布完成。至少还要：

1. 在目标机运行 `Install-DBGPT.cmd`；
2. 从桌面快捷方式启动 DB-GPT；
3. 运行 `Test-DBGPTOfflineInstallation.ps1`；
4. 验证 27B、9B、Embedding、tokenizer、Web 和回环监听；
5. 验证测试数据库、文档、知识库、报告和定时任务；
6. 最终在 Windows 10 + RTX 3090 上复测显存、冷启动、响应时间和稳定性；
7. 取得 C++ 写入程序后完成一小时并发读写测试。

验收通过后，确认发布提交已经推送，再创建并推送不可变标签。示例：

```powershell
git tag -a offline-stage22.0 $BuildSourceCommit -m "DB-GPT Windows offline Stage 22.0"
git push origin dev_deploy
git push origin offline-stage22.0
```

如果发布清单需要在组包时就包含 `sourceTag`，应先在本地让该标签指向 `$BuildSourceCommit`，组包时增加
`--source-tag offline-stage22.0`；只有验收通过后才推送标签。发布失败时不要把候选标签推到远程。

## 13. 哪些改动要求重新准备哪些内容

| 变更 | 必须重做 |
| --- | --- |
| 仅 Markdown 文档 | 通常无需重做离线包 |
| Python/Agent/SQL/安装脚本 | Python 介质、完整组包、清单和目标机验收 |
| 前端源码/可见性/品牌 | 前端静态构建、Python 介质、完整组包和 UI 验收 |
| `uv.lock` 或 Python 依赖 | 完整 wheelhouse、`--no-index` 安装测试和完整组包 |
| Python/VC++/Ollama/NSSM 版本 | runtime lock、运行时介质、完整组包和干净机安装 |
| 模型标签/量化/上下文策略 | 模型仓库、模型接口、GPU 性能和完整组包 |
| tokenizer 策略 | tokenizer 介质、哈希、离线加载和完整组包 |

## 14. 常见失败原因

- 在 Linux、macOS、32 位 Python 或 Python 3.12 上运行 `offline_media.py prepare`；
- 工作区有未提交改动，导致清单提交号无法对应实际内容；
- 只修改前端源码，没有更新 `dbgpt-app/static/web`；
- 输出目录已经存在；
- wheelhouse 中混入 sdist，目标机被迫现场编译；
- 忘记包含 Ollama Python wheel；
- tokenizer 文件名或 SHA-256 不匹配；
- Ollama 临时端口 11435 被占用；
- 同名模型标签后续发生变化，却没有重新做 5090/3090 验收；
- 移动硬盘复制后未重新校验或未安全弹出；
- 把“准备机校验通过”误写成“目标生产机验收通过”。

出现失败时应修正输入并使用新的输出目录重新构建，不要直接修改已经生成的发布目录后继续沿用旧清单。
