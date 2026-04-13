# Browser CLI Long-Run Stability Design

Date: 2026-04-13
Status: Drafted for review
Repo: `/home/hongv/workspace/browser-cli`

## Summary

Browser CLI 现在已经具备可用的 runtime 基线：

- daemon、managed profile、extension mode、safe-point rebinding、`status`、`reload`、popup runtime presentation 都已存在
- extension 与 Playwright 的公开核心动作契约已基本收口
- runtime 的主要控制面已经不是“缺少某个单点能力”，而是“这些能力在长时间、多轮次使用下是否还能持续可信”

因此下一阶段不应继续把重点放在增加新动作或补更多零散 polish，而应明确回答一个更关键的问题：

- Browser CLI 的 runtime 是否已经达到可以长期日用的稳定性门槛

这项工作要解决的不是“偶尔跑通一次”。
它要解决的是：

- daemon 长驻后是否仍保持可控
- extension 断连、恢复、降级、rebind 后语义是否仍然诚实
- workspace/window/tab 状态是否会在多轮使用后逐步漂移
- 大工件传输与多轮命令执行后是否出现残留、泄漏或越来越难解释的 degraded state
- `status`、`runtime-status`、popup、`reload` 是否仍能构成一致的诊断与恢复路径

本 spec 的目标，是把这些问题定义成一组明确的 runtime stability contract、failure surfaces、validation loops 和 acceptance criteria，作为后续 implementation plan 的基础。

## Problem Statement

当前 Browser CLI 的主要风险已经从“功能是否存在”转向“运行时是否会随着时间和轮次变得不可信”。

现有问题不是单一 bug，而是长期运行下容易累积的不确定性，例如：

- daemon 常驻后，driver、workspace、tab registry、extension transport 之间是否会逐步失配
- extension 断连与恢复后，runtime 是否总能以一致方式暴露 pending rebind、`state_reset`、capability completeness 与当前 execution path
- workspace window 或 Browser CLI-owned tabs 是否会残留、漂移，或进入不易诊断的弱绑定状态
- screenshot / pdf / trace / video / network body 这类较大工件在多轮运行后是否会暴露 transport、assembly、cleanup 问题
- `status`、popup 与命令响应 `meta` 是否仍在陈述同一个 runtime 事实，而不是随着修补逐步漂移成多个解释路径

这些问题如果只在 ad hoc 任务里被动暴露，会导致几个后果：

- 稳定性问题无法被重复验证
- 失败会停留在“这次对话里遇到过”的层面，不能沉淀为长期约束
- runtime polish 会不断重复，但没有清晰的完成标准
- 后续 task/workflow 交付建立在不稳的 runtime 基础上

因此 Browser CLI 需要一个单独的 Long-Run Stability 阶段，用来定义：

- 哪些 runtime 行为在长期使用下必须保持可信
- 哪些失败属于可接受降级，哪些失败属于必须修复的问题
- 应通过哪些固定场景、观测信号和通过标准来证明稳定性

## Goals

- 定义 Browser CLI runtime 的长期稳定性契约，而不是继续扩公开能力面。
- 建立一组固定的 long-run smoke / soak 场景，覆盖 daemon、driver、extension transport、workspace、artifact 几类核心断点。
- 让长期运行中的降级、恢复、rebind、`state_reset`、workspace rebuild 等行为保持语义诚实且一致可观测。
- 让 `status`、`runtime-status`、popup、`reload` 成为同一套 runtime truth 与 recovery path 的不同呈现，而不是分叉解释。
- 把 recurring failure 沉淀成稳定的测试、guard、文档或可复现 case，而不是停留在一次性任务记忆里。
- 为后续 implementation plan 提供明确的验证矩阵、失败分级和完成标准。

## Non-Goals

- 不新增新的公开 page/action 能力。
- 不在这一阶段引入第二套 browser runtime 或新的 lifecycle control plane。
- 不要求跨 driver rebind 伪装成完全连续状态；必要时应继续诚实暴露 `state_reset`。
- 不把 `task.py` 或 workflow publish layer 的长期运行稳定性纳入本 spec；这些建立在 runtime 稳定性之上，后续单独处理。
- 不把这一阶段变成广泛的结构重构项目；仅处理直接影响长期稳定性的结构问题。
- 不以“人工运维步骤”替代产品化的 diagnosis / recovery contract。

## Options Considered

### 1. Test-Plan-Only Approach

直接围绕 soak matrix、操作序列、时长、观测项、通过门槛来定义本阶段。

Advantages:

- 执行导向明确
- 易于直接转成检查清单

Disadvantages:

- 容易把 spec 退化成测试列表
- 无法先定义 Browser CLI runtime 在长期运行下到底要保证什么契约
- 后续 plan 容易只补场景，不补 runtime truth 和 recovery path

Rejected.

### 2. Failure-Model-Only Approach

直接围绕 reconnect、rebind、workspace binding、artifact transport、残留进程/窗口等高风险断点来定义本阶段。

Advantages:

- 非常贴近真实 bug
- 风险覆盖面直观

Disadvantages:

- 容易演变成无界 bug bucket
- 缺乏固定验证闭环和完成标准
- 不利于后续 plan 排优先级

Rejected.

### 3. Runtime Contract Plus Validation Loop

先定义 Long-Run Stability 在 Browser CLI runtime 里的含义，再定义 failure surfaces、固定验证场景、观测信号、失败分级和 acceptance criteria。

Advantages:

- 既保留设计层的清晰边界，又能直接转成 implementation plan
- 能把 runtime truth、recovery path、soak 验证收束到同一套契约
- 最适合当前 Browser CLI 从 runtime polish 过渡到长期稳定性的阶段

Disadvantages:

- 需要同时触及 runtime semantics、测试组织和恢复路径验证

Chosen direction.

## Chosen Direction

这一阶段应把 Browser CLI Long-Run Stability 定义成：

- 一组 daemon-owned runtime 契约
- 一组围绕高风险断点组织的固定验证场景
- 一组明确的观测信号、失败分类与恢复验证闭环

换句话说，这项工作不是单纯补测试，也不是单纯做 runtime polish。
它是要回答：

- 哪些 runtime 行为在长期运行下必须持续可信
- 如何通过固定场景持续验证这些行为
- 当行为不满足时，Browser CLI 应如何诚实地暴露和收敛问题

## Stability Contract

Long-run stability 在 Browser CLI runtime 里，不等于“永不出错”。
它的含义是：

- 长时间、多轮次使用后，runtime 仍然保持可理解、可恢复、可验证
- 允许降级与重建，但不允许语义漂移、状态失真或残留持续累积

本阶段应把长期稳定性收敛到以下契约。

### 1. Lifecycle Honesty

Runtime 可以进入 `healthy`、`degraded`、`recovering`、`broken` 等状态，也可以发生 extension fallback、safe-point rebinding、workspace rebuild。

但这些变化必须保持语义诚实：

- 不允许 mid-command rebind
- 不允许把 cross-driver reset 伪装成完全连续
- 发生 driver 切换、状态重建、能力降级时，必须能通过命令 `meta`、`runtime-status`、popup 一致观察到
- `reload` 仍然是公开、统一、可预期的重置路径

换句话说，长期稳定性的第一要求不是“从不变化”，而是“变化必须被正确陈述”。

### 2. Execution Reliability Across Rounds

在 daemon 常驻、多轮命令执行下，核心运行路径必须保持可靠：

- 重复执行公开核心动作后，不应因为历史轮次累积而逐步失效
- extension reconnect、driver fallback、rebind、workspace rebuild 后，后续命令仍应回到可预测行为
- runtime 不应随着轮次增加而进入“偶尔能跑、但无法解释为什么失败”的状态

这要求 Browser CLI 在跨轮次运行时仍保持一套可信 execution path，而不是只在冷启动时表现正常。

### 3. Workspace And Tab Control Integrity

Browser CLI 对其 owned workspace、owned tabs、agent-scoped visibility 的控制，必须在长期运行下持续可信。

具体来说：

- workspace window 不应无界残留或逐步失去绑定可信度而无人察觉
- tab registry、active-tab 状态、busy-state 冲突语义不应在多轮切换后漂移
- 若控制完整性下降，runtime 必须进入可解释的 degraded/recovering 状态，并提供有限恢复路径，而不是继续假装控制仍然可靠

长期稳定不是要求 workspace 永不重建，而是要求 workspace control 的信号和边界始终可信。

### 4. Artifact And Transport Boundedness

较大工件与较重 transport 路径在长时间运行下必须保持有界行为。

包括但不限于：

- screenshot
- pdf
- trace
- video
- network bodies
- extension chunk assembly 与相关 cleanup

契约重点不是“所有工件都永远零成本”，而是：

- 工件生成与传输失败必须是显式失败，而不是静默破坏 runtime 状态
- 临时文件、会话状态、组装缓存、相关进程与 listener 资源必须可清理
- 多轮运行后不应持续积累成明显泄漏、孤儿状态或越来越慢的恢复路径

### 5. Observability And Recovery Consistency

长期稳定要求 Browser CLI 的诊断与恢复路径保持统一，而不是随着时间演化成多个部分正确、整体不一致的状态面。

因此：

- `status`、`runtime-status`、popup 必须继续建立在同一 runtime truth 之上
- recurring failure 必须能落入明确的观测信号，而不是只能靠日志猜测
- 当自动恢复不足时，有限的人类恢复动作必须清晰、收敛，并尽量复用既有公开路径，如 `reload`
- 无法自动恢复的失败，应优先转化为明确的 broken/degraded signal，而不是模糊的“下一次也许会好”

这保证长期运行问题可以被持续验证，而不是只在发生时临时解释。

## Failure Surfaces

Long-run stability 不应被定义成“任何失败都算同一种失败”。
Browser CLI 的长期运行风险主要集中在几类不同断点，它们需要被分别观察和验证。

### 1. Daemon Lifecycle Drift

长时间 daemon 常驻后，最基础的风险是 runtime lifecycle 本身开始漂移。

关注点：

- run-info、socket、实际 daemon 进程之间出现不一致
- daemon 仍存活，但内部 browser runtime、active driver、lifecycle state 不再可信
- repeated `reload`、`stop`、重新启动后，旧状态未被完整清理
- degraded 或 recovering 状态在多轮运行后长期停留，无法自然收敛或被明确打断

这类失败的核心问题不是单个命令失败，而是 Browser CLI 对“自己当前处于什么状态”的陈述开始不可信。

### 2. Extension Transport And Rebinding Instability

双 driver runtime 的主要复杂度集中在 extension transport 与 safe-point rebinding。

关注点：

- extension heartbeat 丢失、连接抖动、短时断连后的恢复行为
- required capabilities 不完整时的降级语义是否一致
- pending rebind 是否始终只在 safe point 生效
- rebind 后是否一致暴露 `state_reset`、driver reason、execution path 变化
- reconnect / fallback / restore 在多轮发生后，是否仍保持可解释且不自相矛盾

这类失败最危险的地方在于：系统表面还能跑，但 runtime truth 已经漂移。

### 3. Workspace And Tab Control Degradation

Browser CLI 的 agent-first 交互依赖它对 owned workspace 与 owned tabs 的稳定控制。

关注点：

- workspace window 丢失、残留、重复创建或绑定状态变 stale
- managed tabs、active tab、busy tab 状态在多轮 open / close / switch 后逐步偏离真实状态
- `X_AGENT_ID` 隔离下的可见 tab 语义在多轮切换后出现交叉污染
- workspace rebuild 后，Browser CLI 是否能重新回到可信控制状态

这类失败不一定马上体现为 crash，但会直接侵蚀 Browser CLI 对其工作面的控制完整性。

### 4. Artifact And Heavy Transport Degradation

较大工件与较重 transport 路径，在长期运行时最容易暴露“短期没问题、长期会积累”的问题。

关注点：

- screenshot / pdf / trace / video / network body 在多轮生成后是否出现传输、组装、落盘、清理异常
- extension chunk assembly、临时文件、artifact buffer 是否会累积残留
- 大工件失败后，是否只表现为单次显式失败，还是会污染后续 runtime
- repeated artifact runs 后，性能、恢复路径、资源占用是否明显恶化

这类失败面对应的是 boundedness，而不只是 correctness。

### 5. Diagnosis And Recovery Divergence

即使 runtime 本身可恢复，如果诊断面和恢复面逐步分叉，长期稳定性依然是不成立的。

关注点：

- `status`、`runtime-status`、popup、命令 `meta` 是否在陈述同一事实
- degraded、recovering、broken 的分类是否长期保持一致
- recurring failure 是否能进入明确的 signal，而不是只能靠日志猜测
- `reload`、popup reconnect、workspace rebuild 等恢复动作是否仍是清晰、有限、可预测的路径

这类失败的本质是 observability drift。它会让系统“部分能用”，但越来越难验证、难排障、难交付。

## Validation Matrix

Long-run stability 应通过少量固定、可重复的场景来验证，而不是依赖零散 ad hoc 任务。

本阶段建议先建立 5 组核心验证场景。每组场景都应有：

- 固定操作序列
- 关键观测信号
- 明确失败判定
- 对应的恢复预期

### Scenario 1: Daemon Residency Loop

目的：

- 验证 daemon 常驻、多轮命令执行后，runtime 基础状态是否持续可信

操作序列：

- 启动 daemon 并保持常驻
- 在同一 daemon 生命周期内重复执行多轮核心命令
- 期间周期性调用 `status` / `runtime-status`
- 中途插入一次或多次 `reload`，验证重置后是否能重新回到稳定状态

重点命令类型：

- open / new-tab / tabs / switch-tab / close-tab
- read-page / html / snapshot
- screenshot 或其他轻量 artifact
- status / reload

关键观测信号：

- daemon pid、socket、run-info 是否持续一致
- active driver 是否可解释
- degraded / recovering 状态是否会异常滞留
- reload 后是否回到可预测状态
- 是否出现残留 workspace、孤儿进程或无法解释的 broken state

失败判定：

- 多轮执行后 runtime 状态越来越不稳定，但没有明确 signal
- reload 无法稳定恢复基础运行状态
- daemon 表面存活，但 `runtime-status` 与实际行为明显不一致

### Scenario 2: Extension Disconnect / Reconnect Loop

目的：

- 验证 extension transport 抖动、断连、恢复时的降级与恢复语义

操作序列：

- 在 extension mode 可用的前提下执行一组正常命令
- 人为制造 extension 断连、短时不可用、再次连接
- 在断连前、断连中、恢复后分别执行命令并观测 runtime
- 重复多轮，覆盖“断开后继续运行”和“恢复后回切 extension”两种路径

关键观测信号：

- extension connected / capability_complete
- pending rebind target / reason
- active driver 变化
- 命令 `meta` 中的 driver reason、`state_reset`
- popup / status / runtime-status 对当前 execution path 的解释是否一致

失败判定：

- mid-command rebind
- 已经 fallback 或 restore，但没有对应 signal
- 同一时刻 `status`、popup、命令 meta 对当前 driver 路径给出冲突描述
- reconnect 多轮后 runtime truth 逐步漂移

### Scenario 3: Workspace / Tab Lifecycle Loop

目的：

- 验证 Browser CLI 对 owned workspace 与 owned tabs 的长期控制完整性

操作序列：

- 重复执行 open / new-tab / switch-tab / close-tab / page-reload
- 覆盖 workspace rebuild、tab 关闭重开、busy tab 冲突恢复等情况
- 在多轮操作后检查 workspace binding 与 tab registry 是否仍可信

关键观测信号：

- workspace binding state
- workspace window id 与 managed tab count
- active tab / busy tab count
- tab visibility 与 `X_AGENT_ID` 相关状态
- rebuild 后 runtime 是否回到 trusted binding

失败判定：

- workspace window 或 managed tabs 无界残留
- active tab / busy tab / visible tabs 状态与实际行为脱节
- rebuild 后仍停留在不可信状态，或需要手工清理才能恢复

### Scenario 4: Artifact Stress Loop

目的：

- 验证较大工件与较重 transport 路径在多轮运行下是否保持有界行为

操作序列：

- 在同一 runtime 内多轮执行 screenshot / pdf / trace / video / network body 相关操作
- 混合成功与人为失败路径
- 检查 artifact 生成后、失败后、重复运行后的 runtime 状态与清理结果

关键观测信号：

- artifact 命令成功率与显式错误率
- 相关临时文件、buffer、assembly 状态是否清理
- artifact 失败后 runtime 是否仍可继续执行后续命令
- repeated runs 后是否出现明显性能恶化或恢复成本上升

失败判定：

- 单次 artifact 失败污染后续 runtime
- 临时状态、chunk assembly 或文件残留持续累积
- 多轮运行后 artifact 路径明显变脆，但没有配套 signal

### Scenario 5: Diagnosis / Recovery Consistency Loop

目的：

- 验证诊断与恢复面本身不会随着长期运行而漂移

操作序列：

- 在 healthy、degraded、recovering、broken 几类典型状态下分别采样
- 对每类状态同时检查命令 `meta`、`runtime-status`、`status`、popup
- 对每类状态执行允许的恢复动作，如 reconnect、workspace rebuild、reload
- 检查恢复动作后的状态收敛是否符合预期

关键观测信号：

- overall_state / summary_reason / recovery_guidance
- available actions
- command `meta` 中的 runtime note、driver reason、`state_reset`
- reload / reconnect / rebuild 后的状态迁移

失败判定：

- 不同诊断面解释冲突
- recovery action 的可用性与实际行为不一致
- runtime 已进入 broken/degraded，但没有清晰 guidance
- 同一类失败每次表现不同，无法归入稳定语义

## Observability And Recovery

Long-run stability 不只是验证“会不会出问题”，还要验证“出问题时 Browser CLI 能否用统一方式说明问题并提供收敛恢复路径”。

本阶段应明确以下观测与恢复要求。

### 1. One Runtime Truth Path

所有长期运行相关诊断，都应建立在同一条 runtime truth path 上，而不是多个表面各自推断。

要求：

- 命令 `meta` 负责说明“这次命令刚刚发生了什么”
- `runtime-status` 负责说明“runtime 当前处于什么状态”
- `status` 负责把本地 runtime 检查与 `runtime-status` 渲染为人可读诊断
- popup 负责复用同一 runtime 解释层进行观察与轻恢复

验证重点：

- 同一时刻，这几个表面对 active driver、pending rebind、`state_reset`、workspace binding、overall state 的表达不能互相冲突
- 新增 runtime 语义时，应优先进入 daemon-owned truth path，而不是先在某个 UI 或命令层做局部解释

### 2. Required Long-Run Signals

为了让 soak / smoke 可验证，以下信号必须持续可用且语义稳定：

- active driver
- extension connected
- capability completeness / missing capabilities
- pending rebind target / reason
- `state_reset` 与最近一次 transition 信息
- workspace binding state
- workspace tab / busy tab 核心摘要
- top-level `overall_state`
- `summary_reason`
- `recovery_guidance`
- allowed recovery actions

验证重点：

- 这些信号在 healthy、degraded、recovering、broken 几类状态下都能得到
- 信号缺失本身应被视为稳定性问题，而不是被默默忽略
- 新 failure mode 若反复出现，应优先补成稳定 signal，而不是只补日志

### 3. Bounded Recovery Surface

恢复路径必须保持有限、明确、可预测，不能随着长期运行问题增加而扩散成无边界的人肉运维流程。

本阶段认可的恢复面应优先收敛到：

- 自动 safe-point rebind
- popup reconnect-extension
- popup rebuild-workspace-binding
- top-level `browser-cli reload`

要求：

- 每种恢复动作的适用前提要清晰
- 每种恢复动作执行后，都应能从 runtime 信号里看到状态迁移
- 恢复失败时，应升级为明确的 degraded / broken，而不是停留在模糊中间态
- 不应把频繁需要手工杀进程、手工关窗口、手工清理残留视为可接受常态

### 4. Failure Classification

长期运行中的失败需要按恢复性和影响范围分类，否则 soak 结果无法指导后续实现优先级。

建议分类：

- `recoverable`
  - 当前命令或当前状态失败，但已有明确 runtime signal 与收敛恢复路径
- `repair-needed`
  - 可以观察和复现，但当前恢复路径不稳定，或失败会持续再现
- `contract-breaking`
  - runtime truth 出现冲突、失真或静默漂移，破坏产品契约
- `resource-leaking`
  - 残留窗口、孤儿进程、临时文件、assembly/buffer 状态持续累积

验证重点：

- soak 发现的问题应进入这些分类之一
- `contract-breaking` 与 `resource-leaking` 默认不应被当作“可接受偶发失败”
- 同类失败重复出现时，应优先变成 test/guard/doc contract，而不是继续临时处理

### 5. Recovery Verification Loop

恢复动作本身也必须被验证，而不是默认认为存在按钮或命令就算完成。

每个恢复路径至少需要验证：

- 触发前的前置状态可识别
- 触发后状态迁移符合预期
- 触发失败时信号更明确，而不是更模糊
- 恢复后后续命令能重新回到可预测行为

这意味着本阶段的目标不是“列出恢复动作”，而是证明这些恢复动作在长期运行里仍然可信。

## Acceptance Criteria

Long-Run Stability 阶段完成，不以“跑过几次手工检查”为标准，而以固定场景下的可重复稳定性为标准。

本阶段建议至少满足以下完成条件。

### 1. Fixed Stability Loops Exist

- 已建立一组固定的 runtime long-run smoke / soak 场景
- 这些场景覆盖 daemon lifecycle、extension reconnect / rebind、workspace / tab lifecycle、artifact stress、diagnosis / recovery consistency
- 场景可以重复执行，而不是依赖一次性手工操作记忆

### 2. Runtime Truth Remains Consistent

- `status`、`runtime-status`、popup、命令 `meta` 对核心 runtime 状态保持一致解释
- active driver、pending rebind、`state_reset`、workspace binding、overall state 等关键语义不出现长期漂移
- 新增或修复的 runtime 语义优先进入共享 truth path，而不是局部表面先行分叉

### 3. Recovery Paths Are Real, Not Nominal

- safe-point rebind、extension reconnect、workspace rebuild、`reload` 都经过长期运行场景验证
- 恢复动作触发前后有明确状态迁移
- 恢复失败时能升级为更清晰的 degraded / broken，而不是进入更模糊状态

### 4. No Persistent Unbounded Residue

- 多轮运行后不存在持续累积的孤儿进程、残留 workspace window、明显异常的 managed tab 残留
- artifact 相关临时状态、assembly/buffer、落盘产物清理保持有界
- 多轮运行不会稳定地产生越来越差的 degraded state 或恢复成本

### 5. Recurring Failures Are Captured Durably

- soak 中暴露的 recurring failure 已进入明确分类
- 主要失败要么被修复，要么被转成稳定 signal、测试、guard、文档化边界
- 不再接受“知道有这个问题，但只存在于对话记忆里”的状态

### 6. Runtime Is Stable Enough For The Next Layer

- browser runtime 已达到可支撑后续 task/workflow 长期运行验证的门槛
- 后续 task/workflow 稳定性工作不需要继续为基础 runtime truth 或恢复语义兜底

## Execution Sequence

为了避免 Long-Run Stability 退化成一组无序修 bug，本阶段应按固定顺序推进。

### Phase 1: Define The Stability Harness

先建立最小可重复的验证骨架：

- 固定 long-run 场景清单
- 每个场景的操作序列
- 每个场景采集的核心 runtime 信号
- 失败分类与记录方式

这一阶段先解决“如何稳定复现与观察”，而不是先追求把所有问题修完。

### Phase 2: Validate Runtime Truth Path

优先验证并修正 runtime truth 本身是否一致：

- `runtime-status` 是否覆盖长期运行所需核心信号
- `status`、popup、命令 `meta` 是否仍建立在同一解释路径上
- rebind、`state_reset`、workspace binding、recovery guidance 是否有稳定语义

原因：

- 如果 truth path 自己不稳定，后续 soak 结果会缺乏可信度

### Phase 3: Run The Core Stability Loops

在 truth path 足够可靠后，系统化跑核心场景：

- daemon residency loop
- extension disconnect / reconnect loop
- workspace / tab lifecycle loop
- artifact stress loop
- diagnosis / recovery consistency loop

这一阶段的目标是暴露 recurring failure，而不是立即追求所有边缘情况全覆盖。

### Phase 4: Close Contract-Breaking And Leaking Failures

优先处理两类最高价值问题：

- `contract-breaking`
- `resource-leaking`

这些问题会直接破坏 Browser CLI runtime 的可信性，不应后置到“以后再收拾”。

对 `recoverable` 与 `repair-needed` 问题，则按是否阻塞核心场景通过来决定优先级。

### Phase 5: Re-run And Tighten Acceptance

在主要问题收敛后，重新跑固定场景，并确认：

- 失败是否已消失或被降级为已知边界
- recovery path 是否仍然成立
- signals 与 docs/guards 是否跟上新的稳定语义
- acceptance criteria 是否真正满足

只有在这一步通过后，Long-Run Stability 才算完成，并可转入下一层 task/workflow 长期运行验证。
