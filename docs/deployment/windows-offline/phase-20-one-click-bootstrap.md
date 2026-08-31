# Windows离线一键安装

## 安装入口

目标机从移动介质运行`Install-DBGPT.cmd`。普通双击时安装器按需弹出UAC；从管理员
终端运行时直接继续，不因启动方式拒绝安装。

安装流程固定为五步：

1. 检查Windows x64、本地目标路径、磁盘空间和固定端口；
2. 校验离线介质清单；
3. 安装固定版本Python、DB-GPT和模型文件；
4. 安装并启动回环地址上的Ollama服务；
5. 真实调用27B、9B和Embedding模型。

完成后为安装用户创建“启动 DB-GPT”和“停止 DB-GPT”两个桌面快捷方式。安装器不
自动启动DB-GPT、不自动打开浏览器，也不把生产验收混入安装流程。

## 默认目录

```text
InstallRoot = C:\Program Files\HGTech\DB-GPT
DataRoot    = C:\ProgramData\HGTech\DB-GPT
ModelRoot   = C:\ProgramData\HGTech\OllamaModels
```

如需更换本地模型盘，在第一次安装前把`deployment-config.json`复制为同目录的
`deployment-config.local.json`，只修改local文件。发布清单仍校验原始默认配置。
应用、模型和可变数据不能长期放在移动介质上。

## 只保留的阻断条件

- 发布介质缺失、损坏或关键文件哈希不匹配；
- 目标不是Windows x64、本地固定磁盘或可用空间不足；
- 安装路径落在移动发布介质中；
- 5670或11434被不属于本安装的进程占用；
- 现有程序目录无法识别，继续操作可能覆盖其他文件；
- Python、Ollama服务或三个本地模型的真实验证失败。

网络连接状态不阻止安装。物理断网、DB-GPT Web健康、当前用户进程、RTX 3090性能、
真实C++写入并发、知识库和定时任务使用独立验收脚本完成，不影响安装结果。

## 重试与重启

安装脚本本身可重复执行。已通过Python和模型仓库自检的内容不会重复复制。VC++安装
要求重启时，通过当前用户的`HKCU RunOnce`在登录后继续，不强制重启电脑。

应用目录中的`.dbgpt-offline-installing.json`只用于确认未完成目录属于本发布包，避免
覆盖未知目录；不再维护额外的多阶段安装状态文件。

安装结果与日志：

```text
%ProgramData%\HGTech\DB-GPT\install\preflight.json
%ProgramData%\HGTech\DB-GPT\install\release-verification.json
%ProgramData%\HGTech\DB-GPT\install\model-validation.json
%ProgramData%\HGTech\DB-GPT\install\system-result.json
%LOCALAPPDATA%\HGTech\DB-GPT\Installer\setup-*.log
```

## 独立生产验收

安装完成后从桌面快捷方式启动DB-GPT，再运行`Test-DBGPTOfflineInstallation.ps1`完成
物理断网与完整功能验收。RTX 3090性能复测和真实C++写入一小时并发测试仍是投入生产
前的独立门槛。
