# Windows 离线产线化：阶段 6 原生功能验收

## 已验证范围

本阶段验证项目现有能力，不增加文档、知识库或定时任务功能：

- 本地知识文档解析测试覆盖 TXT、Markdown、HTML、CSV、Excel、DOC/DOCX 和 PDF，共 11 项通过。
- 定时任务服务、DAO、接口、runner、调度器和恢复相关测试共 68 项通过。
- 会话文件检查和持久化测试覆盖格式识别、大小限制、目录边界、超时子进程和清理。
- 当前环境已具备 APScheduler、Chroma、pandas、openpyxl、python-docx、pypdf 和 pdfplumber；`unstructured` 未安装，不能把依赖它的可选解析路径纳入当前离线包能力。

## Windows兼容修正

- Windows对已退出PID可能返回 `WinError 87`，超时检查现在会正确识别为进程已经退出。
- 需要符号链接权限的安全测试在Windows账户没有该权限时明确跳过，而不是误报产品失败。
- POSIX `0600/0700`模式只在POSIX系统断言。Windows不使用这些模式表达安全边界，阶段7必须通过NTFS ACL限制服务运行目录和文件。

符号链接测试被跳过不代表对应攻击面已在Windows实测。目标机应禁用普通服务账户创建符号链接的权限，并验证上传和运行目录ACL。

## 自动化验收

```powershell
.venv\Scripts\python.exe -m pytest packages\dbgpt-ext\src\dbgpt_ext\rag\knowledge\tests -q
.venv\Scripts\python.exe -m pytest packages\dbgpt-serve\src\dbgpt_serve\scheduled_task\tests packages\dbgpt-core\src\dbgpt\util\scheduler\tests -q
.venv\Scripts\python.exe -m pytest packages\dbgpt-serve\src\dbgpt_serve\session_file\tests\test_inspector.py packages\dbgpt-serve\src\dbgpt_serve\session_file\tests\test_registry.py -q
```

## 尚未关闭的验收项

- 真实Ollama LLM和Embedding尚未到位，知识库入库、向量化、检索问答和定时模型任务不能做端到端验收。
- 当前测试使用小型本地样本，目标机仍需测试实际PDF、Word、Excel和CSV的格式、大小、中文路径及解析耗时。
- 电脑关机、错过触发、系统时间变化和真实模型超时需要在Windows服务化后执行。

因此，本阶段证明代码侧原生能力和Windows基础兼容性，但不把依赖真实模型和目标机服务生命周期的项目标记为已完成。
