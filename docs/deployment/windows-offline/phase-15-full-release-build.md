# Windows 离线产线化：阶段 15 完整发布包组装

## 候选发布目录

2026-08-27在联网Windows准备机组装第一份完整候选发布目录：

- 发布版本：`0.8.1-dev-deploy-20260827`；
- 文件总数：323（发布清单记录322，清单文件不自引用）；
- 总大小：26,864,266,050字节；
- 关键哈希条目：29；
- 日志文件：0；
- SQLite/数据库文件：0。

该阶段的本地候选目录为 `.stage15-offline-release`，随后已由包含阶段16服务验收
修复的新候选包替换，所有大型发布物均不提交Git。发布目录包含：Python 3.11.9
安装器、VC++运行库、NSSM、Ollama及GPU运行库、
7个DB-GPT应用wheel、217个依赖wheel、三个Ollama模型、配置模板和全部安装运维
脚本。

## 组装命令

```powershell
.venv\Scripts\python.exe scripts\windows\offline_release.py build `
  --output D:\Releases\dbgpt-offline-0.8.1-prod1 `
  --release-version 0.8.1-prod1 `
  --python-installer D:\Build\runtime-media\runtime\python-installer.exe `
  --vc-redist D:\Build\runtime-media\runtime\vc-redist.x64.exe `
  --wheelhouse D:\Build\python-media\wheelhouse `
  --app-wheels D:\Build\python-media\app-wheels `
  --ollama-dir D:\Build\runtime-media\ollama `
  --models-dir D:\Build\ollama-models `
  --nssm-exe D:\Build\runtime-media\tools\nssm.exe
```

输出路径必须不存在，避免覆盖已有发布。组装只复制输入介质，不修改模型仓库。

## 已完成验收

1. Python介质生成：7个应用wheel、217个依赖wheel，Ollama Python客户端0.4.7。
2. 源Python介质：临时空环境 `--no-index` 安装成功，`pip check`无破损依赖，
   关键模块、CLI与静态Web自检通过。
3. 完整发布清单：PowerShell和Python校验均通过，322个记录文件无缺失、大小或
   关键哈希不一致。
4. 发布目录副本：再次从发布目录执行临时空环境 `--no-index` 安装，结果通过。
5. 模型仓库：三个固定标签、8个blob、24,654,046,877字节通过存在性和大小校验。

wheelhouse和模型只在介质制作/模型下载阶段做必要的内容读取或Ollama自身校验；
发布清单仍只哈希29个关键安装、应用、配置和脚本文件，没有扩大为全包哈希。

## 尚未完成的交付门槛

- 将完整目录复制到干净Windows 10/11 RTX 5090测试机，并在物理断网状态执行
  管理员全新安装；
- 注册并验证DB-GPT与Ollama Windows服务、开机启动、失败恢复、日志和备份恢复；
- 验证浏览器、数据库、文档、知识库、数据分析、定时任务和模型不可用提示；
- 最终在RTX 3090 24GB产线机复测模型显存/延迟、NTFS ACL、只读数据库拒写和
  一小时C++宿主并发读写。

因此本阶段结论是“完整候选介质已组装并在准备机验证”，不是“可直接投入产线”。
