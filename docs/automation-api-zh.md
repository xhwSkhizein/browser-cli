# 可重复截图与 Node.js 自动化

`browser-cli screenshot` 可以指定捕获范围、视口和图片像素比。需要把语言、时区、字体和页面 DPR 一并固定时，用 `batch --context`：后台服务会在托管 Chrome 里创建一个临时上下文，依次执行动作，最后关闭上下文。

## 控制截图

```bash
# 当前视口，以每个 CSS 像素对应两个图片像素的密度输出
browser-cli screenshot viewport.png --dpr 2

# 整页：直接捕获页面矩形，保留现有响应式布局
browser-cli screenshot full.png --page-range full

# 从页面左上角算起，截取一个矩形，坐标单位为 CSS 像素
browser-cli screenshot crop.png --clip 40,120,800,600 --dpr 2

# 临时使用精确视口，捕获后恢复原视口和滚动位置
browser-cli screenshot fixed.png --viewport-width 1280 --viewport-height 720 --dpr 2
```

`--full-page` 是 `--page-range full` 的兼容写法。矩形与整页捕获不能合用。视口宽高必须一起提供，范围是 1–16384；DPR 范围是 0.1–8。PNG 和 JPEG 均返回文件中实际记录的像素尺寸。

结果保留 `ok/data/meta`，并在 `data` 中提供：

```json
{
  "path": "/absolute/path/fixed.png",
  "screenshot_size": {"width": 2560, "height": 1440},
  "capture": {
    "page_range": "viewport",
    "clip": {"x": 0, "y": 0, "width": 1280, "height": 720},
    "viewport": {"width": 1280, "height": 720},
    "device_scale_factor": 2,
    "page_dimensions_unchanged": true,
    "before": {},
    "after": {}
  }
}
```

实际的 `before`、`after` 含视口宽高、页面宽高、滚动位置和页面 DPR。截图动作会等待字体就绪，并验证前后几何信息一致；验证失败时返回错误，不保存这次截图。临时视口在捕获异常时也会恢复。页面若自行改变尺寸，例如动画、延迟内容或 resize 回调产生了持久变化，这次截图会报错。

截图的 `--dpr` 控制输出图片密度，并保留页面的 `window.devicePixelRatio`。需要让页面代码、媒体查询也看到指定 DPR 时，把 `device_scale_factor` 放在下文的上下文设置里。相对输出路径以 `browser-cli paths` 给出的 `artifacts_dir` 为基准；绝对路径直接使用。

托管 Chrome 对超出可见视口的区域采用实际滚动、逐片捕获和 Pillow 像素合成，避免 Chrome 整页接口持续隐藏滚动条。结束后恢复原滚动位置，前后几何校验仍然生效；合成保留 ICC 配置，PNG/JPEG 底部内容也有像素回归。分片按页面滚动时的实际渲染合成，固定定位和吸附元素遵循页面自身的滚动行为。分片输出最多 6400 万像素、256 片，超出时请分区截图。

扩展模式需要新版扩展提供 `screenshot-controls` 能力。旧扩展会收到明确的重新加载提示，不会悄悄忽略新参数。

扩展截图和 `resize` 会计入 Chrome 标签页自身的浏览器缩放，例如 90%，以保持请求的 CSS 视口尺寸和页面 DPR；用户的浏览器缩放设置保持原值。布局尚未稳定或精确尺寸无法应用时会明确报错，并恢复原视口。

## 在临时上下文内完成一组动作

创建 `commands.json`：

```json
[
  {"action": "open", "args": {"url": "https://example.com"}},
  {"action": "screenshot", "args": {"path": "comparison.png", "full_page": true}}
]
```

创建 `context.json`：

```json
{
  "viewport_width": 1280,
  "viewport_height": 720,
  "device_scale_factor": 2,
  "zoom": 1,
  "locale": "zh-CN",
  "timezone_id": "Asia/Shanghai",
  "font_family": "Arial",
  "font_files": []
}
```

执行：

```bash
browser-cli batch --file commands.json --context-file context.json --result-mode last
```

也可直接传 `--commands '<JSON 数组>' --context '<JSON 对象>'`。`--context '{}'` 使用固定默认值：1440×1024、DPR 1、缩放 1、`en-US`、`UTC`、`Arial`。省略 `--context` 会在当前共享浏览器中执行。

上下文独立保存页面、Cookie、缓存和站点存储，生命周期限于这一条 `batch` 的服务端执行。动作失败或服务端任务被取消时同样关闭；正常返回时 `data.context.closed` 为 `true`。服务端取消时会先关闭临时上下文，再等待正在进行的浏览器调用收尾。客户端超时或连接断开不会取消服务端执行；批量继续运行，并在结束后关闭上下文。视口在上下文中固定，`resize` 或截图的临时视口不能换成其他尺寸。不同尺寸应分两次运行。

为应用指定的字体与缩放样式，临时上下文启用 `bypass_csp`。

`zoom` 范围是 0.25–5，通过 CSS `zoom` 固定页面布局缩放，结果中标明 `zoom_method: "css"`。字体设置会覆盖文档元素及伪元素的字体。要跨机器比较，请使用相同版本的 Chrome、相同平台，以及相同的字体文件，例如：

```json
{"font_family":"ComparisonFont","font_files":[{"family":"ComparisonFont","path":"/absolute/path/comparison.woff2"}]}
```

每个文件最多 10 MiB，最多八个文件。后台会把字体内容嵌入上下文，后续页面无需访问原字体 URL。系统字体名称仍依赖本机安装情况；封闭的 Shadow DOM 或页面自行修改样式也可能影响渲染。

临时上下文使用后台管理的 Chrome 进程。当前使用扩展驱动时，后台会启动托管后端供临时上下文使用，共享工作区继续使用扩展驱动，原有标签页及页面内存状态得以保留。正常隔离运行的 `meta.state_reset` 和 `data.state_reset` 均为 `false`；只有共享驱动确实发生切换时才报告 `true`。临时上下文拥有独立存储，不继承扩展页面的登录状态。

## 从 Node.js 调用

安装或升级后先执行 `browser-cli reload`，让后台服务加载同一版本的接口。

Node.js 18+ 可直接导入随 Python 包安装的 ESM 客户端，无需 npm 依赖。下面的发现步骤只运行一次；浏览器动作通过本地套接字发送。

```js
import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

const { data: paths } = JSON.parse(
  execFileSync('browser-cli', ['paths', '--json'], { encoding: 'utf8' }),
);
const { BrowserCliClient } = await import(pathToFileURL(paths.node_client).href);
const browser = new BrowserCliClient({ home: paths.home, socketPath: paths.socket_path });

const result = await browser.batch([
  { action: 'open', args: { url: 'https://example.com' } },
  { action: 'screenshot', args: { path: 'example.png', full_page: true } },
], {
  context: { viewport_width: 1280, viewport_height: 720, device_scale_factor: 2 },
  resultMode: 'last',
});

if (!result.data.success) throw new Error(JSON.stringify(result.data));
console.log(result.data.results[0].data);
```

源码仓库也可从 `node/browser-cli-client.mjs` 导入。默认情况下，每个客户端有独立的 Agent ID；设置 `agentId` 或 `X_AGENT_ID` 可以复用同一组标签页。`request(action, args)` 返回完整的 daemon 响应，`open`、`snapshot`、`screenshot`、`close` 便利方法返回 `data`。`status()` 只查询已有 daemon 的运行状态。

客户端通过 `browser-cli paths --json` 发现实际套接字路径，因此支持长配置路径触发的短套接字路径。首次连接遇到服务未启动时，客户端会用一次无副作用的批量状态查询启动服务；动作执行期间断线或超时不会自动重放。默认响应超时为 120 秒，响应上限为 32 MiB，可通过构造参数 `timeoutMs`、`maxResponseBytes` 调整。超时表示客户端停止等待，服务端可能仍在执行。传入 `{startIfNeeded:false}` 可禁止自动启动。

每次请求发送浏览器动作前，客户端都先用只读 `runtime-status` 核对 `data.runtime_version`，包括直接指定 `socketPath` 的情况。后台服务缺少版本信息或与客户端不兼容时，抛出 `BrowserCliError`，`code` 为 `DAEMON_INCOMPATIBLE`，`payload` 包含预期版本和实际版本，并提示升级 Browser CLI 后执行 `browser-cli reload`。客户端不会自动重载正在运行的旧服务。请求也携带预期运行版本，新版服务会在执行动作前再次核对；响应的 `meta.runtime_version` 标明处理请求的版本。

`batch` 接受 1–500 个动作，默认遇错停止。批量会等待已在执行的浏览器动作和异步 `read`，运行期间其他浏览器动作排队；只读运行状态、`run-status`、`run-logs` 和 `run-cancel` 仍可随时调用。`stopOnError:false` 对应 CLI 的 `--continue-on-error`。`resultMode` / `--result-mode` 的取值为 `all`、`last`、`summary`：分别保留全部结果、最后执行的结果、失败结果。每个结果保留 `index`、`ok`、`data`、`meta` 和机器可读错误码。批量结果同时包含 `success`、`completed`、`completed_count`、`total_count`、`failed_indices`、`errors`；错误明细在所有返回模式下均保留。`ok:true` 表示批量请求已处理，步骤是否全部成功看 `data.success`。

单个动作失败会抛出 `BrowserCliError`，其中 `code` 和 `payload` 保留原始错误；批量步骤失败留在批量结果中，便于程序保存部分结果。批量中不接受嵌套批量、停止服务、重建工作区或后台异步运行管理动作。Python 任务也可用 `BrowserCliTaskClient.batch(...)` 调用同一接口。

## 读取健康状态

```bash
browser-cli status --json
browser-cli doctor --json
```

两者都提供 `data.health.service`、`extension`、`config_dir`、`managed_profile`、`output_dir`。目录项包含路径、存在性、可写性、是否可创建和 `checked_by: "caller"`。目录检查会做临时写入探测，随后删除探测文件，且不会创建尚不存在的配置目录。

`status` 的 `status_scope` 为 `runtime`，原有 `status` 仍来自后台服务的状态判断。`doctor` 的 `status_scope` 为 `environment`，`overall_status` 汇总安装和环境检查。比如后台服务与扩展都正常，但调用命令的沙箱无权写入默认配置目录时，`status` 可以是 `healthy`，同时 `health.managed_profile.status` 是 `fail`。这表示已有服务可用，而当前进程缺少写入配置目录的权限。

## 从安装包验收

已有后台服务和扩展连接正常时，可以运行真实扩展截图验收：

```bash
node node/smoke-extension.mjs runs/runtime-api-acceptance .venv/bin/browser-cli
```

它会核对 `screenshot-controls`，创建专用测试标签页，验证原生视口恢复、整页、矩形、临时视口、不同 DPR 和 JPEG，并用图片像素确认矩形坐标正确。完成后关闭测试标签页，把截图和 JSON 报告写入指定目录。

构建完成后，可在仓库之外的临时环境检查安装和首次调用：

```bash
uv build --no-sources --clear
uv run python scripts/smoke_installed_wheel.py dist/<构建出的文件名>.whl
```

脚本先检查浏览器启动权限，再创建临时虚拟环境、安装 wheel、把对应 Playwright 版本的 ffmpeg 准备到独立缓存、发现 Node 客户端和套接字、启动独立后台，并完成隔离截图和失败结果处理。Chrome 使用本机稳定版。测试结束后停止独立后台并清理临时文件；当前后台使用不同的目录和端口。`BROWSER_CLI_HOME` 同时决定托管配置目录、套接字和产物的位置。
