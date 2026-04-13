# Browser CLI 技术债务与优化 TODO

## 问题记录

### runtime / task_runtime 功能漂移

**状态**: 待修复  
**优先级**: 中  
**发现时间**: 2026-04-13

#### 问题描述

`browser_cli.runtime` 和 `browser_cli.task_runtime` 两个模块出现功能漂移，导致 Python API 用户无法使用完整的 `read` 能力。

#### 具体表现

| 特性 | `runtime/ReadRunner` | `task_runtime/BrowserCliTaskClient` |
|------|---------------------|-------------------------------------|
| `read-page` action | ✅ 有 | ❌ **缺失** |
| ChromeEnvironment 发现 | ✅ 有 | ❌ **完全缺失** |
| fallback profile 处理 | ✅ 返回给调用者 | ❌ 不支持 |
| 使用场景 | CLI `read` 命令 | Python `task.py` 开发者 |

#### 根本原因

1. **遗留架构**: `read` 最初设计为独立的 one-shot CLI 命令，拥有自己的 orchestration 层 (`ReadRunner`)
2. **迭代遗漏**: 后续 `task_runtime` 成长为完整的浏览器控制客户端时，**遗漏了 `read_page`** 方法
3. **功能被困**: Chrome Environment 发现逻辑（daemon 未运行时自动发现 Chrome）被"困"在 `runtime` 模块，未暴露给 `task_runtime`

#### 影响

- Python 用户使用 `task_runtime` 时，只能用 `open()` + `snapshot()` 组合，与 CLI `read` 行为不一致
- 缺少 Chrome 环境自动发现，task 开发者在某些环境下可能遇到浏览器启动问题
- 代码重复风险：两个模块各自维护类似的逻辑

#### 相关代码

- `src/browser_cli/runtime/read_runner.py` - ReadRunner 实现，包含 Chrome 环境发现逻辑
- `src/browser_cli/task_runtime/client.py` - BrowserCliTaskClient，缺少 read_page
- `src/browser_cli/daemon/client.py` - send_command，被两者共用但 start_if_needed 行为不一致