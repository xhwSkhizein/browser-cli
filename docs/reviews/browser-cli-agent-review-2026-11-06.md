# 多步骤优化改动复审与修复

日期：2026-11-06。复审范围是工作区中上一轮尚未提交的改动，重点为快照筛选/截断、scope 与 interactive 的组合，以及部分执行状态。本次直接修复发现的问题并补回归；没有提交、推送或发布，也没有开展真实 Agent 性能实验或真实站点操作。

## 发现并修复的问题

| 问题 | 可复现的错误行为 | 修复 |
| --- | --- | --- |
| P1：scope 在 interactive 之后解析 | 完整快照中的 `main` 仍存在，`snapshot -i --scope REF` 却先将其移除，误报 `STALE_SNAPSHOT`；interactive 的扁平树还会丢失范围和角色筛选所需的层级。 | 区域/角色与 interactive 组合时先取得完整结构，确定范围和子树，再筛交互元素及祖先上下文，最后截断。真实存在但没有交互元素的区域返回空匹配，不报失效。普通 `-i` 与仅精简的 `-i --compact` 保持原表示。 |
| P1：从显示文本猜测引用归属 | 含引号的正文可能出现在树中却从 `refs_summary` 消失；进一步构造同角色、同名称前缀及另一真实 `[ref=…]` 的文字，可以让范围选到伪造行。仅匹配完整前缀仍不足以解决这种歧义。 | 统一生成器内部记录 `SemanticSnapshot.line_refs`。筛选、范围选择和截断携带每行真实引用，不再从页面文字推断身份。缺失或矛盾的来源记录会拒绝投影；这些内部记录不进入公共响应，也不改变引用编号或默认树文本。 |
| P1：多字段填写的提交阶段越过旧页面 | 最后一个 input 事件改变 URL 后，`fill-form --submit` 仍可能在新页面按 Enter；如果字段已填、提交子步骤报 `not_started`，整步也会错误地继承该状态。 | 提交前重新验证原页面引用。前面只要已有字段成功，后续字段或提交拒绝就保留 `execution_state=unknown`。不会在已改变 URL 的页面按 Enter，不自动重放已填字段。 |
| P1：成功动作被收尾错误误报为未执行 | 浏览器动作已返回成功，`end_command` 再抛一个带 `not_started` 的错误时，batch 将该步骤误报为未执行，可能诱使调用方重放写操作。 | 独立记录动作是否已成功返回。此后的收尾/响应处理失败使用 `execution_state=completed`，仍保留失败响应和原错误码，batch 默认停止后续步骤。 |
| P1：二次收尾错误覆盖原失败或取消 | 部分动作失败之后，收尾再失败会逃出步骤执行器，丢失 batch 的失败索引和计数；原取消也可能被普通收尾错误替换。 | 原动作失败时保留原错误和已记录的步骤进度，以 `meta.cleanup_failed` 标记附加收尾失败。取消信号继续上抛，沿用原有 `unknown` 返回，不被收尾异常替换，也不保证能取回完整进度。收尾只调用一次，不重试，不重放浏览器操作。日志仅新增 action 和异常类型，不记录请求参数。 |
| P2：客户端把任意 view 对象当作筛选已生效 | daemon 返回 `view` 对象却回报不同的 role/scope/行数上限，客户端仍接受未按要求筛选的数据；截断标记与计数矛盾也未被发现。 | Python 和 Node 客户端核对所请求参数；显式行数限制还须满足返回行数、匹配行数与截断布尔值一致。不一致时返回现有 `DAEMON_INCOMPATIBLE`，不把未筛选树放进错误摘要、不重放；batch 保留进度且使用 `unknown`。 |

关键代码：

- `src/browser_cli/refs/generator.py:236`、`refs/models.py:67`：生成器内部行来源记录。
- `src/browser_cli/refs/view.py:76`、`:117`：验证行来源、按顺序筛选和截断，返回实际可见引用。
- `src/browser_cli/daemon/browser_service.py:551`：有结构的 interactive 组合；`:655`：填写/提交的部分执行状态。
- `src/browser_cli/daemon/app.py:147`：动作完成与收尾失败分开判断，保留失败/取消和进度。
- `src/browser_cli/daemon/client.py:126`、`src/browser_cli/task_runtime/node/client.mjs:10`：客户端筛选回执检查。

同步更新了使用指南、README、AGENTS 和文档守卫。11 月 5 日报告及基准文件保留为历史记录，并加了指向本报告的说明；没有用旧性能数字冒充本次复测结果。

## 回归覆盖

先增加回归测试，确认修复前确实出现失败，再修改实现。覆盖内容包括：

- 引号正文、伪造 ref、同角色前缀仿冒、内部来源记录缺失/不一致。
- scope/role/interactive 的组合、空匹配、禁用状态、真正的 cursor 状态与名称里的伪状态。
- 截断在筛选后生效；截断后的引用数与实际返回相符；无引用的祖先行可以使返回行数大于引用数。
- iframe 路径、同名元素 nth、旧引用编号和完整 registry 保持；普通 interactive 表示不变。
- Python/Node 的不一致筛选回执、大小写/前缀归一化和重复 role；错误不回传未筛选内容、不触发重放。
- 填写后页面变化，不发送 Enter，后续 batch 步骤不执行，前面字段效果仍可观察且只执行一次。
- 成功动作后收尾失败的 `completed`，部分失败后的 `unknown`，收尾二次失败不覆盖原失败或取消；all/last/summary 进度一致。

浏览器集成回归复用一个独立 Chrome Headless Shell 进程与本地模拟页面。启动前实际权限检查确认当前沙箱拒绝 LaunchServices，因此复用此前用户授予的本地测试授权，通过受审查的沙箱外执行运行。没有尝试受限启动、切换浏览器或操作真实账号。

## 检查结果

最终 `./scripts/check.sh` 退出 **0**：

- Python：**546 passed**，105.66 秒，比上一轮的 512 项增加 34 项回归。
- Node/扩展 JS：**72 passed，0 failed，0 skipped**，包括 33 项 Node 客户端测试，比上一轮增加 15 项。
- 其中本地浏览器工作流集成回归为 **47 项**，共享一个独立 Headless Shell 进程；新增 3 项集成场景验证组合筛选与截断、填写后的 URL 变化、动作完成后的收尾失败。最终全量运行同时覆盖修正后的行来源实现。
- compileall、Python 3.10 兼容检查、ruff check/format、JS syntax，以及架构/产品/文档守卫全部通过。
- `uv build --no-sources` 成功生成当前源码的本地 wheel 与 sdist，源码包一致性测试通过。
- `git diff --check` 通过。没有提交、推送、发布，也没有扩大浏览器操作权限。

最终完整检查日志：`/private/tmp/browser-cli-review-check-final.log`；最终本地构建日志：`/private/tmp/browser-cli-review-build-final.log`。早期失败复现保存在 `browser-cli-review-regressions-before.log`、`browser-cli-review-state-before.log`，它们仅含本地测试数据。

复现命令：

```bash
uv run pytest -q tests/unit/test_snapshot_views.py tests/unit/test_batch.py tests/unit/test_daemon_client.py tests/unit/test_daemon_browser_service.py tests/unit/test_owned_page_cancellation.py tests/unit/test_cli_output_contract.py
node --test node/tests/client.test.mjs
uv run pytest -q tests/integration/test_agent_workflows.py
uv build --no-sources
./scripts/check.sh
git diff --check
```

本次构建用于让源码包一致性测试检查当前文件，没有发布。完整日志保存在 `/private/tmp/browser-cli-review-*.log`。

## 保留的限制

本次修复不证明同 URL 重载后的文档身份，也不消除 URL 检查与实际输入之间的所有导航竞态。`max-lines` 是内容行数限制，不是字节或 token 上限；截断提示另占一行。筛选和精简也不承担敏感数据脱敏。

没有修复已有 `--no-full-page` 视口裁剪缺口，没有新增全局 deadline，没有扩大脚本权限或改变断连后不重放、关闭自有页面才取消远端等待的约定。scope/interactive 的扩展采集参数和语义有双驱动 stub 覆盖，真实浏览器验证使用 Headless Shell；真实 Chrome 扩展实机验收仍属于下一步。真实 Agent 工具次数、模型轮次、token 和端到端耗时仍未测，本报告不主张新的性能提升。
