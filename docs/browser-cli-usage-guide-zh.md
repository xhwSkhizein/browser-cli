# Browser CLI 使用导引

## 先把它当成什么

先把 Browser CLI 当成一个会替你操作浏览器的命令行助手。你不用先学 Playwright，也不用先写一百行脚本。你先打一条命令，它替你开页面、等页面渲染、点按钮、读结果。

这句话里有两个关键词。第一个词是“命令行”。你和它说话，主要靠 `browser-cli ...`。第二个词是“浏览器”。它真的会启动一个浏览器环境，而不是只抓原始 HTML。很多站点把内容写在 JavaScript 里，等页面跑起来才把文字塞进 DOM。这个项目正是来处理这件事。

如果你第一次接触浏览器自动化，先记住一句最实用的话：它不是在“下载网页”，它是在“使用网页”。

---

## 第一次上手，先跑通最短路径

先不要碰任务、自动化、扩展。你先证明这台机器能让 Browser CLI 成功打开一个页面。这一步最短，也最能排除环境问题。

项目建议的第一天路径很简单：

1. 安装 Browser CLI。
2. 跑 `browser-cli doctor`。
3. 跑 `browser-cli paths`。
4. 跑一次 `browser-cli read https://example.com`。

如果你用 `uv` 安装，命令是：

```bash
uv tool install browser-control-and-automation-cli
browser-cli doctor
browser-cli paths
browser-cli read https://example.com
```

这里有一个容易混淆的小地方。发布到包仓库的名字叫 `browser-control-and-automation-cli`，真正安装后的命令仍然叫 `browser-cli`。前者像盒子上的商品名，后者像你每天按下去的开关。

`doctor` 会先查机器。它会看 Python 环境，也会看 Chrome 是否存在。`paths` 会告诉你 Browser CLI 把自己的运行目录、日志目录、自动化目录放在哪里。等你以后查问题，这条命令会很有用，因为它直接把路径亮给你看，而不是让你去猜。

---

## 第一条真正有用的命令是 `read`

`read` 最适合用来理解这个项目，因为它做一件事，而且只做一件事：打开一个页面，等它渲染完成，然后把结果吐出来。

你可以先这样试：

```bash
browser-cli read https://example.com
```

这条命令默认输出渲染后的 HTML。你得到的不是服务器刚返回的那一坨原始文本，而是浏览器已经执行脚本、已经把页面拼好之后的结果。

如果你想看另一种结果，用 `--snapshot`：

```bash
browser-cli read https://example.com --snapshot
```

这里的 snapshot 不等于截图。它更像一份面向自动化的“页面结构摘要”。它会把按钮、标题、链接、输入框这些语义元素整理成一棵树。你把它读成“这页上有什么”，而不是“源码长什么样”。

如果页面靠下拉才会继续加载内容，再加 `--scroll-bottom`：

```bash
browser-cli read https://example.com --scroll-bottom
```

这时 Browser CLI 会滚到页面底部，再停一停，再读。这个停顿很关键。很多页面在你滚到末尾之后才发第二批请求，你滚得太快，抓到的还是半页东西。

所以，`read` 像一支探针。它先帮你确认两件事：

- 这个站点能不能被当前浏览器环境正常打开。
- 你要的内容是应该读 HTML，还是应该读 snapshot。

---

## 当你想“操作页面”，就切到交互命令

`read` 只读不动手。你要点按钮、填表单、切标签页，就要用 daemon-backed commands。

最简单的一组命令是：

```bash
browser-cli open https://example.com
browser-cli snapshot
browser-cli click @8d4b03a9
browser-cli html
```

这组命令背后的动作很像一个人：

- `open` 打开页面。
- `snapshot` 看一眼页面，把可操作元素列出来。
- `click @8d4b03a9` 去点刚才看到的那个元素。
- `html` 再读一遍页面，看点击之后发生了什么。

你会立刻注意到一个陌生东西：`@8d4b03a9` 这样的短串。这个项目叫它 `ref`。你可以把它当成页面元素的临时编号。你先让系统给你一张地图，再拿地图上的编号去操作元素。

这比直接写 CSS selector 更适合入门，也更适合 agent。因为你面对的不是源码作者的类名，而是“按钮”“链接”“输入框”这些人能看懂的对象。

一个常见流程长这样：

```bash
browser-cli open https://example.com/login
browser-cli snapshot
browser-cli fill @user_ref "alice"
browser-cli fill @password_ref "secret"
browser-cli click @submit_ref
browser-cli verify-text "Welcome back"
```

这里的节奏很重要。你先 `snapshot`，再 `fill` 或 `click`。你不要闭着眼去点。浏览器自动化里最常见的错误不是“代码不会运行”，而是“你点的元素已经变了，或者你根本没看到它”。

---

## `snapshot` 是你最该养成的习惯

如果你以后只记住一条使用建议，我会建议你记这条：动手之前，先 `snapshot`。

原因很简单。网页会变。按钮位置会变，文字会变，组件会重渲染，DOM 会抖一下再稳定。你如果直接拿旧编号去点，系统很可能会告诉你 `REF_NOT_FOUND` 或 `STALE_SNAPSHOT`。这不是它脾气坏，而是它在提醒你：地图过期了。

所以一个更稳的操作节奏是：

```bash
browser-cli open https://example.com
browser-cli snapshot
browser-cli click @button_ref
browser-cli snapshot
browser-cli fill @input_ref "hello"
```

旧地图引出新地图。第一次点击改变了页面，第二次 snapshot 就刷新了你手里的坐标。

这件事听起来琐碎，做起来却省时间。你少和“为什么明明刚才能点现在不能点”打架，就会更快走到任务完成那一步。

---

## 你可以把 daemon 理解成“常驻的浏览器管家”

交互命令之所以能连着用，是因为背后有一个 daemon。你不用手动启动它。你第一次执行 `open`、`snapshot`、`click` 这种命令时，Browser CLI 会按需拉起它。

这意味着什么？意味着浏览器状态会活着。

比如你先登录一个站点，再切到另一个命令读取页面。Cookie、标签页、当前页面、网络监听，这些东西不会在每条命令之间蒸发。你不是每次都拿到一个刚出生的浏览器，而是在和同一个会话继续说话。

你可以用这些命令观察它：

```bash
browser-cli status
browser-cli tabs
browser-cli reload
```

`status` 用来看体温。它会告诉你 daemon 是否活着、当前 driver 是什么、扩展是否连上、工作区标签页状态怎样。`tabs` 用来看你手里有哪些页。`reload` 则更像“重启运行时”，不是页面里的普通刷新。页面里的刷新命令叫 `page-reload`，这是两件不同的事。

这个区分很值钱。一个刷新页面，一个重置浏览器运行时。你把扳手和重启按钮分开，排错时就不容易误伤。

---

## 当 `read` 不够时，就开始写 `task`

你会很快遇到这样的场景：我不是只想点一次按钮，我想把这串动作反复执行。比如每天打开某个站点，点开一条详情，再把 HTML 存到文件里。命令一条条手打当然能做，但第二次你就会嫌烦。

这时就进入 `task`。

一个最小任务目录长这样：

```text
my_task/
  task.py
  task.meta.json
  automation.toml
```

你先不用被三个文件吓到。先抓分工。

- `task.py` 写动作。
- `task.meta.json` 写任务说明。
- `automation.toml` 写发布和调度配置。

对初学者来说，先盯住 `task.py` 和 `task.meta.json` 就够了。

运行一个任务之前，你先验证：

```bash
browser-cli task validate my_task
```

验证通过，再运行：

```bash
browser-cli task run my_task --set url=https://example.com
```

这里的 `--set` 很直白。它把一个输入值塞给任务。你把它看成命令行版的函数参数就行。

---

## `task.py` 写的不是浏览器底层 API，而是一段动作剧本

项目给你一个 `Flow` 对象。你在 `task.py` 里主要和它打交道。它把常用动作包成了更容易读写的方法。

一个很短的任务可以写成这样：

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

这段代码读起来像说明书：

- 打开页面。
- 抓一份 snapshot。
- 找到名字叫 `Reveal Message` 的按钮。
- 点击。
- 等待 `Revealed` 出现。
- 返回 HTML。

这就是项目刻意提供 `Flow` 的原因。它不逼你一开始就去接触低层浏览器对象。它先给你一套动词：`open`、`snapshot`、`click`、`wait_text`、`html`。这些词组合起来，已经能做很多事。

仓库里有几个很适合照着读的例子：

- [interactive_reveal_capture/task.py](../tasks/interactive_reveal_capture/task.py)
- [lazy_scroll_capture/task.py](../tasks/lazy_scroll_capture/task.py)
- [douyin_video_download/task.py](../tasks/douyin_video_download/task.py)

第一个例子教你点按钮。第二个例子教你滚动到底。第三个例子开始接真实站点，也开始处理 cookies、接口请求和下载文件。

---

## `task.meta.json` 不写代码，它写“人脑里的备忘录”

很多人第一次看到 `task.meta.json`，会以为它是多余文件。其实它恰好补上了代码不适合写的那部分知识。

代码适合写动作。元数据适合写意图、输入、恢复路径、关键等待点、稳定的角色名称。你可以把它当成一页贴在任务旁边的纸条。纸条上写着：

- 这个任务要什么输入。
- 它成功时应该得到什么。
- 哪一步最容易卡住。
- 哪个按钮最关键。
- 页面变了之后应该先重抓 snapshot。

这种信息很适合给人看，也适合给 agent 看。它不负责执行，但它能帮你少走弯路。

---

## 当任务准备长期运行时，再进入 `automation`

`task` 像工作台上的源文件。你随时改，随时试，下一次运行就看到新行为。

`automation` 则像你把当前任务拍成一个冻结版本，放进档案柜里。你发布一次，系统就把当时的 `task.py`、`task.meta.json`、`automation.toml` 复制到 Browser CLI 自己的自动化目录里，形成一个不可变版本。

发布命令很直接：

```bash
browser-cli automation publish my_task
```

发布后你通常会继续用这几条命令：

```bash
browser-cli automation list
browser-cli automation inspect <automation-id>
browser-cli automation status
browser-cli automation ui
```

这里的使用心法也很简单。

- 你想改任务逻辑，回去改 `task.py`。
- 你想看当前已经发布了什么，跑 `automation list`。
- 你想看某个自动化现在用的是什么配置，跑 `automation inspect`。
- 你想用浏览器界面点一点，跑 `automation ui`。

这套设计把“编辑中的东西”和“已经发布的东西”分开了。你不会一边调试，一边偷偷改坏线上用的版本。

---

## `automation.toml` 解决的是“怎么运行”，不是“怎么做动作”

这是一个很值得早点抓住的分工。

如果你想让任务每小时跑一次，或者想把输出放到某个目录，或者想设置超时、钩子、重试，这些配置应该写进 `automation.toml`。如果你想点击按钮、抓页面、下载文件，这些动作应该留在 `task.py`。

这条边界能帮你避免一种常见混乱：把一份任务拆成两套逻辑，一半在 Python 里，一半在 TOML 里。项目故意不鼓励这种写法。它要你把动作留在代码，把运行策略留在配置。

你按这个习惯写，后面看的人会轻松得多。因为他一眼就知道：要改步骤，开 `task.py`；要改调度，开 `automation.toml`。

---

## 如果你需要更像真人 Chrome 的行为，再开 extension mode

项目默认走 managed profile mode。对多数人来说，这条路最快，也最稳。你先把基本流程跑通，再考虑浏览器扩展。

什么时候值得折腾 extension mode？典型场景有两个。

- 你确实要靠真实 Chrome 的行为来复现问题。
- 你遇到站点对普通自动化环境更敏感，想尽量贴近真实用户环境。

扩展接入方式在仓库里已经写得很直白：

1. 打开 `chrome://extensions`
2. 开启开发者模式
3. 点击 `Load unpacked`
4. 选择 `browser-cli-extension/`

接上之后，再跑：

```bash
browser-cli status
```

你要看的是 extension 是否 connected，capability 是否 complete。不要只看“扩展图标亮了没亮”。真正决定 Browser CLI 是否会切过去的是协议和能力，不是图标的心情。

---

## 多 agent 使用时，先理解 `X_AGENT_ID`

如果你一个人手动用，通常不用管 `X_AGENT_ID`。如果你让多个 agent 共用 Browser CLI，这个环境变量就很关键。

你可以这样试：

```bash
X_AGENT_ID=agent-a browser-cli open https://example.com
X_AGENT_ID=agent-a browser-cli tabs

X_AGENT_ID=agent-b browser-cli open https://example.org
X_AGENT_ID=agent-b browser-cli tabs
```

这里最有意思的地方不是“能开两个标签页”，而是“每个 agent 只看见自己的页”。这让多个 agent 可以共用一个浏览器运行时，却不至于互相把活动标签页抢来抢去。

这对自动化特别重要。你不希望 agent A 正在填表，agent B 突然切走同一个活动页。`X_AGENT_ID` 就是在做这层隔离。

---

## 你可以按这个顺序真正学会使用它

如果你想把学习路线压成一条直线，我建议你按下面这七步走。

1. 先安装，跑通 `doctor`、`paths`、`read`。
2. 再学 `open`、`snapshot`、`click`、`html` 这四个交互命令。
3. 然后学会在每次页面变化后重新 `snapshot`。
4. 接着学 `verify-text`、`wait`、`wait-network`，把“点一下试试”变成“点一下并确认结果”。
5. 再写一个最小 `task.py`，让一串动作变成一次任务运行。
6. 然后补上 `task.meta.json`，把任务知识写清楚。
7. 最后再做 `automation publish`，把它变成可发布、可追踪的自动化版本。

这条路线像爬楼梯。你先学把门推开，再学在屋里走路。你不要站在楼下就讨论吊顶。

---

## 遇到问题时，先查这几样

浏览器自动化最容易卡住的地方，不在“语法”，而在“状态”。所以排错也要围着状态走。

先看环境：

```bash
browser-cli doctor
browser-cli paths
```

再看运行时：

```bash
browser-cli status
browser-cli tabs
```

如果命令连续异常，先不要急着杀进程，先试：

```bash
browser-cli reload
```

如果是元素点不到，先别怀疑人生，先重新抓：

```bash
browser-cli snapshot
```

如果是任务行为不对，先单独跑：

```bash
browser-cli task validate my_task
browser-cli task run my_task --set url=https://example.com
```

这几条命令像你工具箱里最常用的扳手。很多问题，拧这几下就知道症结在哪。

---

## 最后用一句话把它钉住

Browser CLI 最适合这样使用：你先用 `read` 探路，再用交互命令摸清页面，再把动作写进 `task.py`，最后把稳定版本发布成 `automation`。

这样做的好处很具体。你先拿到结果，再整理流程，最后沉淀版本。你不是一上来就搭一套大而全的自动化系统，而是先让浏览器替你完成一件小事，再把这件小事磨成工具。
