# Browser CLI 使用导引

## 先把位置摆正

如果你把 Browser CLI 当成“给人手敲命令的浏览器工具”，你一开始就看偏了。它真正擅长的事，是让 Agent 在真实浏览器里读页面、操作页面、记住状态、复用流程。

人当然也能直接运行 `browser-cli open`、`browser-cli click`、`browser-cli read`。但这不是它最有价值的用法。它最有价值的用法，是你把目标、边界和凭据交给 Agent，Agent 再用 Browser CLI 去完成浏览器里的具体动作。

换句话说，人负责交代任务，Agent 负责跑浏览器。

---

## Browser CLI 解决的不是“怎么点按钮”，而是“怎么让 Agent 稳定地用浏览器”

普通脚本最容易坏在三个地方。页面是动态的，脚本拿到的常常不是最终内容。状态是连续的，脚本却总从一个刚出生的浏览器开始。流程是重复的，脚本写完一次后很难沉淀成可复用的任务。

Browser CLI 正好补这三个缺口。

- 它能读渲染后的页面，而不是只抓原始 HTML。
- 它能保留一个常驻浏览器，让 Agent 连续操作同一组标签页、Cookie 和登录态。
- 它能把一次跑通的流程收进 `task.py`，再发布成可复用的 automation。

这三件事连起来，才是它的主线。Agent 先看清页面，再动手操作，最后把稳定流程留下来。

---

## 人和 Agent 怎么分工

最有效的分工很简单。人定义目标、约束和验收条件，Agent 负责把这些要求翻成浏览器动作。

一个好目标长这样：

> 登录供应商后台，进入昨日订单列表，筛出退款订单，导出 CSV，保存到 `exports/`，如果页面结构变化就先停下来并报告。

这句话里已经有 Agent 需要的关键信息。

- 它知道要去哪一个系统。
- 它知道要拿什么结果。
- 它知道结果该落到哪里。
- 它知道什么时候该继续，什么时候该停。

Agent 拿到这类目标后，通常会这样工作：

1. 先用 `browser-cli read` 或 `browser-cli snapshot` 看页面。
2. 再用 `open`、`click`、`fill`、`page-reload` 之类的命令推进流程。
3. 确认步骤稳定后，把动作写进 `task.py`。
4. 需要长期运行时，再发布成 automation。

人不必站在旁边一条条敲命令。人只需要给出方向、权限和边界。

---

## 先看清页面，Agent 才能做对事

Agent 用浏览器工作，第一步不是“点击”，而是“观察”。Browser CLI 给 Agent 的第一种能力，就是读到页面真正呈现出来的内容。

最短的探路命令是：

```bash
browser-cli read https://example.com
```

这条命令会打开页面，等页面渲染，再返回结果。它读到的是浏览器执行脚本后的页面，而不是服务器刚吐出来的原始文本。对靠 JavaScript 渲染的后台、控制台、仪表盘来说，这个区别很要命。你读原始 HTML，常常只会看到一个空壳；你读渲染结果，才能看到表格、按钮和真实文案。

如果 Agent 需要的不是整页 HTML，而是“这页有哪些可操作元素”，可以改用：

```bash
browser-cli read https://example.com --snapshot
```

`--snapshot` 给出的不是截图，而是一份面向操作的页面结构摘要。标题、按钮、链接、输入框会以更适合自动化的方式整理出来。Agent 读这份结构，比在一大段 HTML 里翻 CSS class 更快，也更稳。

如果页面要滚到底部才会继续加载内容，再加：

```bash
browser-cli read https://example.com --snapshot --scroll-bottom
```

这类命令适合 Agent 探路。它先看见页面，再决定下一步该点哪里、等什么、抓什么。

---

## 页面一旦要互动，Agent 就该切进常驻浏览器

`read` 适合侦察，不适合长流程。Agent 一旦要登录、翻页、填表、下载文件，就需要一个活着的浏览器上下文。Browser CLI 用 daemon 提供这个上下文。

你可以把 daemon 理解成“Agent 共用的浏览器管家”。它会保留浏览器进程、标签页、Cookie、当前页面和一些运行状态。于是 Agent 不必每一步都从零开始。

一个最小的交互流程通常长这样：

```bash
browser-cli open https://example.com/login
browser-cli snapshot
browser-cli fill @user_ref "alice"
browser-cli fill @password_ref "secret"
browser-cli click @submit_ref
browser-cli html
```

这串命令里最关键的不是 `click`，而是 `snapshot`。Agent 先抓一份当前页面的语义地图，再按地图上的 ref 去点按钮、填输入框。这样做，比直接硬写 CSS selector 更接近人类看页面的方式，也更适合 Agent 在页面变化后重新定位。

这也是 Browser CLI 的一个核心设计：Agent 操作的是“页面上那个按钮”“那个输入框”“那个链接”，而不是一串容易变的 DOM 细节。

---

## `snapshot` 不是装饰，它是 Agent 的工作记忆

网页会变。弹窗会插进来，列表会重排，组件会重渲染。Agent 如果拿着旧 ref 继续点，迟早会撞上 `REF_NOT_FOUND` 或 `STALE_SNAPSHOT`。

稳妥的节奏是这样的：

```bash
browser-cli open https://example.com
browser-cli snapshot
browser-cli click @primary_button_ref
browser-cli snapshot
browser-cli fill @search_input_ref "refund"
browser-cli snapshot
browser-cli click @export_ref
```

每次页面明显变化后，Agent 都先刷新地图，再继续走。这一步看起来多，其实省时间。它让 Agent 少在“刚才还能点，现在为什么不能点”这种问题上打转。

如果你只记住一条协作习惯，就记这条：让 Agent 在关键节点重抓 `snapshot`。

---

## `task.py` 把一次成功流程变成一件可复用的工具

Agent 临场操作能解决一次问题，`task.py` 才能留下可复用的方法。你可以把它看成“把一次浏览器操作写成剧本”。

一个最小任务往往只做几件事：

- 打开页面。
- 观察页面。
- 操作页面。
- 验证结果。
- 返回结构化产物。

在 Browser CLI 里，这种剧本写在 `task.py`。它通常配合 `browser_cli.task_runtime` 里的 `Flow` 使用。代码读起来更像动作说明，而不像浏览器底层 API：

```python
from browser_cli.task_runtime.flow import Flow


def run(flow: Flow, inputs: dict) -> dict:
    flow.open(inputs["url"])
    snapshot = flow.snapshot()
    ref = snapshot.find_ref(role="button", name="Reveal Message")
    flow.click(ref)
    flow.wait_text("Revealed", timeout=5)
    return {"html": flow.html()}
```

这段代码没有绕弯。它打开页面，抓页面结构，找到按钮，点击，等待结果，最后返回 HTML。Agent 一旦把临场探索沉淀成这样的任务，下一次就不必重新摸路。

这里的边界也很清楚：

- `task.py` 写动作。
- `task.meta.json` 写任务知识和输入输出约束。
- `automation.toml` 写发布和运行配置。

把这三件事分开，Agent 才容易维护，后面接手的人也容易读。

---

## automation 让 Agent 从“会做一次”变成“能长期做”

很多浏览器工作不是只跑一次。日报抓取、后台巡检、订单导出、对账下载，这些任务会反复出现。Browser CLI 的下一层能力，就是把已经稳定的任务发布成 automation。

发布命令很直接：

```bash
browser-cli automation publish my_task
```

发布之后，系统会把当时的 `task.py`、`task.meta.json` 和 `automation.toml` 固化成一个不可变版本。这个版本可以被追踪、检查和重复运行。你以后再改源目录，不会悄悄改坏已经发布的版本。

这层设计对 Agent 很重要。Agent 在探索时需要灵活，在执行长期任务时需要稳定。Browser CLI 把这两种状态分开了：

- 探索和改动留在任务目录。
- 稳定和复用进入 automation 版本。

这就像实验台和生产线。你当然都需要，但你不该把它们混成一个地方。

---

## 多个 Agent 共用浏览器时，`X_AGENT_ID` 负责隔离

一旦你让多个 Agent 同时工作，浏览器就不只是“能打开页面”这么简单了。谁能看见哪个标签页，谁在操作当前活动页，谁该避开别人的上下文，这些都要讲清楚。

Browser CLI 用 `X_AGENT_ID` 处理这件事。

```bash
X_AGENT_ID=agent-a browser-cli open https://example.com/a
X_AGENT_ID=agent-b browser-cli open https://example.com/b
```

这两个 Agent 可以共用同一个 daemon 管理的浏览器实例，但它们不会把对方的标签页当成自己的工作台。这样做有两个直接好处。

- Agent A 填表时，Agent B 不会突然切走它正在用的页面。
- 每个 Agent 都能按自己的任务继续推进，而不是在共享状态里互相踩脚。

如果你想把 Browser CLI 接进多 Agent 系统，这不是一个边角特性，而是基础能力。

---

## 什么时候该让 Agent 用 Browser CLI

最合适的场景通常有几个明显特征。

- 页面依赖 JavaScript 渲染，直接抓 HTML 不够用。
- 流程跨多个页面，要保留登录态、标签页和上下文。
- 页面动作很多，API 又不稳定、不可见，或者根本没有可用 API。
- 任务会重复发生，值得沉淀成 `task.py` 和 automation。

举几个具体例子：

- Agent 登录客服后台，按筛选条件导出昨天的投诉单。
- Agent 打开广告平台，逐个账户截图预算告警页面并汇总。
- Agent 进入供应商门户，下载对账单，再把文件放进固定目录。
- Agent 在内部系统里巡检几个关键页面，发现错误提示就停下并报告。

这些任务的共同点不是“都需要浏览器”，而是“都需要一个会观察、会等待、会继续操作的浏览器”。

---

## 什么时候不必强行上 Browser CLI

Browser CLI 能做很多事，但不是所有事都该交给浏览器。

如果站点已经给了稳定 API，任务只是在拉 JSON、存数据库、发通知，那就先用 API。浏览器是重工具。你该用它的时候用，不该用的时候别把问题硬拽进页面。

一个简单判断是：任务的关键证据在页面里，还是在接口里？

- 如果关键证据在页面里，比如按钮、弹窗、下载链接、渲染后的表格，用 Browser CLI。
- 如果关键证据在接口里，而且接口稳定、权限清楚，优先直接调接口。

这不是退让，而是省力。

---

## 人真正需要学会的，不是每条命令，而是怎样把任务交代清楚

你不需要先变成浏览器自动化工程师，才能把 Browser CLI 用起来。你更需要学会的，是怎样给 Agent 一个能执行、能验收、能回退的任务说明。

这类说明通常包括四样东西：

- 目标：Agent 最后要拿到什么。
- 边界：哪些站点能进，哪些动作不能做。
- 输入：账号、日期、筛选条件、保存目录。
- 停止条件：页面结构变化、验证码、权限异常时该停下来还是该重试。

比如你可以这样对 Agent 说：

> 用 Browser CLI 登录运营后台，导出 2026-04-14 的退款订单，文件放到 `exports/refunds-2026-04-14.csv`。如果登录后出现验证码，不要继续尝试，直接报告。

这句话比“帮我把退款订单导出来”强得多。前一句给了路径、结果、文件名和停止条件；后一句只给了愿望。

Agent 能跑多稳，常常取决于你把任务说得有多具体。

---

## 一条实际工作流

把上面的能力连起来，一条典型工作流通常是这样走的。

1. 人提出目标：去哪个系统，拿什么结果，什么时候停。
2. Agent 用 `browser-cli read` 探路，确认页面是不是动态渲染，先看清结构。
3. Agent 切进 daemon-backed 命令，边 `snapshot` 边 `click`、`fill`、`wait`，把流程跑通。
4. 流程稳定后，Agent 把动作写进 `task.py`，把知识写进 `task.meta.json`。
5. 需要长期复用时，人或 Agent 运行 `browser-cli automation publish`，把当前任务冻结成一个可追踪版本。

这条路的重点不是“命令越来越多”，而是“探索、固化、复用”越来越清楚。

---

## 先学哪几样，已经够用

如果你现在就想把 Browser CLI 用进 Agent 工作流，不必先把整套命令背下来。先抓住这几样就够了。

- `browser-cli read`
  让 Agent 先看清页面。
- `browser-cli open`、`snapshot`、`click`、`fill`
  让 Agent 在常驻浏览器里连续操作。
- `task.py`
  让 Agent 把成功流程沉淀成可复用脚本。
- `browser-cli automation publish`
  让稳定任务进入长期运行。
- `browser-cli status`
  让你知道当前浏览器运行时到底活着没有。

这些能力已经足够覆盖大多数“让 Agent 去网页里办事”的场景。

---

## 最后把一句话说死

Browser CLI 不是给人演示命令有多全的工具。它是一个把浏览器交给 Agent 的运行时。

你给 Agent 一个明确目标，它替你读动态页面、操作真实浏览器、保留上下文、沉淀任务、发布自动化。人不必亲手点完每一个按钮。人只需要把事情交代清楚，再让 Agent 去做。
