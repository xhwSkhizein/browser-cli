# 工作进展与后续计划

更新时间：2026-10-22。当前分支：`codex/runtime-observability-api`。

## 当前整体状态

四项功能主体已经实现。关键核查后，进一步修复了异步读取与批量调度、Node 客户端运行版本检查、取消收尾和独立托管配置目录等问题，并补充真实浏览器与独立安装验收。改动已完成审阅，按环境诊断、自动化接口和审阅修复三部分整理为本地提交，尚未推送、创建 PR 或发布版本。本机默认 CLI 与后台仍运行功能验收时安装的 wheel；本次审阅新增的清理修复保存在源码提交中。真实扩展截图发现并修复了非 100% Chrome 缩放下的坐标、DPR、像素取整及 ICC 色彩配置问题，八种实图验收均已通过。

Browser CLI 原有的基础包括命令行、常驻后台服务、托管 Chrome 与扩展两种驱动，以及 Python 任务和自动化服务。本轮继续使用这些基础：截图、批量动作和临时上下文都经过同一后台服务；Node.js 客户端直接调用该服务。

本轮开始前已有的 macOS 浏览器启动权限检查属于当前实现的依赖，已审阅并随环境诊断一起提交。`runs/` 下的运行产物保留在本机，通过忽略规则排除出提交。

## 四项优化的完成情况

| 需求 | 已实现的行为 | 当前状态 |
| --- | --- | --- |
| 可控截图 | 支持当前视口、整页、指定矩形、精确视口和 DPR；返回实际图片尺寸、捕获参数及前后页面几何信息；临时修改结束后恢复，并校验页面尺寸和滚动位置 | 实现完成；托管 Chrome 与真实扩展均已验收，包含 90% 浏览器缩放下的尺寸、区域和颜色核对 |
| 隔离浏览器上下文 | `batch --context` 固定视口、页面 DPR、CSS 缩放、语言、时区和字体；隔离 Cookie 与站点存储；成功、失败或服务端任务取消后关闭上下文 | 实现完成；真实 Chrome 覆盖环境参数、存储隔离、重复截图、取消、超时和断线后的清理 |
| 更准确的健康检查 | `status` 与 `doctor` 分别报告服务、扩展、配置目录、托管配置和输出目录；区分运行状态与当前调用进程的目录权限 | 实现完成；分类测试通过，已复核后台健康而调用进程目录不可写的真实场景 |
| 结构化自动化接口 | 提供 Node.js 18+ ESM 客户端、直接套接字通信、批量动作和稳定 JSON；支持完整、最后一步和摘要三种结果模式 | 实现完成；协议、真实后台与独立 wheel 安装验收通过，客户端已纳入 Python 安装包 |

### 截图与可重复运行

- CLI 新增 `--page-range`、`--clip`、`--viewport-width`、`--viewport-height`、`--dpr` 等参数，保留 `--full-page` 兼容写法。
- 截图结果返回 `screenshot_size` 和 `capture`；PNG、JPEG 的尺寸取自实际图片数据。页面前后几何校验失败时返回错误，不保存本次截图。
- 截图参数中的 DPR 控制输出图片密度；上下文的 DPR 同时影响页面看到的 `window.devicePixelRatio`。两者用途已经写入使用文档。
- 临时上下文复用后台管理的 Chrome 进程。字体可通过本地字体文件嵌入；上下文内固定视口，其他尺寸另开一次运行。
- 修复了临时 CDP 连接和截图参数可能重置页面 DPR 的问题，相关经验已写入 `AGENTS.md`。

### 健康检查

- `status --json` 的 `status_scope` 为 `runtime`，保留后台服务给出的运行状态。
- `doctor --json` 的 `status_scope` 为 `environment`，汇总安装和环境检查。
- 两者共用 `health.service`、`extension`、`config_dir`、`managed_profile`、`output_dir`，目录信息标明 `checked_by: "caller"`。
- 目录权限通过实际临时写入探测，随后清理探测文件。因此可以明确表达“服务与扩展正常，但当前命令进程无法写入默认目录”，避免将两种状态混为一谈。

### Node.js 与批量执行

- 正式客户端随 Python 包一起安装；`browser-cli paths --json` 返回 `node_client` 和实际 `socket_path`，源码仓库另提供导入入口。
- 首次发现路径或启动服务后，浏览器动作直接走套接字，不必逐条启动 CLI 子进程。
- 批量支持 1–500 个动作、遇错停止或继续，以及 `all`、`last`、`summary` 结果模式。精简模式减少成功步骤的大块输出，同时保留错误明细。
- 响应保留 `ok/data/meta`：顶层 `ok` 表示请求已处理，批量是否全部成功应检查 `data.success`。
- 批量执行期间协调其他浏览器动作和后台异步读取；运行状态、日志及取消指令仍可响应。连接中断或等待超时后不会自动重放已发送动作。

## 关键核查后的补充优化

- 请求和后台异步读取共用 `daemon/execution.py` 的执行协调器。普通批量和隔离批量都会等待正在执行的读取；新的读取可以排队，排队或运行中的读取仍可查询和取消。取消尚未开始的读取也会进入终态。
- Node 客户端在每次动作前读取 `runtime-status` 并核对运行版本，直接指定套接字路径也适用。不兼容时返回 `DAEMON_INCOMPATIBLE`，包含预期和实际版本及升级/重载指引。服务端再次检查请求中的预期版本；产品守卫检查 Python 与 Node 的版本声明一致。
- 取消隔离批量时，先停止安排后续步骤、关闭临时上下文，再等待正在进行的浏览器调用收尾；“遇错继续”模式也遵循这个规则。客户端超时或断线不会取消服务端执行，也不会重放动作；执行结束后关闭上下文。
- 审阅发现命令清理抛错或在清理期间取消时，异常分支会重复调用 `end_command`，可能把共享命令计数少算一次。现已在等待清理前清除待清理标记，保证只调用一次；两个稳定复现的回归测试均通过。
- 托管配置目录随 `BROWSER_CLI_HOME` 一起迁移，避免独立测试服务误用默认托管配置。
- 扩展视口与截图矩形计入 Chrome 标签页的浏览器缩放，保留页面 DPR 和用户缩放设置；读取稳定几何信息后才确认恢复。小数边界通过整数包围区域与精确裁剪处理；Chrome 矩形截图可能缺失的 ICC 信息从原生截图恢复，再通过已有离屏页面解码和编码，以保留颜色。
- 新增 `scripts/smoke_installed_wheel.py` 与 `node/smoke-extension.mjs`，将安装包和真实扩展验收变为可重复执行的命令。独立安装会为该 Playwright 版本准备临时 ffmpeg 缓存。
- `runs/` 已加入 Git 忽略规则，保留其中已有运行产物。

## 验证结果

本轮代码的最后一次完整检查已经通过：

| 检查 | 结果 |
| --- | --- |
| Python 测试 | 347 项通过，零跳过，含本次审阅新增的两项回归 |
| JavaScript 测试 | 28 项通过，零跳过 |
| Lint、格式及 Python 3.10 兼容检查 | 通过 |
| 架构、产品契约及文档同步检查 | 通过 |
| 源码包与 wheel 构建 | 通过；开发版本由当前提交生成，源码包包含新增扩展模块和验收测试 |
| wheel 中实现和 Node.js 客户端内容核对 | 105 个源码文件与当前源码一致 |
| 独立 wheel 安装 | 冷启动、1280×960 截图、失败处理与配置隔离均通过 |
| 本机默认 CLI 与后台 | 已安装功能验收 wheel，运行协议 v2；本次审阅修复尚未重新安装到默认服务 |
| `git diff --check` | 通过 |

使用的主要命令：

```bash
UV_CACHE_DIR=/private/tmp/browser-cli-uv-cache PYTEST_ADDOPTS=-ra ./scripts/check.sh
UV_CACHE_DIR=/private/tmp/browser-cli-uv-cache uv build --no-sources --clear
```

真实浏览器测试在检查 macOS LaunchServices 权限后，经审查获准在沙箱外运行，使用本机稳定版 Chrome。原有 `read` 集成测试的可用性探测也已改为使用该 Chrome，避免因缺少 Playwright 自带浏览器而跳过。

独立安装验收已经完成路径发现、随 wheel 安装的 Node 客户端导入、后台冷启动、1280×960 隔离截图、失败结果处理和临时配置目录核对。真实环境中已确认 `status` 保持 `healthy`，同时沙箱调用进程的目录项为 `fail`，`doctor` 汇总环境失败。后台已运行 `2026-10-22-capture-context-batch-v2`，扩展报告 `screenshot-controls`；90% Chrome 浏览器缩放下的八种真实扩展截图已通过：原生临时视口、视口 DPR 1/2、整页、矩形 PNG/JPEG、固定视口 PNG/JPEG；同时确认前后几何一致，以及 PNG 裁剪区域与整页对应区域颜色完全一致、JPEG 在压缩误差范围内一致。报告和截图保存在 `runs/runtime-api-acceptance/extension.json` 及同目录图片中。实际健康检查报告保存在 `runs/runtime-api-acceptance/status.json` 与 `doctor.json`。

## 当前边界与需要保留的说明

1. 隔离运行由托管驱动实现。从扩展驱动切换时可能重建共享标签页，影响页面内存和登录状态；结果通过 `state_reset` 明确报告。
2. `zoom` 使用 CSS 缩放，结果标明 `zoom_method: "css"`。为注入字体和缩放样式，临时上下文启用 `bypass_csp`。
3. 跨机器逐像素比较仍需要相同平台、Chrome 版本和字体文件。系统字体、封闭的 Shadow DOM、页面自行修改样式都可能影响结果。
4. Node.js 超时只表示客户端停止等待，服务端可能仍在执行；重试前应确认动作状态。
5. 旧扩展缺少 `screenshot-controls` 能力时会返回明确提示。启用新功能需要重新加载后台服务和扩展。

## 接下来的方向

主体实现、真实环境验收与本轮审阅已完成。改动整理为三笔本地提交：环境诊断与启动保护、截图和隔离批量自动化、命令清理只执行一次。接口扩展根据实际调用需求决定优先级。

### P0：本轮交付待办

- [x] 核对工作区改动；启动权限检查是当前实现依赖的一部分，`runs/` 产物保留并排除出提交。
- [x] 重载后台与扩展，确认服务运行新版本且扩展报告 `screenshot-controls`。
- [x] 完成八种真实扩展截图验收，核对实际尺寸、视口/DPR/滚动恢复，以及矩形 PNG 的精确颜色、JPEG 在压缩误差内的颜色和区域。
- [x] 复核真实健康检查场景：后台和扩展正常、调用进程目录不可写时，`status` 与 `doctor` 的分项结果符合各自作用域。
- [x] 从 wheel 在独立临时环境完成路径发现、客户端导入、冷启动、隔离截图、失败处理与配置目录核对。
- [x] 审查并补齐调度、生命周期、取消及版本兼容回归；最终完整检查已通过。
- [x] 整理并提交当前分支。后续是否推送、创建 PR、合并和发布，按交付要求推进。

### P1：验收后可推进的完善

- [ ] 为 Node.js 客户端补充 TypeScript 类型声明，改善参数提示和结果类型检查。

### P2：根据使用反馈决定

- [ ] 评估隔离上下文内动态读取结果、再决定下一步动作的需求；当前隔离运行以单次批量请求为边界。
- [ ] 根据实际重复运行记录，评估字体加载、页面稳定等待和截图差异诊断是否需要更多控制项。

TypeScript 声明、动态交互和更多差异诊断仍是后续增强。本轮已完成最小运行版本兼容检查。

## 后续接手入口

完整操作示例见 [可重复截图与 Node.js 自动化](docs/automation-api-zh.md)，长期约束和导航见 [AGENTS.md](AGENTS.md)。主要实现位置如下：

| 内容 | 入口 |
| --- | --- |
| 截图参数、几何信息与图片尺寸 | `src/browser_cli/browser/capture.py` |
| 上下文参数、字体与环境固定 | `src/browser_cli/browser/context.py` |
| 托管浏览器截图与上下文底层操作 | `src/browser_cli/browser/service.py` |
| 扩展截图和视口恢复 | `browser-cli-extension/src/debugger.js` |
| 批量调度与上下文生命周期 | `src/browser_cli/daemon/execution.py`、`src/browser_cli/daemon/app.py`、`src/browser_cli/daemon/browser_service.py` |
| 共用健康检查 | `src/browser_cli/daemon/health.py` |
| Node.js 正式客户端与仓库导入入口 | `src/browser_cli/task_runtime/node/client.mjs`、`node/browser-cli-client.mjs` |
| 真实浏览器集成验证 | `tests/integration/test_capture_context_batch.py` |

可重复验收命令：

```bash
node node/smoke-extension.mjs runs/runtime-api-acceptance .venv/bin/browser-cli
uv run python scripts/smoke_installed_wheel.py dist/<构建出的文件名>.whl
```
