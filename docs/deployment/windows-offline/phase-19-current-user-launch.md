# Windows 离线产线化：阶段 19 当前用户桌面快捷方式启动

## 决策

用户最终确认恢复项目原有运行权限：DB-GPT不再注册为`LocalService` Windows服务，
不创建新账号或自动启动任务，而是由安装用户双击桌面快捷方式启动。Ollama继续以
`NetworkService` Windows服务运行。该决策取代此前固定使用`LocalService`和生产
数据库额外NTFS ACL的方案，但不改写阶段17和阶段18已经发生的历史验收事实。

SQLite连接器保持兼容：未选择`read_only`时使用原有普通`sqlite:///path`连接；选择
时仍可使用`mode=ro`和`query_only=ON`。SQL工具继续限制为单条只读SELECT/CTE，并
保留行数、输出、超时和并发限制。

## 实现

- `Register-DBGPTServices.ps1`只注册`HGTechOllama`，不再创建`HGTechDBGPT`服务；
- `Install-DBGPTDesktopShortcuts.ps1`为当前用户创建“启动 DB-GPT”和“停止 DB-GPT”
  两个快捷方式；
- `Start-DBGPT.ps1`设置固定模型、DataRoot、16384上下文、离线tokenizer和UTF-8环境，
  防止重复启动，记录PID，等待健康接口后打开本机页面；
- 加密密钥生成后保存到DataRoot并随运行数据备份，重启、升级和同用户恢复时保持稳定；
- `Stop-DBGPT.ps1`只停止PID记录且可执行文件属于当前安装目录的进程；
- `Backup-DBGPTData.ps1`在需要时停止当前用户进程，备份后恢复启动；
- `Restore-DBGPTData.ps1`不再写入`LocalService` ACL；
- `Test-DBGPTOfflineInstallation.ps1`验证Ollama服务、当前用户DB-GPT进程、旧服务未
  运行、回环监听、离线tokenizer和三个真实模型接口。

电脑重启后需要用户再次双击快捷方式，安装程序不创建登录任务或开机自启动项。

## 安全边界变化

DB-GPT的Python、Shell和文件系统工具继承当前Windows用户权限。`read_only`只能约束
通过SQLite连接器建立的连接，SQL校验只能约束SQL工具；二者都不能阻止Python或
Shell修改当前用户本来有权修改的数据库和其他文件。用户已明确接受这一恢复原项目
行为带来的剩余风险，验收报告不得继续宣称通过操作系统账号隔离实现生产数据库拒写。

## C++实时写入

当前示例数据库已确认处于WAL模式，`PRAGMA quick_check`为`ok`，存在`.db`、`-wal`和
`-shm`且能够并发打开查询。C++写入端继续负责WAL、事务和checkpoint；DB-GPT不得
改变journal mode。正式投产前仍需执行一小时真实C++写入与DB-GPT查询联合测试，验证
已提交数据可见、无持续锁等待、无读取错误、数据库完整且WAL不无界增长。

## 验收门槛

- PowerShell脚本语法、离线发布构建和部署单元测试通过；
- 在RTX 5090本机迁移现有安装，确认DB-GPT实际所有者为当前用户；
- 桌面快捷方式启动、停止、防重复启动和日志通过；
- Desktop路径SQLite普通连接和数据库问答通过；
- Web与Ollama仅监听回环，27B、9B、Embedding和tokenizer离线检查通过；
- 重建候选离线包并在干净物理断网Windows机器安装；
- 最终在RTX 3090完成16K上下文、性能和一小时业务链路验收。
