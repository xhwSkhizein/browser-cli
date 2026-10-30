# Browser CLI 面向 Agent 的迭代建议

审查日期：2026-10-28。依据 Agiwo 会话 `sess-261028131656-yt9` 的完整 RunLog，以及本机 `~/workspace/browser-cli` 当前源码。Browser CLI 的 HEAD 为 `b70aa9b167b4a54ed6cc2d52da6c202b3db7e1fa`，工作区另有未提交修改；下面的源码结论针对审查时的工作区，不等同于已发布版本。

这次任务需要列出抖音合集、保存每集下载地址、标题、时长和字幕信息。Agent 最后取得了 120 项，但为了操纵浏览器、处理异常和搬运数据，写了许多一次性 shell / JavaScript / Python 片段。最值得改进的是：让命令成功和失败都能被程序可靠读取，让同一标签页上的操作顺序明确，让大结果直接保存为完整文件。

## 证据与边界

- 会话共 42 次模型调用、48 次工具调用，运行约 12 分 7 秒；模型调用耗时累计约 11 分 19 秒。39 次工具调用走 `bash`，没有 Worker。
- 本次 Browser CLI 成功响应报告 `runtime_version=2026-10-22-capture-context-batch-v2`、`driver=extension`、`agent_id=public`。
- 下文的 `#63` 等编号指该会话 RunLog 的 `sequence`，不是第几次模型调用。
- 已用当前源码做无浏览器探针：CLI 错误输出、参数解析、失败 batch 的退出码、标签页锁冲突。探针替换了 daemon 连接，未启动 Chrome，也未重跑抖音抓取。
- 原始日志及探针输出在 Agiwo 的 `.agiwo-data/reviews/sess-261028131656-yt9/`，未随仓库提交。本文不包含 Cookie 值或带签名的下载地址。

## 一、优先修复成功与失败的输出契约

### 问题

`eval` 成功时输出 `ok/data/meta` JSON，失败时输出 `Error: ...` 文本到 stderr。Agent 将 `2>&1` 重定向到 `.json` 文件后，后续程序把错误文本当 JSON 解析，又产生一次异常和一轮模型修复。

本次 `#113` 的直接症状是 `JSONDecodeError`；`#117` 读回文件才发现原始原因是标签页忙。`#103` 的“没有活动标签页”也只有文本，外层 shell 还返回了 0。

当前源码中的无浏览器探针结果：

| 调用 | 观察结果 |
| --- | --- |
| `eval`，daemon 返回 BusyTabError | 退出 75，stdout 为空，stderr 为文本错误 |
| `eval '() => 1' --json` | 退出 2：不接受 `--json` |
| `batch` 返回 `ok:true, data.success:false` | CLI 退出 0，stdout 是步骤失败的 JSON |

batch 的最后一项是当前产品契约，不是本次轨迹出现的错误；但它意味着调用者不能只看退出码或顶层 `ok`。建议在引导 Agent 使用 batch 前先解决这层易错语义。

### 建议

1. 所有 JSON-first action 默认在成功和失败时都输出同形 JSON 到 stdout；stderr 留给诊断。若保留文本模式，显式选择文本模式。
2. action catalog 统一注册输出模式。若支持 `--json`，所有 action 的行为一致；不能只在 `read/status` 等手写命令中支持。
3. 错误保留 `error_code`、`message`、`meta.action`、`meta.agent_id`。失败时再附必要的恢复信息，避免每次成功都重复大段说明。
4. 保留 batch 的协议层 `ok` 与步骤层 `data.success`，在 CLI 对步骤失败返回非零退出码；同步调整契约测试和文档。
5. Python / Node 客户端也应提供容易发现的 batch 成功检查，不能把 `invoke()` 返回了字典当作任务成功。

可在失败响应中增加以下候选字段；这是设计建议，尚未实现：

```json
{
  "ok": false,
  "error_code": "AGENT_ACTIVE_TAB_BUSY",
  "message": "Active tab is busy",
  "execution_state": "not_started",
  "meta": {"action": "eval", "agent_id": "agent-a"},
  "blocked_by": {"command": "cookies", "request_id": "..."}
}
```

`not_started` 只用于确实没有执行页面操作的拒绝。超时、断连或操作后清理失败须保留结果不明，不能因此自动重放点击、提交或下载。

源码入口：`src/browser_cli/cli/main.py::build_parser/main`、`commands/action.py::run_action_command`、`outputs/json.py`、`daemon/client.py::_error_from_payload`、`task_runtime/client.py::batch`。

验收：对 `NO_ACTIVE_TAB`、`AGENT_ACTIVE_TAB_BUSY`、参数错误、daemon 错误、失败 batch 做完整 CLI 测试，核对 stdout 可解析、退出码非零及错误字段保留。不能只测 JSON 渲染函数。

## 二、让标签页冲突可诊断，先复用现有 batch

### 问题

`#113` 扫描字幕与 `#114` 导出 Cookie 来自同一个模型工具批，被 Agiwo 并行执行；两者争用同一活动标签页，扫描被拒绝。当前源码中 `_handle_eval` 和 `_handle_cookies` 都调用 `_run_active_page_action`，后者获取 `TabRegistry.claim_active_tab`。用当前 TabRegistry 也能离线复现该冲突。

Cookie 命令的帮助说明是读取共享 browser context，但它实际也要求活动标签页并独占该页。对 Agent 而言，这项前置条件很难从命令名和帮助推断。

当前 BusyState 已保存请求编号、命令、执行者和开始时间，但错误仅说“当前页正在被操作”；runtime status 对单页也主要暴露 `busy` 布尔值，调用者不知道谁在占用、等待多久、自己的请求是否已开始。

### 建议

- **立即可用的处理**：在同一个任务脚本里串行执行这些操作，或复用现有 `batch`。Agiwo 的同一浏览器控制流不要同时发多个独占页面操作。
- 在 action 元数据中声明执行作用域，例如“活动页独占”“上下文读取”“运行状态读取”。由同一份元数据生成帮助和可供客户端查询的能力目录。
- Busy 错误带上当前作用域内的阻塞命令、请求编号、开始时间，以及 `execution_state=not_started`。恢复信息只暴露本执行者有权查看的标签页。
- `cookies` 短期先明确“需要活动页且占用该页”。是否改为 context 级读取，应核对 extension 与 Playwright 的行为后再决定，不能只放开锁。
- 若后续需要等待锁，做有期限、可取消的显式选项；普通命令立即报 Busy 的现有行为可以保留。不要遇到 Busy 就自动新建标签页或重放整个 batch。

batch 已有按序执行、`--file`、`--result-mode all|last|summary` 和独占协调，无需重新发明一套事务/工作流。不过当前 batch 会阻止其他浏览器动作进入，应保持短小；它不提供副作用回滚。

源码入口：`daemon/app.py::_handle_eval/_handle_cookies/_run_active_page_action`、`tabs/registry.py::BusyState/claim_active_tab`、`daemon/browser_service.py::_serialize_tab_record`、`daemon/execution.py`、`actions/cli_specs.py`。

验收：同一作用域的并行调用能得到明确的执行前拒绝；同一个 batch 的 eval 与 Cookie 操作按序完成；取消和清理后锁被释放；不同执行者的标签页仍然隔离。

## 三、把 Agent 身份接线做成默认可见的事实

### 问题

本次成功响应全部使用 `agent_id=public`。Browser CLI 已支持 `X_AGENT_ID`，但 Agiwo 的 bash 子进程没有按会话和执行者注入这个值。其他使用默认身份的任务因此可能共享活动页状态。

`#103` 曾在先前调用成功后返回 `NO_ACTIVE_TAB`。现有轨迹没有足够的浏览器生命周期信息，无法断定是用户关页、外部调用、重绑定或其他原因；不能直接把它归咎于某个已知恢复 bug。

### 建议

- Agiwo 从真实 `ToolContext` 为浏览器调用注入稳定的 `X_AGENT_ID`，例如由 session 与 agent 身份组成；同一执行者跨 bash 调用保持一致。
- 不按每次工具调用生成新身份，否则下一条命令反而看不到上一条创建的标签页。
- 在机器使用说明和轻量能力摘要中突出该变量，以及“隔离标签页可见性，不隔离共享 Cookie/storage”的边界。
- 对落入默认身份的机器调用，可以返回一个紧凑的 fallback 标记；避免每次响应重复长警告，也不要破坏人的普通终端用法。
- `NO_ACTIVE_TAB` 明确区分“当前执行者无页”与 runtime 故障，保留已有 `state_reset` / transition 信息。已知目标的只读任务可由调用方决定重开；不要默认重启 daemon。

源码入口：`agent_scope/__init__.py::resolve_agent_id`、`tabs/registry.py`、`daemon/browser_service.py`。Agiwo 的接线入口是 `crates/agiwo-tools/src/builtin/bash.rs` 与 `process/runner.rs`，不是让模型手填身份。

验收：两个会话、Main 与 Worker 分别使用自己的标签页；相邻工具调用保持同一身份；runtime 重绑定仍报告已有 reset 事实。

## 四、提供“完整保存、紧凑返回”的数据出口

### 问题

`#63` 中 Agent 自己把 `RENDER_DATA` 切成 200,000 字符，然后尝试解析 JSON。原文其实有 208,339 字符，截断必然破坏结构。接下来又经过取全文、解码、找键等多轮调用，才发现其中没有需要的视频详情。

这是调用方截断造成的错误，不能算 Browser CLI 自己截坏了结果。但现有交互方式容易诱导 Agent 在 `slice()`、`head -c`、重定向和嵌套 JSON 之间手工拼接。

### 建议

优先复用现有 Python / Node 客户端：由本地任务脚本接收完整返回值、原子写文件、验证 JSON，再向 Agent 返回路径和业务摘要。Browser CLI 可进一步增加通用文件出口，建议包括：

- eval 从代码文件或 stdin 读取，减少三层引号转义。
- 将结果完整、原子地写到调用者指定文件；返回绝对路径、字节数、哈希和结果类型。
- JSON 导出保持完整结构，不能把截断后的 JSON 当作成功文件。若有上限，明确报错或返回完整文件引用。
- 文件写入放在客户端侧，沿用调用者的权限与路径；不要让 daemon 以自己的目录和身份随意写任意输出路径。
- 模型默认只收到统计、小样例和文件位置；正文和签名 URL 留在文件，按需读取。

这些是候选接口，不是当前已经存在的命令参数。先解决客户端脚本能稳定使用的路径，再判断是否值得增加公开 CLI surface。

源码入口：`actions/cli_specs.py::_add_eval_arguments`、`commands/action.py`、`outputs/json.py`、`task_runtime/client.py`、`task_runtime/node/client.mjs`。

验收：用超过 200 KB、包含中文和特殊字符的 fixture，比对保存文件与原始结果的哈希；写入失败、取消及不完整响应不得生成成功文件；模型摘要不包含完整 Cookie 值。

## 五、先改善浏览器内请求的示例，再决定是否增加 API

### 问题

外部 curl / yt-dlp 被风控，而页面上下文的 `fetch(..., {credentials:'include'})` 成功。本次可用路径其实已存在于 `eval`；Agiwo 的 `tools/capture/lib/douyin.py` 也已有 page-context fetch fallback。但脚本失败时只留下通用提示，Agent 随后重新探索了相同路线。

Agent 反复生成“请求接口 → 检查 HTTP → 读 JSON → 选字段 → 保存”的代码，分别拉列表和扫描字幕，浪费模型往返和网站请求。

### 建议

- 给网络型任务提供一段短的成功示例：检查 HTTP 状态、检查 JSON、保留业务状态、保存完整返回值、再输出需要的字段。
- 一次分页同时保留标题原文、时长、所选清晰度、下载候选地址、字幕候选字段和翻页事实，避免为遗漏字段重新扫全集。
- 先在站点任务/技能中实现分页、重试和字段语义；Douyin 的 mix、subtitle、水印判定不应进入通用 Browser CLI 内核。
- 多个真实任务证明重复后，再考虑通用的浏览器上下文 request / export helper。它应复用现有 daemon 和 driver，保留状态码、最终地址和数据来源；不承诺绕过 CORS、风控或自动解决 CDN 认证。
- CDN 下载的 Cookie、Referer、重定向和所选媒体流，应由下载适配层明确处理；“页面 fetch 成功”不等于“外部直链可下载”。

源码入口：`task_runtime/client.py::eval`、`drivers/_extension/page_actions.py`、`browser/service.py::evaluate`。站点逻辑入口为 Agiwo 的 `tools/capture/lib/douyin.py`。

验收：使用分页 fixture 验证 cursor、has_more、重复项、部分失败和字段缺失；不为这个通用 helper 增加固定的站点抓取流程。

## 六、帮助 Agent 选择能力，不要求先创建一套任务资产

现有能力已经包含 `batch`、Python / Node 客户端、文本等待、network 观察、verify 工具和恢复命令。本次 Agent 没有有效发现它们，反而主要靠零散命令和固定 sleep。

建议增加或整理一页很短的 Agent 快速入口：

1. `status --json` 检查已有 runtime，健康时复用；细查故障再用 doctor。
2. 需要交互与页面状态时使用 `open/eval`；内容一次性读取使用 `read`。
3. 同一活动页的依赖动作放进串行脚本或短 batch。
4. 等待已知文本、网络响应或已定义条件；固定 sleep 仅作有上限的兜底。
5. 大结果保存文件、返回摘要；读取错误码并核对 batch 的 `data.success`。

当前 explore / converge / delivery 技能主要围绕 `task.py`、`task.meta.json` 和可发布自动化。对一次性采集任务，可以增加轻量用法或简化适用范围：直接完成任务并保存必要文件，不把制作任务元数据和发布自动化作为前置要求。

当前 `status` 已有 daemon-owned presentation、恢复指引、binding 和 live probe 等改进，工作区还在修改相关代码。不要因为旧轨迹中的 doctor 摘要不足，就再建一份健康状态分类器。先让调用方复用当前状态源，并为常见机器任务提供紧凑投影。

源码入口：`commands/status.py`、`daemon/runtime_presentation.py`、`actions/cli_specs.py`、`packaged_skills/browser-cli-explore/SKILL.md`。

## 建议实施顺序

| 顺序 | 工作 | 用户收益 | 代价与边界 |
| --- | --- | --- | --- |
| 1 | 默认结构化错误、batch 失败退出码 | 消除“失败文本 → JSONDecodeError → 再询问模型” | 修改 CLI 契约及端到端测试 |
| 2 | Agiwo 注入身份，同页操作按序执行 | 减少活动页丢失和 Busy 重试 | 保留并行文件/计算任务；共享存储边界仍在 |
| 3 | 本地客户端完整导出、紧凑摘要 | 减少转义、截断和上下文膨胀 | 文件权限、原子写、取消均需验证 |
| 4 | 能力说明与 Busy 诊断 | 减少试命令与固定等待 | 只扩展已有状态事实，避免第二套状态机 |
| 5 | 在多个任务上验证通用 request helper | 减少重复浏览器请求样板 | 站点分页和业务判断留在任务适配层 |

本次未修改 Browser CLI 运行代码，也未验证新版 Chrome/extension 的线上行为。性能收益应在保留完整数据、证据范围和错误分支的前提下另行对照，不能由命令数减少直接推断。
