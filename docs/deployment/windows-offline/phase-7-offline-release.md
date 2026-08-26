# Windows 离线产线化：阶段 7 发布包与服务化

## 发布包构成

发布构建工具要求显式提供Python x64离线安装程序、完整wheelhouse、DB-GPT应用wheels、Ollama独立程序、本地模型目录和NSSM。工具不会联网，不接受缺失介质，也不会覆盖已有输出目录。

```powershell
.venv\Scripts\python.exe scripts\windows\offline_release.py build `
  --output D:\Releases\dbgpt-offline-0.8.1 `
  --release-version 0.8.1-prod1 `
  --python-installer D:\Inputs\python-installer.exe `
  --wheelhouse D:\Inputs\wheelhouse `
  --app-wheels D:\Inputs\app-wheels `
  --ollama-dir D:\Inputs\ollama `
  --models-dir D:\Inputs\models `
  --nssm-exe D:\Inputs\nssm.exe
```

输出的 `release-manifest.json` 记录全部文件路径和大小，只对安装器、应用 wheels、配置、脚本、Python、NSSM和Ollama入口程序等关键文件记录SHA-256。模型和wheelhouse不做重复内容哈希；其完整性由文件大小、安装/导入结果及后续运行时自检验证。在目标机安装前用Windows自带PowerShell执行一次必要校验：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\Test-OfflineRelease.ps1 `
  -ReleaseRoot D:\Releases\dbgpt-offline-0.8.1
```

关键文件缺失、大小变化或关键文件内容校验失败会导致非零退出码。运维人员附加的说明文件不会被当作发布包损坏。

校验成功后，在管理员PowerShell中执行离线安装。安装器拒绝覆盖已有程序目录，升级必须使用阶段8的备份和回滚流程：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\Install-DBGPTOffline.ps1 `
  -ReleaseRoot D:\Releases\dbgpt-offline-0.8.1 `
  -InstallRoot "C:\Program Files\HGTech\DB-GPT" `
  -DataRoot "C:\ProgramData\HGTech\DB-GPT" `
  -ModelRoot "D:\HGTech\OllamaModels"
```

安装器先执行必要发布校验，然后静默安装固定Python，使用 `--no-index` 从wheelhouse显式安装应用和 `ollama` Python包，并运行不联网的模块、CLI及静态Web自检。自检通过后复制Ollama、模型、配置和运维脚本。它不自动注册服务，也不接触生产数据库。

## 服务化边界

`Register-DBGPTServices.ps1`使用NSSM注册两个服务：

- `HGTechOllama` 使用 `NetworkService`，只监听 `127.0.0.1:11434`，对模型目录具有修改权限。
- `HGTechDBGPT` 使用 `LocalService`，依赖Ollama服务，对DB-GPT数据目录具有修改权限。

程序目录只授予两个账户读取和执行权限。生产数据库ACL不由脚本自动修改，防止安装器扩大生产目录权限；必须在明确真实路径后单独授予 `LocalService` 所需的最小读取权限，并验证主库、`-wal`、`-shm`和目录访问。

脚本检测到同名服务时会停止，不覆盖现有服务。实际注册必须在目标机管理员PowerShell中执行，开发机只进行语法和 `-WhatIf` 路径检查。注册命令示例：

```powershell
powershell -ExecutionPolicy Bypass -File `
  "C:\Program Files\HGTech\DB-GPT\scripts\Register-DBGPTServices.ps1" `
  -InstallRoot "C:\Program Files\HGTech\DB-GPT" `
  -DataRoot "C:\ProgramData\HGTech\DB-GPT" `
  -ModelRoot "D:\HGTech\OllamaModels" `
  -LlmModel "已离线注册的LLM名称" `
  -EmbeddingModel "已离线注册的Embedding名称"
```

## 仍需准备的真实介质

- 固定版本的Python Windows x64安装程序和必要VC运行库；
- 使用锁文件在联网构建机下载的完整Windows x64 wheelhouse，其中必须包含 `proxy_ollama`及可被安装器识别的 `ollama-*.whl`；
- 当前提交对应的全部DB-GPT wheels和预构建静态Web资源；
- Ollama独立Windows程序、NSSM和已校验模型文件；
- 目标模型的本地注册/导入说明。

不得把模型、机器密钥、生产数据库和目标机路径提交Git。

## 自动化验收

```powershell
.venv\Scripts\python.exe -m pytest tests\deployment\test_offline_release.py -q
.venv\Scripts\ruff.exe check scripts\windows\offline_release.py tests\deployment\test_offline_release.py
```

测试使用假介质完成组包、Python校验、PowerShell校验和篡改检测，不安装软件、不注册服务、不修改ACL。
