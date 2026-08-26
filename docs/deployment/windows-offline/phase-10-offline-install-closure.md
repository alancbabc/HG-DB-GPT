# Windows 离线产线化：阶段 10 离线安装闭环

## 实现范围

- 离线安装器在安装DB-GPT应用 wheels 时显式安装 `ollama`，不再假定wheel位于wheelhouse就会被自动安装。
- 发布构建在输入阶段检查 `ollama-*.whl`，缺失时立即失败。
- 新增安装后运行时自检，验证Python 3.11 x64、DB-GPT与Ollama模块、CLI及预构建静态Web；自检不访问网络。
- 发布清单记录全部文件路径和大小，只哈希关键安装文件。模型、wheelhouse、日志、缓存及普通运行数据不做重复内容哈希，发布目录中的运维说明文件不会导致校验失败。
- 运行数据备份改为路径、数量和大小检查，并对复制后的 `metadata/dbgpt.db` 执行SQLite `quick_check`；不再逐文件计算SHA-256。
- 既有版本1发布和备份清单仍可读取，避免破坏已有测试或备份恢复入口。

## 阶段验收

```powershell
.venv\Scripts\python.exe -m pytest tests\deployment -q
.venv\Scripts\python.exe -m ruff check scripts\windows tests\deployment
npm --prefix web run test:ui-visibility
```

真实Python安装、真实wheelhouse和完全断网安装属于后续阶段；本阶段使用假介质验证缺失依赖、关键文件变化、额外说明文件、PowerShell校验、备份完整性和恢复流程。

## 2026-08-26 验收结果

- `tests/deployment` 共14项通过。
- `scripts/windows` 与 `tests/deployment` Ruff检查通过。
- UI可见性4项测试通过。
- 安装、发布校验、备份和恢复PowerShell脚本语法解析通过。
- 当前开发环境除尚未安装的 `ollama` 外，其余运行时模块、DB-GPT CLI和静态Web自检通过；`ollama`必须在后续真实wheelhouse安装验收中关闭。
