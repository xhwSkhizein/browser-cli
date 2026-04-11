# Extension Driver 对齐状态

本文档描述当前 `extension_driver` 与 `playwright_driver` 的对齐状态，以及仍然保留的收尾项。

## 当前状态

- daemon action catalog 仍然是唯一产品能力真相
- `PlaywrightDriver.__getattr__` 与 `BrowserService.__getattr__` 保持移除状态
- `ExtensionDriver` 已拆成 facade + `_extension/` domain helpers
- extension background 已拆成 orchestrator + domain handlers
- `trace-*` 与 `video-*` 已进入 extension required capabilities
- `status` 与 extension popup 都会显示 required capability 完整度

## 已完成的关键对齐

- 页面与标签生命周期
- semantic ref 驱动的核心交互与验证
- console / network / cookies / storage
- screenshot / pdf
- trace-start / trace-chunk / trace-stop
- video-start / video-stop
- deferred video save on `close-tab` / `workspace-close` / daemon `stop`
- extension artifact chunk transport

## 当前保留差异

下面这些不是公开动作面的缺失，而是实现层面的已知差异：

- extension trace 目标是“CLI 与工件兼容”，不是 Playwright Trace Viewer 的字节级兼容
- extension video 改为基于 CDP screencast 与 offscreen encoder，输出仍然是 deferred `.webm`，但它是帧采样视频而不是系统级实时录屏
- extension artifact 生成链路与 Playwright 不同，但对外 contract 保持一致

## 仍需持续关注的收尾项

- 继续扩大真实 Chrome smoke 覆盖，尤其是 trace/video 在真实页面上的稳定性
- 如有必要，再把 extension background domain handlers 继续细化为更小的内部文件
- 维持 capability、docs、guards 与真实行为同步，避免重新把 trace/video 降级成 deferred items
