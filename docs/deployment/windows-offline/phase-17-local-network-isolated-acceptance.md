# Windows 离线产线化：阶段 17 本机远程安全断网验收

## 目标与边界

在不关闭物理网卡、不影响远程控制会话的前提下，只阻断候选包运行进程访问
Internet，保留浏览器、DB-GPT与Ollama之间的本机回环通信。本阶段可以验证离线
介质、服务和主要功能链路，但不能替代干净Windows系统或RTX 3090产线验收。

`Set-DBGPTProcessNetworkIsolation.ps1`只创建三个按可执行文件路径限定的出站阻断
规则：安装目录内的Python、Ollama和llama-server。规则的远端范围为Windows防火墙
的 `Internet` 动态地址关键字，不修改网卡、路由、DNS、全局出站策略或远程控制
软件。脚本支持 `Apply`、`Status`和 `Remove`，只操作三个固定名称的规则。

## 本机验收路径

本机使用以下独立目录，不覆盖源码、候选包或用户运行数据：

- 安装目录：`C:\HGTechOfflineAcceptance\DB-GPT`；
- 数据目录：`C:\HGTechOfflineAcceptance\Data`；
- 模型目录：`D:\HGTechOfflineAcceptance\OllamaModels`。

安装和服务注册必须在管理员PowerShell执行。应用进程隔离规则后，验收命令不使用
`-RequirePhysicalNetworkDisconnected`，而使用：

```powershell
powershell -ExecutionPolicy Bypass -File `
  "C:\HGTechOfflineAcceptance\DB-GPT\scripts\Test-DBGPTOfflineInstallation.ps1" `
  -InstallRoot "C:\HGTechOfflineAcceptance\DB-GPT" `
  -ModelRoot "D:\HGTechOfflineAcceptance\OllamaModels" `
  -RequireProcessNetworkIsolation
```

安装器先读取固定运行时版本并检查Windows已注册的VC++ x64运行库。已安装版本满足
要求时不会重复运行安装器；版本不足且VC++安装返回3010时，脚本在创建应用、数据
和模型目录前明确停止，要求重启Windows后重新执行，避免留下不可安全重跑的半安装
目录。

Windows PowerShell 5.1不使用 `Start-Process -Wait`等待VC++或Python安装器，因为该
参数可能继续等待已经完成安装后仍驻留的Windows Installer子进程。安装器改为获取
目标进程对象并调用 `WaitForExit()`，只等待直接启动的安装程序结束。

本机首次服务启动暴露了三个Windows安装问题：

- 模型ACL在递归移除继承后，manifest和blob文件成为空ACL；最终方案只在模型根目录
  设置Administrators、SYSTEM和NetworkService的受保护ACL，再把所有子项重置为
  继承根目录权限。NetworkService只有读取和执行权限；
- DB-GPT服务在GBK环境输出Unicode启动横幅时失败；服务环境固定
  `PYTHONUTF8=1`和 `PYTHONIOENCODING=utf-8`；
- 独立数据目录缺少Alembic模板，首次初始化找不到 `metadata\alembic\env.py`；发布包
  现在显式携带四个迁移模板文件，安装器复制到应用目录，服务注册时只补充数据目录
  中缺失的模板，不覆盖已有元数据库或迁移文件。

## 本机实测结果

2026-08-27在Windows 11构建 `10.0.26200`、RTX 5090上完成进程级隔离验收，未关闭
网卡，远程控制连接未受影响。结果文件为
`C:\HGTechOfflineAcceptance\Data\installation-acceptance.json`，全部检查通过：

- `HGTechDBGPT`与 `HGTechOllama`均作为Windows服务运行；
- Web健康接口和Ollama `0.32.15`仅通过 `127.0.0.1`访问；
- 三条按候选可执行文件路径限定的Internet出站阻断规则有效；
- 模型仓库包含3个固定标签、8个blob，共24,654,046,877字节；
- 27B主模型、9B备用模型真实生成成功，Embedding返回1024维向量；
- 首次冷启动实测：27B加载约142秒，9B加载约50秒，Embedding加载约15秒；模型加载
  后生成速度分别约48和166 token/s。该数据只用于RTX 5090测试机，不代表RTX 3090；
- 浏览器首页、数据库页和知识库页加载成功，控制台无错误，既有UI隐藏与品牌文案保持。

## 通过条件

- 三个进程级Internet阻断规则存在、启用且Windows防火墙配置文件均启用；
- 远程控制和物理网卡保持不变；
- Web与Ollama仅监听回环地址；
- 两个Windows服务正常运行；
- 三个固定模型的真实生成和Embedding检查通过；
- 浏览器首页、数据库和知识库页面可正常加载。

本阶段尚未执行文档导入、知识库检索、数据分析对话和定时任务完整业务操作；这些链路
仍属于后续一小时断网业务验收，不能因为页面可加载就判定已通过。

本阶段结果必须明确标记为“本机进程级隔离验收”，不能记录为物理断网或干净系统
验收。测试后可以保留规则继续作为本机离线边界，也可由管理员使用 `Remove`精确
移除，不影响其他防火墙规则。
