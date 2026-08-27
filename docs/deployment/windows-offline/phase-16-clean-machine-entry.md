# Windows 离线产线化：阶段 16 干净测试机执行入口

## 本阶段改动

- 服务注册的每个NSSM、`sc.exe`和`icacls`调用都检查原生退出码；任一步失败立即
  停止，不再误报注册完成。
- Ollama的 `NetworkService` 对固定模型仓库只保留读取和执行权限。脚本移除模型
  目录的宽泛继承，并保留Administrators和SYSTEM完全控制；模型更新必须由管理员
  在停止服务后离线完成。
- 新增 `Test-DBGPTOfflineInstallation.ps1`，用于目标机统一验证服务、物理断网、
  回环监听、Web健康、模型仓库和三模型真实接口。

生产数据库ACL仍不由安装或服务注册脚本自动修改。必须在已确认真实路径后单独
配置 `LocalService` 对数据库、`-wal`、`-shm`和目录所需的最小读取权限。

## 干净机执行顺序

将完整发布目录复制到本地磁盘，拔掉网线并禁用Wi-Fi，然后打开管理员PowerShell。

```powershell
$release = "D:\OfflineMedia\dbgpt-offline-0.8.1-prod1"
$install = "C:\Program Files\HGTech\DB-GPT"
$data = "C:\ProgramData\HGTech\DB-GPT"
$models = "D:\HGTech\OllamaModels"

powershell -ExecutionPolicy Bypass -File "$release\scripts\Test-OfflineRelease.ps1" `
  -ReleaseRoot $release

powershell -ExecutionPolicy Bypass -File "$release\scripts\Install-DBGPTOffline.ps1" `
  -ReleaseRoot $release -InstallRoot $install -DataRoot $data -ModelRoot $models

powershell -ExecutionPolicy Bypass -File "$install\scripts\Register-DBGPTServices.ps1" `
  -InstallRoot $install -DataRoot $data -ModelRoot $models

Start-Service HGTechOllama
Start-Service HGTechDBGPT

powershell -ExecutionPolicy Bypass -File `
  "$install\scripts\Test-DBGPTOfflineInstallation.ps1" `
  -InstallRoot $install -ModelRoot $models `
  -RequirePhysicalNetworkDisconnected | Tee-Object `
  -FilePath "$data\installation-acceptance.json"
```

验收脚本在服务缺失或停止时快速失败，不会为每个停止的服务等待10分钟。服务运行
后，它等待本机端点就绪，并确认5670和11434没有监听到非回环地址。严格断网模式
要求所有物理网卡均不是 `Up` 状态；虚拟回环和软件适配器不计入。

## 通过条件

- `HGTechOllama`和`HGTechDBGPT`均为Running；
- 物理网卡断开，Web和Ollama只监听127.0.0.1/`::1`；
- Web `/api/health`成功；
- Ollama版本0.32.15，三个固定模型存在；
- 27B、9B分别生成非空结果，Embedding返回非空向量；
- 模型仓库的三个manifest和8个引用blob仍完整；
- 报告 `success` 为true且进程退出码为0。

本阶段只交付目标机执行入口并完成模拟失败路径、PowerShell语法和部署自动化测试。
实际系统级安装、服务账户运行和物理断网结果必须从干净RTX 5090测试机回传，不能
在当前已有开发依赖和缓存的准备机上替代。

## 最新候选介质

包含本阶段修改的 `.stage16-offline-release` 已在准备机重建并通过独立清单校验：

- 版本：`0.8.1-dev-deploy-20260827-stage16`；
- 324个文件、总计26,864,273,523字节；
- 清单记录323个文件，其中30个关键文件带哈希；
- 已包含 `Test-DBGPTOfflineInstallation.ps1`；
- 日志文件和数据库文件均为0。

阶段15旧临时候选目录已删除并由该目录替代，模型源仓库和Python介质仍独立保留。
