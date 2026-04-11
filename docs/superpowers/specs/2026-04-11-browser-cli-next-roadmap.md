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

- 验证 daemon 和浏览器后端在长时间、多轮次使用下是否稳定

重点：

- 长时间 daemon 常驻
- 反复 open / close / reload
- extension 断连 / 重连
- driver rebinding
- 大工件传输
- 多任务切换

完成标准：

- 没有持续累积的残留窗口、孤儿进程、明显资源泄漏
- 关键命令在多轮运行后仍然可靠
- 长时间运行的 smoke/soak 有稳定结果

### 5. Structural Cleanup

目标：

- 在不扩能力面的前提下，继续把当前实现整理成长期可维护结构

重点：

- extension background domain handlers 进一步细化
- Python driver helpers 继续按主题拆小
- tests 按 parity / lifecycle / task delivery 分类更清晰
- docs / guards / capabilities 与真实行为持续同步

完成标准：

- 后续新增能力不需要继续把逻辑堆回单文件
- 代码边界、测试边界、文档边界一致
- 维护成本持续下降

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
