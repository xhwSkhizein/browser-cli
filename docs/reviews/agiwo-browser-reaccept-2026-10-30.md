# Agiwo 浏览器联调复验报告（2026-10-30）

三组问题均已完成检查与实装验收。错误 JSON 和 batch 退出码在当前源码中已有修复，但本机实际安装版及常驻 daemon 尚未更新；取消后的自有页面清理存在独立缺陷，本次已修复。已安装本地构建并替换空闲 daemon，复用现有 Chrome 扩展完成两组 Agiwo 原始验收，均退出 0。

第 2 至 4 节记录的是提交 `bacc32d` 对应的实装现场；后续 CI / review 修复及源码验证见第 7 节。后续源码验证不替代或扩大原实装记录的适用范围。

## 1. 根因与修复位置

| 问题 | 本次检查结果 | 修复位置与行为 |
| --- | --- | --- |
| daemon-backed action 失败只有文本 | 旧安装版真实复现：新身份 `eval` 退出 75，stdout 为空，stderr 为 `Error: No active tab...`。当前源码已包含上一轮 JSON 修复。 | `src/browser_cli/cli/main.py`、`commands/action.py`、`outputs/json.py`、`errors.py` 和 daemon 错误响应。实际升级后 stdout 为单个完整 JSON；`NO_ACTIVE_TAB` / `AGENT_ACTIVE_TAB_BUSY` 保留 action、agent_id、request_id，退出 75，明确为 `not_started`；Busy 包含 `blocked_by`。本次进一步使 daemon 未明确分类的运行失败默认保留 `unknown`。 |
| batch 子步骤失败仍退出 0 | 旧安装版真实复现：子项 `TAB_NOT_FOUND`、`data.success=false`，进程仍退出 0。当前源码已有修复。 | `src/browser_cli/commands/action.py` 根据 `data.success` 返回 75。顶层 `ok=true` 仍表示请求已处理；`errors`、`failed_indices`、步骤索引和按 result-mode 保留的结果继续输出。 |
| 取消后页面仍 Busy，无法清理 | 关闭页面原先也要先取得普通操作占用，因此正在执行延迟 fetch 的页面会拒绝自己的清理请求。仅结束 CLI 或取消 Python 等待并不能证明浏览器操作停止。 | `tabs/registry.py::begin_close/check_claim`、`daemon/app.py::_handle_close_tab/_run_active_page_action`、`daemon/execution.py`、`daemon/browser_service.py`、`daemon/server.py`、`extension/session.py`。关闭先核验所有权并预留页面，允许中断该页的 Busy 操作；收到浏览器真实关闭确认后移除页面、取消并限时收尾对应 daemon 等待。迟到结果不能写回或恢复活动页；取消请求的响应及 artifact 缓冲被清理。 |

清理使用现有命令：以原 `X_AGENT_ID` 调用 `browser-cli close-tab PAGE_ID`，或使用 `close` 关闭该身份的活动页。无权访问的页面返回 `TAB_NOT_FOUND`。清理仍等待全局 stop / workspace rebuild，但可穿过普通页面操作与 batch 的执行等待；其他身份的独立页面保持并行。清理本身不启动浏览器、不重建工作区、不切换 driver。关闭失败或未获确认时，保留原操作的 Busy 占用，错误状态为 `unknown`。

相关回归位于 `tests/unit/test_owned_page_cancellation.py`、`tests/unit/test_extension_request_cancellation.py` 和 `tests/integration/test_capture_context_batch.py`。覆盖真实浏览器 fetch、客户端保留连接/提前断连、未确认关闭、迟到结果、batch 中断、跨身份隔离、缓冲清理及生命周期互斥。

## 2. 实际安装与运行版本

| 项目 | 升级前 | 本次验收时 |
| --- | --- | --- |
| CLI 安装路径 | `/Users/hongv/.local/bin/browser-cli` | 同一路径，实际 wheel 安装，未用源码命令代替 |
| Python 包版本 | `0.1.6.dev8` | `0.1.7.dev4`（本地构建） |
| daemon PID | `85550` | `31115` |
| daemon runtime | `2026-10-22-capture-context-batch-v2` | `2026-10-30-owned-page-cancel-v3` |
| 实际扩展报告版本 | `0.1.3` | `0.1.3`，复用已连接扩展 |
| 实际 driver | extension | extension |

源码工作分支为 `codex/owned-page-cancellation`。本次不修改扩展 JavaScript；已有扩展的关闭能力经实际联调验证。Python 与打包 Node 客户端的 runtime 标识同步升级，避免旧 daemon 继续被当成兼容实例。

安装命令退出 0：

```sh
uv tool install --force --reinstall-package browser-control-and-automation-cli --python 3.12 \
  /Users/hongv/workspace/browser-cli/dist/browser_control_and_automation_cli-0.1.7.dev4-py3-none-any.whl
```

wheel SHA-256：`ab135d2685af72ac7752313c3e2e05ee8ef251eae9d1a4427bd179d713f2c664`。

实际安装目录为 `/Users/hongv/.local/share/uv/tools/browser-control-and-automation-cli/lib/python3.12/site-packages/browser_cli`。核对 CLI 入口、action runner、daemon、tab registry、extension transport 和 Node package 共 7 个关键文件，内容均与当时已测源码一致；证据见 `installed-version-after.json`。

升级前确认 daemon 无登记页面、无 Busy、无运行命令。旧版的正常 stop 会关闭现有扩展工作区，因此本次部署仅终止经验证空闲的旧 daemon PID，并启动新安装包的服务监听，等待原扩展重连；未向 Chrome 发送 workspace-close，未启动替代浏览器。这是一次安装更新；取消修复本身不依赖 daemon reset。

升级前后及全部验收结束时，原工作区窗口均为 `946756413`，原有页面数均为 1。验收结束后 daemon 登记页面数为 0、Busy 数为 0，活动命令为空；测试自建页面已全部清理。`browser-cli status --json` 退出 0，状态 healthy，扩展实测探针 pass。

## 3. 源码回归

在 `/Users/hongv/workspace/browser-cli` 执行：

```sh
uv build --no-sources --clear
./scripts/check.sh
```

两项退出码均为 0。构建成功；检查包含 lint、Node 测试、Python 测试及仓库 guard：51 项 Node 测试通过，432 项 Python 测试通过，guard 为 ok，无跳过或取消。Python 回归包含真实浏览器集成用例，使用已固定的 Chrome Headless Shell，并通过宿主执行权限及启动检查后运行；不是仅靠 mock 得出结论。

日志：`artifacts/reaccept/20261030T051926Z-63a7de3f/source-build.log`、`source-check.log`。

## 4. 实际 CLI / daemon / 扩展联调

初次检查前已执行 `browser-cli status --json`。真实联调始终复用健康扩展，仅访问本地固定 fixture；两组报告均记录 `model_calls=0`。

Agiwo 在本次工作期间已将 `tools/capture/` 迁移到 `.agiwo/skills/capture-content/scripts/`，旧路径不再存在。实际运行迁移后的原脚本；未修改测试、断言或采集逻辑。运行前后核对该脚本目录中 23 个 Python 文件，哈希完全相同。

在 `/Users/hongv/workspace/agiwo-rs` 执行的实际命令：

```sh
python3 .agiwo/skills/capture-content/scripts/verify_browser_integration.py \
  --out .agiwo-data/browser-cli-reaccept/integration-20261030T053925Z-97696875
python3 .agiwo/skills/capture-content/scripts/verify_browser_lifecycle.py \
  --out .agiwo-data/browser-cli-reaccept/lifecycle-20261030T053925Z-97696875
```

| 验收 | 退出码 | 结果 | 耗时 |
| --- | --- | --- | --- |
| integration | 0 | 11/11，errors 为空 | 2.964 秒 |
| lifecycle | 0 | 6/6，errors 为空 | 1.743 秒 |

重点检查结果：

| 检查 | 结果 |
| --- | --- |
| `fresh_identity_no_active_tab` | true |
| `batch_failure_exit_nonzero` | true，实际退出 75 |
| `batch_failure_json` | true |
| `real_no_active_tab_recovery` | true |
| `cancel_stops_within_managed_grace` | true，SIGTERM 后约 0.091 秒退出 |
| `cancel_preserves_local_facts` | true，保留已采集 25 集 |
| `cancel_does_not_claim_complete` | true，状态 cancelled，子进程退出 130 |
| `cancel_releases_identity_lock` | true |
| `cancel_closes_owned_page` | true，无遗留 fixture 页 |

原始 Agiwo 报告：

- `/Users/hongv/workspace/agiwo-rs/.agiwo-data/browser-cli-reaccept/integration-20261030T053925Z-97696875/browser-report.json`
- `/Users/hongv/workspace/agiwo-rs/.agiwo-data/browser-cli-reaccept/lifecycle-20261030T053925Z-97696875/lifecycle-report.json`

额外运行 `python3 artifacts/reaccept/20261030T051926Z-63a7de3f/verify_installed_protocol.py`，退出 0，13/13 检查通过。该检查直接调用 PATH 中的真实安装命令，验证：无活动页与 Busy 错误均为单个 JSON、stderr 为空、退出 75；其他身份不能关闭该页；其他身份在长 fetch 期间仍可执行；关闭占用中的自有页约耗时 0.070 秒；被中断操作退出 75 并标记 unknown；`all/last/summary` 三种 batch 模式各自配合 stop/continue 时，六种组合均退出 75 且保留失败索引、错误及相应完成计数。

## 5. 明确保留的限制

CLI 退出或 socket 断连本身仍不等于远端取消。调用端应在其清理阶段，以同一执行身份显式关闭其自有页面；本次 Agiwo 原有 `Browser` 清理流程已能完成这一动作。

确认页面关闭可终止该页面中的 JavaScript / fetch，并释放该页操作占用，但不能撤销此前已发生的副作用，也不能保证已到达 HTTP 服务端的请求停止处理。关闭响应的 `interruption.execution_state` 因此保留 `unknown`；被中断请求可以返回 `OPERATION_CANCELLED` 或浏览器实际错误，例如本次扩展返回的 `EXTENSION_ACTION_FAILED`（frame removed），均不能据此自动重放。未确认关闭时不会只释放锁并宣称远端已终止。

本次没有修改 Agiwo 的提示词、工具集合、历史投影或前缀缓存，也没有执行模型调用或付费评测。Agiwo 目录仅新增验收产物及原脚本正常使用的运行锁文件。

## 6. 证据位置

本次原始证据目录：`/Users/hongv/workspace/browser-cli/artifacts/reaccept/20261030T051926Z-63a7de3f/`。该目录已加入忽略规则，包含本机运行细节，不随源码提交。

主要文件包括 `installed-contract-before.json`、`runtime-before-upgrade.json`、`installation.json`、`installed-version-after.json`、`installed-protocol.json`、`agiwo-acceptance.json`、两组 Agiwo 报告副本及 stdout/stderr、脚本前后哈希、`status-after-acceptance.json` 和 `cleanup-summary.json`。源码回归通过与实际安装联调通过分别以上述日志和真实报告为证。

## 7. CI / review 补充验证

PR #23 的 review 指出恢复命令重复维护错误提示映射，并为没有提示的错误输出 `next_action: null`。已删除命令层的重复映射，统一使用 `cli/error_hints.py`；新回归用例先复现了 recover 和 workspace 两条路径的问题，再确认无提示时省略该字段。PR #24 新增的 `EXTENSION_RUNTIME_UNHEALTHY` 提示也迁入统一入口，保留原有扩展恢复测试，并补充涉及函数的契约说明。

完整组合复核还发现：`BrowserService` 使用共享变量保存命令元数据，关闭页的并发请求会覆盖原 `eval` 的信息。新增用例复现后，改用每个异步任务独立的 `ContextVar` 保存元数据，保留 driver 切换诊断，生命周期计数仍在所有任务间共享。取消错误文案同时明确页面可能仅被预留清理，避免在浏览器关闭尚未确认时宣称已经关闭。

修复后的完整组合执行 `uv build --no-sources --clear` 和 `./scripts/check.sh`，均退出 0：434 项 Python 测试、51 项 Node 测试通过，lint 和 guard 通过。源码回归日志为 `/private/tmp/browser-cli-pr25-review-check.log`；PR #24 同步修复后的独立完整回归为 421 项 Python 测试通过。PR #23 的本地首次完整回归只有旧分支打包产物一致性检查失败，保留原验收包并重建该分支后，四项打包检查全部通过，其余 416 项已通过；远端最新提交的七项 CI 作业均成功。

这些补充不表示已重新安装本机常驻 CLI，也不表示重跑了第 4 节的 Agiwo 实装脚本。最终远端 CI 和 review 状态以 [PR #23](https://github.com/xhwSkhizein/browser-cli/pull/23)、[PR #24](https://github.com/xhwSkhizein/browser-cli/pull/24)、[PR #25](https://github.com/xhwSkhizein/browser-cli/pull/25) 为准。
