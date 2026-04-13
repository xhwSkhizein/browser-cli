# Browser CLI Next Roadmap

## Summary

`browser-cli` 现在的底层浏览器能力已经基本成型：

- managed profile mode 与 extension mode 双后端架构已落地
- daemon / tabs / `X_AGENT_ID` / semantic ref / JSON contract 已收口
- extension driver 已基本对齐 playwright driver 的公开核心动作面
- `status` / `reload` / popup / guards 已建立起基本的运行态治理

接下来的重点不应再是继续堆 driver 能力，而应转向：

- 用真实任务验证交付链是否稳定
- 把 `task.py + task.meta.json + workflow.toml` 这条用户交付路径补完整
- 把 runtime 生命周期与长期运行稳定性打磨到日用级别

## Roadmap

### 1. Real Task Validation

目标：

- 选取 2-3 个真实网站任务
- 完整跑通 `explore -> task.py + task.meta.json`
- 验证 extension mode、semantic ref、popup 状态、Agent 使用体验是否足够稳定

建议任务类型：

- 通用页面内容抓取
- 登录后页面信息提取
- 懒加载 / 滚动加载页面采集

完成标准：

- 每个任务都能稳定重放
- task 产物能脱离对话独立执行
- 暴露出来的 parity 或 runtime 问题被收敛记录

### 2. Workflow Publish Layer

目标：

- 把已经稳定的 `task.py` 提升为用户侧可交付的 `workflow.toml`
- 实现 workflow 的运行、调度、输出、hooks 包装

范围：

- `workflow validate`
- `workflow run`
- `workflow.toml` 中的 schedule / outputs / hooks 约定
- 任务参数注入与默认值覆盖

完成标准：

- 至少有 1-2 个真实 task 能发布成 workflow
- workflow 层不复制任务逻辑，只做包装
- 用户可以明确配置何时运行、输出到哪里、执行后做什么

### 3. Real-Browser Runtime Polish

目标：

- 把 `browser-cli` 从“能跑”提升到“可长期日用”

重点：

- `status` 信息继续补强
- `reload` / `stop` / reconnect 行为更可预期
- popup 的状态展示与手动恢复路径更清晰
- workspace window / tab 生命周期更稳
- extension reconnect / safe-point rebinding 进一步打磨

完成标准：

- 出问题时可以主要依赖 `status` 和 popup 快速定位
- 不再频繁出现残留 workspace 或难以解释的 runtime 状态
- 长时间运行下，daemon 和浏览器窗口行为保持可控

### 4. Long-Run Stability

目标：

- 不是继续补新能力，而是验证 Browser CLI 在长时间、多轮次、真实使用节奏下是否仍然可信
- 把 soak 过程中暴露的生命周期问题收敛成可观测、可复现、可恢复的运行时行为

重点：

- 建立一组固定的长运行场景，而不是只靠一次性 smoke：
  - daemon 长驻 + 多轮命令执行
  - 反复 `open / close / reload / page-reload`
  - extension 断连 / 重连 / 延迟恢复
  - safe-point rebinding 与 `state_reset` 暴露
  - 大工件传输，如 screenshot / pdf / trace / video / network bodies
  - 多任务或多 Agent 切换下的 tab / workspace 控制稳定性
- 每个高频失败都要落到明确收敛路径：
  - `status` / `runtime-status` 能解释当前处于什么生命周期状态
  - popup 能提供有限但可靠的人工恢复入口
  - `reload` 能作为统一的重置路径，而不是回到手工杀进程
  - 真正 recurring 的失败要沉淀为 soak case、integration case 或 guard，而不是只留在对话记忆里
- 长运行关注的是“运行态诚实性”，不要求伪装成完全连续：
  - rebind 仍可发生，但必须只在 safe point 发生
  - cross-driver continuity 不应伪装成无状态切换，必要时明确暴露 `state_reset`
  - extension 降级、workspace 重建、artifact 失败都要有一致的机器可读信号

完成标准：

- 有一组可重复运行的 long-run smoke / soak 场景，覆盖 daemon、driver、workspace、artifact 几类核心断点
- 多轮运行后没有持续累积的残留窗口、孤儿进程、明显资源泄漏或不断恶化的 degraded state
- `status`、`runtime-status`、popup、`reload` 对长期运行问题给出一致解释，而不是各自发明状态语义
- 长运行中暴露的主要问题，要么被修复，要么被显式降级并文档化为当前已知边界

### 5. Structural Cleanup

目标：

- 在不扩公开能力面、不打断真实任务交付节奏的前提下，把当前实现整理成更适合长期维护和继续演进的结构
- 让代码边界、测试边界、文档边界、guard 边界逐步重新对齐，而不是继续依赖少数大文件承载越来越多的产品语义

重点：

- 结构收口应围绕当前已经暴露出复杂度的热点，而不是做泛化重构：
  - extension background handlers 按 domain 继续细化，减少 `background.js` 持续吸收产品行为
  - Python driver helpers 与 daemon/browser lifecycle 相关辅助逻辑继续按主题拆小，避免 driver parity、lifecycle、artifact、workspace 语义互相缠绕
  - runtime presentation、capability reporting、workspace control 这类已成为产品契约的逻辑，应保持单一解释路径，避免 CLI、popup、driver 再次各自复制判断
- 测试结构要服务于产品边界，而不是只跟着文件名增长：
  - parity 测试明确回答 extension 与 Playwright 是否仍满足同一公开契约
  - lifecycle 测试明确覆盖 status / reload / reconnect / rebind / state_reset 等运行态语义
  - task delivery / workflow 测试明确覆盖从 `task.py` 到 `workflow.toml` 的真实交付链
- docs、guards、capabilities 要继续与真实行为同步：
  - 新增或调整产品契约时，同步更新 AGENTS、相关 specs、guards
  - extension capability 声明、daemon runtime 暴露、popup 展示逻辑不能长期漂移
  - recurring failure 的 durable lesson 应写回导航文档或 guard，而不是停留在一次性修复里

完成标准：

- 后续新增能力时，不需要继续把产品逻辑堆回 `background.js`、单个 driver 文件或单个 daemon 大文件
- 测试目录和测试命名能更直接映射 parity、lifecycle、task delivery 这些真实产品维度
- docs、guards、capabilities 与运行时行为保持同步，减少“代码已变、文档和约束没跟上”的回归源
- 结构整理以持续小步进行，不应成为打断 Real Task Validation、Workflow Publish、Long-Run soak 收敛的独立大项目

## Recommended Sequence

建议顺序固定为：

1. Real Task Validation
2. Workflow Publish Layer
3. Real-Browser Runtime Polish
4. Long-Run Stability
5. Structural Cleanup

原因：

- 真实任务最能暴露当前系统是否真的可交付
- workflow 应建立在已验证稳定的 task 之上
- runtime polish 和长期稳定性应服务于真实使用，而不是先于真实使用空转
- 结构整理应在主要产品路径验证后持续进行，而不是再次打断交付节奏

## Immediate Next Step

下一步最值得做的事情是：

- 选择一个真实站点任务
- 用 `[$browser-cli-explore-delivery](/Users/hongv/workspace/m-projects/browser-cli/skills/browser-cli-explore-delivery/SKILL.md)` 跑完整探索链
- 先稳定产出 `task.py + task.meta.json`
- 暂不急于发布 `workflow.toml`

这会直接验证当前系统是否已经到达“可持续交付”的阶段。
