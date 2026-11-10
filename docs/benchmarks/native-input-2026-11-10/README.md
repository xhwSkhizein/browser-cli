# x.com 原生输入前后对比

旧逻辑：主线 733c80e 的 input_actions.js 与 page_runtime.js；新版：codex/native-extension-input，包含原生输入与临时焦点恢复。两次使用同一份 node/smoke-input.mjs，重载相应扩展后分别执行，未发帖、未重试。

环境：macOS，已登录真实 Chrome，extension 驱动；CSS 视口 1920×1118，DPR 2；开始及每个用例结束均为 hidden。

| 指标 | 修改前 | 修改后 |
|---|---:|---:|
| 通过率 | 3/24（12.5%） | 24/24（100.0%） |
| 输入命令数 | 42 | 42 |
| 输入请求 UTF-8 字节 | 6660 | 6660 |
| 输入响应 UTF-8 字节 | 11025 | 11025 |
| 42 次输入命令总耗时 | 272.78 ms | 1453.73 ms |
| 单条输入命令耗时中位数 | 5.28 ms | 22.31 ms |
| 含准备/观察的请求数 | 96 | 96 |
| 含准备/观察的请求字节 | 29512 | 29512 |
| 含准备/观察的响应字节 | 25766 | 25745 |

耗时是输入命令从发出到完整响应的实测耗时，不包括页面打开、准备、条件等待及测试观察。旧版多数命令没有实际效果，因此不能把旧版的较低耗时解读为完成任务更快。新版额外的浏览器内部处理不增加 Agent 必需调用。

| 用例（每项 3 次） | 修改前通过 | 修改后通过 | 修改前中位耗时 | 修改后中位耗时 |
|---|---:|---:|---:|---:|
| mouse-focus | 0/3 | 3/3 | 14.79 ms | 59.04 ms |
| tab-default | 0/3 | 3/3 | 7.22 ms | 101.48 ms |
| select-all | 0/3 | 3/3 | 6.45 ms | 22.59 ms |
| backspace-default | 0/3 | 3/3 | 9.41 ms | 58.89 ms |
| held-shift | 0/3 | 3/3 | 12.64 ms | 44.17 ms |
| move-down-up-focus | 0/3 | 3/3 | 18.66 ms | 71.30 ms |
| type-trusted | 0/3 | 3/3 | 5.86 ms | 36.58 ms |
| scroll-after-move | 3/3 | 3/3 | 10.11 ms | 32.91 ms |

请求/响应量是实际 daemon 线路上的完整换行 JSON UTF-8 字节数，含响应信封及元数据。准备/观察请求仅用于验收，单列统计；CLI preflight/path discovery 与最终关闭不在 all_requests 中。模型 token、模型回合及真实 Agent 工具调用量未测量。输入命令逐条的 action、请求及响应字节数均一致；观察响应少 21 字节来自 21 个 false 变成 true。

测试脚本 SHA-256：`c6634ed342a300b89aa80a87b7eece335176f0b08f4fccfa8af22109c965c910`。完整记录：[before-final.json](before-final.json)、[after-final.json](after-final.json)、[comparison.json](comparison.json)。

样本量有限，仅覆盖本次账号、平台、页面及 8 类输入；不代表所有 x.com 页面或完整 24h 摘要工作流。
