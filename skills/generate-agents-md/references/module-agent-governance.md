# Dispatcher 与稳定模块维护 Agent 协议

仅在用户要求模块对应长期维护 Agent、调度会话转派、跨会话继承需求，或仓库已有稳定模块 Agent 体系时加载本文件。它定义长期治理契约，不登记当前 thread/session/run ID。

## 0. 交付保证模式

- 默认 `delivery-first-local-coordination`：用封闭结构的本地协调 receipt/租约绑定 module、Agent/run、owned paths、候选与证据哈希，并保留单写者、文件锁、CAS 和原子替换；无需签名或外部宿主校验，不得把它描述为安全证明。
- 可选 `strict-security`：仅在高风险/合规映射或人工明确选择时，额外要求宿主证明或签名租约。不得因严格模式基础设施缺失自动阻塞默认交付链。
- 所有待人工确认项统一进入机器疑问清单，标记 `P2 pending` 与 `delivery_disposition=NON_BLOCKING_P2`。Agent 记录可逆最小影响默认值和回退后继续闭环；收到答案再修正基线并只重跑受影响门禁。

## 1. 事实提取

先从代码入口、目录、公共接口、配置、测试、泳道和既有模块日志证明模块边界。为每个稳定模块记录：

- 唯一且不随单次任务改变的模块键和名称；
- 职责、拥有路径、公共边界和依赖方向；机器所有权单元格必须至少包含一个反引号包裹的项目相对路径，多个路径仅以逗号分隔，API/协议说明留在职责范围列；
- 唯一稳定的长期维护 Agent 标题；
- 边界冲突、共享文件和必须由集成任务处理的交叉面。

“大功能模块”必须同时是长期稳定的业务能力、具有可独立测试的入口与输出契约、并能划出不重叠的所有权边界。辅助函数、临时任务切片、单个文件或一次性修复归入既有模块，不为其新增长期 Agent，避免 Agent 数量和上下文成本无界增长。

每个大功能模块恰好对应一个独立长期维护 Agent，并形成模块内闭环：需求基线 → 方案与流程 → 实现 → 定向测试 → 不同只读 Agent 的独立黑盒验收 → 当前证据、模块 run/latest、进度索引及适用泳道维护。任何一环未绑定当前需求、代码/构建或仍有开放缺陷/失败门禁，该模块不得完成；未答疑问仅作为 P2 跟踪。

根 AGENTS.md 必须内嵌唯一的 `Machine-Enforced Authority Matrix`，并由 Machine Policy 以规范定位符和 canonical JSON SHA-256 绑定。矩阵使用封闭枚举，为每行绑定单一 actor/action/object、repository scope、注册模块键和本地协调或宿主证明 receipt；固定 `deny` 不得被自然语言、委派、控制动词或行序覆盖。实际 Agent/run、完成状态、精确 `pass` verdict、receipt/candidate SHA-256、代码版本和 Build ID 来自结构化门禁证明；严格模式追加宿主结果。矩阵缺失、重复键、未知字段、固定行漂移或 path/SHA 漂移均失败关闭。

每次被 Dispatcher 派发的模块维护实现 run 和独立门禁 run 必须使用不同的 Codex 原生 `gpt-5.6-sol` Agent/run；实现/维护固定 `reasoning_effort=high`，审核、黑盒和独立验收固定 `reasoning_effort=xhigh`。默认本地协调 receipt 精确绑定请求配置、Agent/run、角色、模块、owned paths、input/output SHA-256、baseline/code/build 和 verdict，但不证明宿主实际运行身份；严格模式再由可信宿主校验器复核。Dispatcher、聚合写者、维护者和门禁审查者的 Agent/run 必须全局唯一；身份复用、配置替换、记录漂移或失败门禁均阻塞，默认模式不会仅因缺宿主校验器而阻塞。

稳定标题是长期规则；provider、模型、thread ID、session ID、一次性 run ID、在线状态和当前任务队列都是运行时事实，只能放运行时登记或证据。公共模板使用占位符，真实项目必须解析为经验证值。

## 2. Dispatcher 边界

Dispatcher 是用户唯一需求入口，负责：

1. 识别受影响模块并选择唯一实现 Agent；
2. 把当前用户会话中的最小充分上下文传给目标模块会话；
3. 协调跨模块依赖、独立门禁和全流程验证；
4. 汇总模块结论、开放风险和证据；
5. 发现稳定新边界时，先创建模块及其长期维护 Agent，再委派初始化。

Dispatcher 角色始终只读，不得修改业务代码，不得写共享计划、进度、追踪、上下文或证据索引，不得兼任实现、变更审查或黑盒角色。它可以执行只读核对并编排命令，但实际写入只能来自当次唯一实现 Agent。需要实现时必须使用不同 implementation Agent/run 获得当前协调租约；不得复用 Dispatcher 的 Agent ID 或 run ID，也不得在同一 run 内切换角色。

## 3. 上下文交接包

交接包至少包含以下字段，并仅链接当前角色需要的工件：

| 字段 | 内容 |
| --- | --- |
| 用户目标 | 当前明确请求和期望结果 |
| 批准需求与约束 | 当前基线、人工裁决、非目标和禁止事项 |
| 影响面 | 模块、拥有边界、直接依赖和冲突 |
| 输入/输出契约 | 入口、参数、schema、文件身份和失败语义 |
| 风险 | 风险等级、环境阻断和未知项 |
| 验证 | 目标测试、完整门禁、验收标准和独立角色 |
| 证据 | 相关路径、哈希、版本、当前 run 与剩余门禁 |

用户无需在模块会话重新描述需求。不得转发完整聊天、无关历史、全仓文档、其他 Agent 推理或实现自报；无法用已批准证据回答的歧义必须返回 Dispatcher 和需求基线。

## 4. 唯一写者与独立门禁

- 普通代码增量仅累计当前 run 的变更与证据，不逐次启动审查。只有模块实现、定向测试、追踪和当期证据形成闭环候选，或人工主动要求时才启动审查；人工触发可审查当前快照但不自行关闭模块。审查后任何代码或配置变化都会使结论失效，下一闭环候选必须按当前代码指纹重新审查。
- 主、父、子层级不授予固有写权。每项实现任务恰好一个 implementation Agent；单模块任务使用登记的模块维护 Agent，并以当前唯一活动协调租约匹配 module、Agent/run、稳定标题、精确 owned paths 和策略哈希。严格模式额外宿主证明这些字段。只有当前租约持有者可写该模块。
- 机器可读的运行证据必须显式记录 `assigned_model` 与 `assigned_reasoning_effort`；实现固定为 `gpt-5.6-sol/high`，只读方案、审核、裁决和独立验收固定为 `gpt-5.6-sol/xhigh`，不得以角色自报代替调度或 receipt 绑定。
- 模块维护 Agent 可以作为其获派变更的唯一实现写者，但不得审查或验收自己的实现；适用的变更审查和黑盒验收必须由不同的独立只读 Agent 针对同一代码/构建身份执行。Dispatcher 身份不能成为实现写者；若同一上层执行主体需要实现，必须使用前述分离且不复用身份的 implementation Agent/run。
- 模块维护 Agent 不得以 `complete`、`finalize`、“完成”或任何同义表述自行关闭自己的交付。每次显式 actor 出现都开始新的 scope，不依赖前置标点或连接词枚举；维护者/实现者 scope 只要同时出现自有交付与关闭、自验、批准、验收、完成或最终签署/审批权归属即默认失败，即使独立审查、黑盒或验收已经 `passed`、`completed` 或 `success` 也不得豁免；Dispatcher scope 只要同时出现模块交付与这些动作或权限归属也默认失败。只有绑定该动作的明确否定才能使相关分句合法。独立门禁通过只允许当前租约持有的模块维护 Agent 记录已经通过的结果，永不授权其自行 review、black-box、acceptance、adjudicate、close、complete 或 accept。主动语态与 `by`/“由”被动语态、`belongs to`/“归”、`from`/“从”及 `under authority of`/“在授权下”关系都必须按同一分句绑定 actor、交付对象、动作和组合极性；动作按完整单词、词形及 `final approval`、`final approver`、`final signatory`、`owns acceptance`、`approval authority/rights`、审批权和批准权等名词化授权归一，不把 `acceptance` 子串当成 `accept`。合法结果记录必须绑定可信证据证明的独立门禁 `passed`、`completed` 或 `success`；裸 `independent acceptance`，以及 `optional`、`omitted`、`pending`、`forged`、失败或未通过等状态都不能记录为通过，更不能授权任何自有动作。`allow`、`permit`、`authorize`、`ask`、`instruct` 控制的宾语 actor 仅继承直接绑定控制动作的明确否定；`prevent`、`forbid`、`block`、`disallow`、`stop ... from`、禁止、不允许和阻止属于动作级禁止，并按双重否定组合极性，正向控制以及后续 `but` 或新主句不得继承。`neither ... nor`/“均不得”可安全禁止多个 actor；同一动作的直接否定覆盖其 `and/or` 链，无关 actor 的否定或条件不得跨 scope 豁免。
- 模块维护/实现 Agent 不得承载 `$native-gpt-review-loop` 的 coordinator/adjudicator 职责；coordinator/adjudicator 的 Agent ID 与 run ID 必须同时不同于租约写者，始终只读、永不持 writer lease，且不得为该写者自证任何门禁。同一身份不能通过切换 role 或新建 run 先裁决再写；实际修订只交给不同的 canonical module-maintainer/implementation Agent identity+run，并再次校验唯一活动模块写租约。该租约只授权精确 owned paths 内的实现和合法结果记录，不授权裁决。两个 Sol 方案/审查 Agent 仍只读，父 GPT、主 Agent 或子 Agent 标签以及父子关系均不会赋予 Dispatcher、writer 或任何未持租约 Agent 额外权限。
- 其他模块维护 Agent 只读提供边界意见；独立 UI/UX、验收用例、需求一致性、领域、变更审查和黑盒 Agent 对代码和共享记录只读。
- Dispatcher 组织全流程验证并核对证据绑定，不代替独立结论。实现 Agent 和 Dispatcher 都不得自证独立门禁。
- 每个已启动的独立门禁必须分别保存 spawn receipt 和 output result。completion 阶段仅有 spawn receipt 必须 fail closed；implementation 阶段尚未启动且不适用的门禁仍按阶段规则省略，不得伪造空结果占位。
- 共享记录由唯一实现 Agent 使用项目规定的锁、期望哈希和原子更新命令写入；多个 Agent 不得并发写入。
- 原子更新命令写入前重新解析根 AGENTS.md canonical ownership，并逐项匹配 module key、稳定标题、Agent/run、精确 target/owned paths、当前 AGENTS/authority-matrix SHA-256 与唯一活动协调租约。默认本地模式校验结构、哈希、锁与 CAS；严格模式再校验宿主证明。缺租约、跨模块目标或 identity/ownership/lease 漂移时不得创建目录或替换文件。
- 机器强制范围仅覆盖经 `update_project_record.py` 或严格模式 guarded updater 的受控写入；本 Skill 无法归因或阻止绕过入口的同一 OS 用户 shell/直接文件写入。需要文件系统级强制时，必须另用隔离 worktree、容器或 OS 权限；默认模式不得声称已提供该隔离。
- 跨模块或系统级任务只有在每个受影响模块都关闭当前需求 ID、代码/构建、定向测试、独立验收、模块 run/latest 与适用流程变化泳道证据，且没有开放 finding 后才能完成；Dispatcher 只能聚合核对，不能替任何模块补签。

跨模块时，每个维护 Agent 用 `assets/module-delivery-bundle.template.json` 声明完成包并运行模块门禁。包必须绑定 canonical 疑问清单及当前需求基线；每个未答项保持非阻塞 P2，伪造 `ANSWERED`、基线/哈希漂移或失败门禁才失败关闭。所有模块关闭后，不同的原生 Sol `SYSTEM_AGGREGATION` 写者生成并哈希绑定系统清单，只读 Dispatcher 调用 `scripts/validate_system_delivery_bundle.py`。默认本地模式重验逐模块交付、身份分离、规范化模块集合、需求/变更并集、所有权、code/build、清单哈希与零开放缺陷；严格模式再复核全部宿主 provenance。

## 5. 可选严格安全路由

选择 `strict-security`，或在 `project` 模式显式选择 `authorization-mode=local-controlled-same-user` 时，必须完整读取并执行 `references/strict-security-governance.md`。默认 `delivery-first-local-coordination` 不加载该文件；严格基础设施缺失不得使默认交付链阻塞，也不得自动回退或冒充严格证明。

## 6. 新模块创建

只有经代码与契约证明会长期存在、且不能归入现有非重叠边界的能力才创建新模块。创建顺序必须是：

1. 分配不复用的模块键、稳定名称和非重叠边界；
2. 建立独立长期维护 Agent/会话；
3. 在根 AGENTS.md 的映射表登记稳定标题和拥有边界；
4. 同步需求追踪、上下文清单、执行日志索引和系统/模块泳道；
5. 再把初始化和实现派给该新模块的唯一实现 Agent。

步骤 1–3 未完成，或 ownership 与既有模块重叠时，实施必须保持 `blocked`。运行时 thread/session ID 不得回填到长期 AGENTS.md。

## 7. 生成后核对

- 映射表中的模块键和稳定标题均唯一，拥有路径/边界不重叠或已明确共享协调方式。
- 根文件只包含唯一 canonical authority matrix，Machine Policy 定位符和 SHA-256 与其一致；稳定能力不混入 run 事实，固定 deny 未被项目文字改写。
- 每个大功能模块都满足稳定能力、独立可测入口/输出和非重叠边界定义；辅助文件没有被错误拆成长期 Agent。
- 每个大功能模块的需求到验收、证据与维护闭环均绑定当前身份；维护 Agent 没有自验自己的实现。
- Dispatcher 角色始终只读；需要实现时使用不同 implementation Agent/run，且不得复用 Dispatcher 的 Agent ID 或 run ID；严格模式追加宿主证明。
- 主、父、子层级没有固有写权；每项实现任务只有一个与模块、身份、owned paths 和唯一活动模块写租约完全匹配的写者。
- 系统清单由独立 `SYSTEM_AGGREGATION` 写者生成并用 output receipt 绑定候选正文，Dispatcher 只读调用；所有参与者的 `agent_id` 与 `run_id` 全局唯一，严格模式追加宿主证明。
- 每项实现任务只有一个写者，所有审查和验收角色只读。
- 交接包字段完整且没有完整聊天、无关历史或其他 Agent 推理。
- 新模块创建顺序先所有权和长期维护会话、后实现。
- 若使用 system-governance bootstrap，已保存显式用户授权、same-user 风险披露、项目外固定公钥指纹、签名/时效/nonce/哈希/精确路径验证和持久原子消费证据；bootstrap 已失效，后续写入改用正常模块租约。
- 长期 AGENTS.md 中没有易变 thread/session ID。

使用 `scripts/validate_agents_md.py <AGENTS.md> --mode project --strict` 验证机器契约；失败必须回到规则生成或事实调查，不能仅靠文字说明放行。
