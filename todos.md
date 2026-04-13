# Browser CLI 技术债务与优化 TODO

## 问题记录

### 剩余真实任务样例与 automation 交付层仍未完全收口

**状态**: 待修复  
**优先级**: 中  
**发现时间**: 2026-04-14

#### 问题描述

仓库里已经有真实站点 task；其中 `douyin_video_download` 已进入
`automation.toml + automation publish + docs/examples/smoke` 这条正式交付路径，
但 `karpathy_nitter_latest_five` 还没有收口到同样的交付层。

#### 根本原因

1. **交付链仍偏向少量样例**: 当前 automation 相关文档和样例虽然已纳入 Douyin，但真实站点 automation 例子仍然偏少
2. **剩余真实任务未收口**: `karpathy_nitter_latest_five` 仍停留在 task-first 状态
3. **后续样例梯度仍不完整**: 仓库还缺“第二个真实站点 automation 样例”来证明这不是单点成功

#### 影响

- 用户虽然能看到一个真实站点 publish 样例，但仍难判断这是不是可复用的普遍路径
- automation publish 层仍缺第二个真实站点任务作为端到端对照样本
- 后续 agent 仍需要花时间判断下一步该继续补样例还是回到底层能力

#### 相关代码

- `tasks/douyin_video_download/task.py`
- `tasks/karpathy_nitter_latest_five/task.py`
- `tasks/douyin_video_download/automation.toml`
- `tasks/interactive_reveal_capture/automation.toml`
- `tasks/lazy_scroll_capture/automation.toml`
- `docs/examples/task-and-automation.md`
- `README.md`
