# Browser CLI 项目导读

## 先看全貌

这个项目不是“给开发者写脚本用的一个浏览器库”，它更像一个站在命令行后面的浏览器操作员。你发出一句话式命令，它去开浏览器、找页面、点按钮、读内容，然后把结果用稳定的 JSON 或文本吐回来。

它做三件事，而且三件事分得很清楚。

1. `browser-cli read` 负责“一次性读取网页”。
2. daemon-backed actions 负责“持续控制浏览器”。
3. `task` 和 `automation` 负责“把一串操作固化成可复用任务”。

这三件事连起来，就是一个给 AI agent 用的浏览器工作台。入口在 [main.py](../src/browser_cli/cli/main.py)，命令目录很小，后面的系统很厚。

---

## 先用一个具体场景理解它

假设你想做两件事。

第一件事，你只想知道一个页面渲染后的内容。页面里的文字要等 JavaScript 跑完才出现。你不想自己管 Chrome 进程、等待时机、滚动到底部。你只想打：

```bash
browser-cli read https://example.com --scroll-bottom
```

这时项目走的是“短路径”：

- CLI 收到命令，在 [read.py](../src/browser_cli/commands/read.py) 里把 URL 规范化。
- 它调用任务运行时客户端 [client.py](../src/browser_cli/task_runtime/client.py)。
- 客户端走共享读取逻辑 [read.py](../src/browser_cli/task_runtime/read.py)。
- 这层把请求发给 daemon 的 `read-page`。
- daemon 再让浏览器服务 [browser_service.py](../src/browser_cli/daemon/browser_service.py) 新开一个临时页、等待渲染、必要时滚动、抓 HTML 或 snapshot，然后把这个临时页关掉。

测试里专门盯着这件事：`read` 读完不能把临时标签页泄漏出来，已有标签页也不能被打乱。你能在 [test_task_runtime_read.py](../tests/integration/test_task_runtime_read.py) 里看到这个约束。

第二件事，你想持续操作页面。比如：

```bash
browser-cli open https://example.com
browser-cli snapshot
browser-cli click @8d4b03a9
browser-cli fill @abcd1234 "hello"
```

这时项目走的是“长路径”：

- CLI 仍然很薄，[action.py](../src/browser_cli/commands/action.py) 只负责把命令变成请求。
- action catalog 在 [cli_specs.py](../src/browser_cli/actions/cli_specs.py)。这里列了 60 多个动作，像 `open`、`snapshot`、`click`、`network-start`、`verify-text`。
- daemon client 在 [client.py](../src/browser_cli/daemon/client.py) 里保证守护进程存在，然后把请求通过 Unix socket 发过去。
- daemon app 在 [app.py](../src/browser_cli/daemon/app.py) 里分发动作。
- 真正干活的是 daemon 自己持有的浏览器服务 [browser_service.py](../src/browser_cli/daemon/browser_service.py)。

所以，CLI 像前台。daemon 像总调度台。浏览器服务才像真正拿着鼠标和键盘的人。

---

## 它最重要的设计，不是“能开浏览器”，而是“把控制面收拢”

很多浏览器自动化项目，一上来就让你直接写 Playwright API。这个项目刻意不这么做。它先冻结公共契约，再让实现去服从它。

你能从两个地方看出这种执拗。

- 产品契约守卫在 [product_contracts.py](../scripts/guards/product_contracts.py)。它会检查顶层命令必须有 `read`、`task`、`automation`、`status`、`reload`，而且不允许冒出 `explore` 或 `session` 这种表面。
- 架构守卫在 [architecture.py](../scripts/guards/architecture.py)。它限制包之间的依赖方向，防止 CLI 直接摸浏览器底层，防止 driver 偷偷接受原始 `ref`。

这就像一栋楼先浇了承重墙。房间可以改，承重墙不能乱拆。

---

## daemon 是整套系统的脊梁

daemon 解决一个很具体的问题：浏览器状态很贵，不能每敲一条命令就从零启动一次。

如果没有 daemon，你执行 `open`、`click`、`html` 会变成三次独立进程。前一次打开的页，后一次根本不认识。daemon 让浏览器实例活着，让标签页、Cookie、localStorage、network capture、console capture 都延续下去。

这一层的关键文件有三组。

- 传输和拉起： [client.py](../src/browser_cli/daemon/client.py)
- 命令分发： [app.py](../src/browser_cli/daemon/app.py)
- 浏览器状态机： [browser_service.py](../src/browser_cli/daemon/browser_service.py)

`browser-cli status` 也很重要。它不是附属命令，而是“先看体温计”。它读 daemon 的运行信息，再问 daemon 当前活得怎么样，最后生成一份人能看懂的状态报告，入口在 [status.py](../src/browser_cli/commands/status.py)。状态分类逻辑集中在 [runtime_presentation.py](../src/browser_cli/daemon/runtime_presentation.py)。

这意味着，状态语义不分散。CLI、扩展弹窗、后台都看同一份 runtime truth，而不是各自瞎猜。

---

## driver 层解决的不是“兼容多个后端”，而是“对外只暴露一个浏览器”

项目底下有两套真实后端。

- Playwright driver，在 [playwright_driver.py](../src/browser_cli/drivers/playwright_driver.py)
- Chrome extension driver，在 [extension_driver.py](../src/browser_cli/drivers/extension_driver.py)

它们都实现同一份抽象接口 [base.py](../src/browser_cli/drivers/base.py)。这个接口很长，因为项目把“浏览器能做的事”完整列了出来：开标签页、截图、抓网络、填表单、验证文本、录 trace、录视频。

这层的关键想法是：外面只有一个 `browser-cli`，里面可以换司机。

默认司机是 Playwright。它最稳，项目自己能管。底层浏览器服务在 [browser/service.py](../src/browser_cli/browser/service.py)，它会用专用 Chrome 数据目录启动持久上下文。这个数据目录的发现和锁文件检测在 [discovery.py](../src/browser_cli/profiles/discovery.py)。

如果浏览器扩展连接上了，而且能力齐全，系统会优先切到 extension driver。扩展端入口在 [background.js](../browser-cli-extension/src/background.js)，它通过 WebSocket 连回 daemon，协议定义在 [protocol.py](../src/browser_cli/extension/protocol.py) 和对应的 JS 文件里。

这里最值得你注意的，不是“双后端”，而是“安全切换”。项目不在命令执行一半时切 driver。它等到 safe point，也就是命令边界，再切。测试在 [test_daemon_browser_service.py](../tests/unit/test_daemon_browser_service.py) 里把这件事钉死了。

为什么？因为半路换司机，状态就会乱。标签页可能要重建，snapshot 一定会失效。所以系统把这种切换明确标成 `state_reset`。它不装作“什么都没发生”。

这很诚实，也很适合 agent。

---

## semantic ref 是这套系统最像“给 agent 设计”的地方

新手最容易问：为什么不直接用 CSS selector？

因为 agent 常常先“看”，再“点”。它看到的是页面语义，不是开发者的类名。页面今天叫 `.btn-primary`，明天叫 `.btn-main`，agent 不该跟着碎掉。

这个项目的做法是：

- 先抓一份 semantic snapshot。
- snapshot 里给每个元素分配短 ref，比如 `@abcd1234`。
- 这个 ref 不直接存 DOM 节点指针，而是存角色、名字、文本、层级、frame 路径等信息。
- 真正执行 `click @abcd1234` 时，daemon 再把 ref 还原成 `LocatorSpec`，然后交给 driver。

生成和恢复都在 `refs` 包里：

- 解析与重建在 [resolver.py](../src/browser_cli/refs/resolver.py)
- 模型在 `refs/models.py`
- 最新 snapshot 注册表在 `refs/registry.py`

这里有一个很重要的边界：driver 不接受原始 ref。它只接受 daemon 算好的 `LocatorSpec`。守卫脚本也盯着这点。这样 Playwright 和 extension 才不会各自偷偷发明一套 ref 语义。

你可以把它想成这样：agent 先画一张地图，再拿地图编号去找门牌。地图由 daemon 统一画，司机只负责按门牌开车。

---

## `X_AGENT_ID` 让多个 agent 共用浏览器，又互相少踩脚

这部分很像“多人共用一个办公室，但每个人只看见自己的文件夹”。

`X_AGENT_ID` 在 [agent_scope/__init__.py](../src/browser_cli/agent_scope/__init__.py) 里解析。tab 的归属、活跃页、忙碌状态都由 [tabs/registry.py](../src/browser_cli/tabs/registry.py) 管。

结果是这样：

- 多个 agent 可以共用同一个浏览器实例和存储状态。
- 但每个 agent 默认只看见自己开的标签页。
- 如果某个标签页正在被另一个请求操作，系统会报 busy，而不是两边一起抢鼠标。

这和传统“每个测试开一个浏览器”不同。它更像多用户操作系统，而不是一次性脚本。

---

## `task` 把临时命令串成一段可复用逻辑

当你从“手打一串命令”走到“我要反复做这件事”，项目就让你进入 `task` 层。

一个任务目录最少有两个文件：

- `task.py`，写动作逻辑
- `task.meta.json`，写结构化知识

任务入口装载和校验在 [entrypoint.py](../src/browser_cli/task_runtime/entrypoint.py)，元数据模型在 [models.py](../src/browser_cli/task_runtime/models.py)。

先看一个很短的真实例子，[interactive_reveal_capture/task.py](../tasks/interactive_reveal_capture/task.py)：

- 打开 URL
- 抓 snapshot
- 找到名字叫 `Reveal Message` 的按钮
- 点击
- 等待文字 `Revealed`
- 导出 HTML 和 snapshot artifact

这段逻辑读起来已经很像人在说话了。原因在 [flow.py](../src/browser_cli/task_runtime/flow.py)。`Flow` 把底层命令包成更顺手的方法：`open()`、`snapshot()`、`click()`、`wait_text()`、`write_text_artifact()`。

`task.meta.json` 也很值得看，比如 [interactive_reveal_capture/task.meta.json](../tasks/interactive_reveal_capture/task.meta.json)。它不存聊天记录，而存稳定知识：输入、目标、成功路径、恢复提示、关键 ref、已知等待点。换句话说，它像任务说明书，不像流水账。

---

## `automation` 再往前走一步：把任务冻结成版本

`task` 还是活源码。你改 `task.py`，下次运行就变了。

`automation` 不一样。它强调“发布时冻结”。

发布逻辑在 [publisher.py](../src/browser_cli/automation/publisher.py)。它会把：

- `task.py`
- `task.meta.json`
- `automation.toml`

一起复制到 `~/.browser-cli/automations/<automation-id>/versions/<version>/` 下面。这个版本以后不再改。你再发布一次，就生成新版本。

这里的三种文件分工很清楚。

- `task.py` 写“怎么做”。
- `task.meta.json` 写“这件事是什么、怎么恢复、关键点在哪”。
- `automation.toml` 写“什么时候跑、输出放哪、超时多久、钩子怎么配”。

清单结构在 [models.py](../src/browser_cli/automation/models.py)，加载器在 [loader.py](../src/browser_cli/automation/loader.py)。

这层再往上，是一个常驻本地服务。CLI 入口在 [commands/automation.py](../src/browser_cli/commands/automation.py)，HTTP API 在 [api/server.py](../src/browser_cli/automation/api/server.py)，服务拉起逻辑在 [service/client.py](../src/browser_cli/automation/service/client.py)。

所以，`task` 像工作台上的草稿本，`automation` 像盖章入库的版本件。

---

## 扩展和弹窗不是第二套大脑，它们只是观察窗

浏览器扩展会做两件事。

- 它把真实 Chrome 的能力通过 WebSocket 接到 daemon。
- 它提供一个 popup，让人看当前 runtime 是健康、降级、恢复中还是坏掉。

但 popup 不自己定义状态语义。它读 daemon 给出的 presentation。你能在 [popup_view.js](../browser-cli-extension/src/popup_view.js) 和 [runtime_presentation.py](../src/browser_cli/daemon/runtime_presentation.py) 里看到这条线。

这点很重要。否则 UI 一套说法，CLI 一套说法，agent `meta` 再一套说法，系统很快就会自相矛盾。

---

## 如果你是第一次接触浏览器自动化，最该先抓住这五个概念

1. 页面不是静态文件。很多文字要等 JavaScript 跑完，`read` 就是在“等它真的长出来”。
2. 浏览器自动化不只是“打开网址”。还包括标签页状态、等待时机、网络记录、截图、下载、表单、验证。
3. 这个项目把“浏览器动作”变成命令，把“命令串”变成任务，把“任务发布版”变成自动化。
4. semantic ref 不是 CSS 选择器的花哨替代品。它是给 agent 用的语义地图。
5. dual driver 不是功能炫技。它是现实妥协：默认先稳，再在安全时机切到更接近真人 Chrome 的后端。

---

## 你可以按这个顺序理解整个仓库

1. 先读 [README.md](../README.md)，建立产品感。
2. 再读 [main.py](../src/browser_cli/cli/main.py) 和 [cli_specs.py](../src/browser_cli/actions/cli_specs.py)，知道对外有哪些命令。
3. 再读 [app.py](../src/browser_cli/daemon/app.py) 和 [browser_service.py](../src/browser_cli/daemon/browser_service.py)，知道命令怎样落到浏览器。
4. 然后读 [base.py](../src/browser_cli/drivers/base.py) 和两个 driver，理解“一个契约，两个后端”。
5. 再读 [resolver.py](../src/browser_cli/refs/resolver.py)，理解 ref 为什么能给 agent 用。
6. 最后读 [flow.py](../src/browser_cli/task_runtime/flow.py) 和示例任务，看看作者希望人怎样写自动化。
7. 如果你想理解“为什么这些边界不能乱动”，看 [product_contracts.py](../scripts/guards/product_contracts.py) 和 [architecture.py](../scripts/guards/architecture.py)。

---

## 一句话收尾

这个项目的核心，不是“控制浏览器”四个字，而是“把浏览器控制整理成一套适合 agent 长期使用的公共基础设施”。它把命令面、状态面、驱动面、语义定位、任务复用、版本发布，都钉在了明确的位置上。

如果你愿意，我下一步可以继续做两件事里的任意一件：

1. 用一张“分层架构图 + 一条命令时序图”把这套系统画出来。
2. 按新手路线，带你从 `browser-cli read` 开始，一步步读懂 `open -> snapshot -> click -> task -> automation publish`。
