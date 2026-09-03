# AGENTS.md 提取与审查清单

## 目录

1. 模式与指令优先级
2. 事实来源与证据矩阵
3. 公共与专属规则分类
4. 章节与作用域设计
5. 已有文件更新门禁
6. 脱敏门禁
7. 需求追踪与交付门禁
8. 自动代码审查
9. 上下文与 Token 预算
10. 开发计划与完成进度
11. 模块化执行日志
12. 泳道图同步
13. 前端交互验证
14. 质量门禁

## 1. 模式与指令优先级

必须先确定模式：

- `project`：直接用于项目，禁止占位符、模板注释和待办标记。
- `public-template`：用于复用，允许通用占位符，禁止真实项目与环境标识。
- `review`：仅输出问题和证据，不修改文件。

AGENTS.md 不能覆盖系统、开发者或当前用户指令。多个 AGENTS.md 之间，更深目录文件只在其目录树内优先于上级文件。

## 2. 事实来源与证据矩阵

按可信度从高到低提取：

1. 用户当前明确要求。
2. 当前作用域内已有 `AGENTS.md`。
3. 实际代码、构建清单、CI、测试与部署配置。
4. README 和设计文档。
5. 历史提交与注释。

文档与代码冲突时，以可运行代码和配置描述当前事实，并报告文档差异。临时日志、聊天记录、一次性命令和当前机器负载不能直接升级为长期规则。

生成前建立临时证据矩阵：

| 候选规则 | 原始来源 | 核验方式 | 作用域 | 稳定性 | 处理 |
|---|---|---|---|---|---|
| 示例 | 用户/文件:行/命令 | 读取/运行/对比 | 根/目录 | 稳定/临时/未知 | 写入/下沉/省略/待确认 |

至少核实：

- 仓库根、主要入口、语言和运行时版本。
- 安装、测试、构建、格式化和启动命令。
- 目录职责、模块边界、依赖方向和公共契约。
- 数据库、消息系统、文件格式、时间与坐标约定。
- 部署目标、资源限制、离线要求和回滚方式。
- 日志、指标、隐私、许可证和数据留存要求。
- 所有父级与子级 AGENTS.md 的作用域。
- 现有开发计划、路线图、任务记录、变更日志和完成进度文件。
- 现有系统总览、模块泳道图、交互入口、图文件生成脚本和浏览器验证命令。
- 现有执行日志索引、模块键、当前摘要、单次日志、执行编号和代码版本来源。
- 现有调度入口、稳定模块边界、模块拥有路径、长期维护 Agent 标题和跨模块共享边界。
- 现有 thread/session ID 登记位置；区分稳定所有权标题与只能进入运行时证据的易变标识。

## 3. 公共与专属规则分类

适合公共模板：

- 先核实事实再修改。
- 最小变更、根因修复、避免无关改动。
- 测试从局部到整体，不伪造结果。
- 敏感信息最小化。
- AGENTS.md 的目录作用域和优先级规则。
- 架构、测试、调试、部署与文档同步的可选章节结构。

必须留在项目专属文件：

- 产品业务规则、算法阈值、模型版本和验收门槛。
- 固定服务名、数据库表、API 路径和数据格式。
- 特定操作系统、GPU、运行时或部署工具要求。
- 场景策略、回归样本约束和项目独有发布流程。
- 已验证的项目命令、目录和环境变量名。

不得以真实值进入公共模板：

- 认证材料、会话材料和带认证信息的连接串。
- 个人用户名、家庭目录、内外网 IP、主机名和端口映射。
- 客户名、人员信息、原始数据路径和未公开数据集标识。
- 未公开仓库、工单、商业权重和内部服务地址。

项目专属文件需要处理受控敏感连接配置时，停止在本清单展开细节；只有用户在本次任务中明确授权，才完整读取 `references/sensitive-configuration-policy.md`。该例外不得继承到公共模板。

## 4. 章节与作用域设计

每个章节都必须回答“这会改变 Agent 的行为吗”。不能回答则删除。

- **项目上下文**：限定交付目标、技术栈和支持环境。
- **项目约束**：模块边界、数据契约和明确禁止事项。
- **项目结构**：只列定位修改所需的关键目录。
- **验证**：真实命令、执行范围和结果声明规则。
- **变更边界**：兼容性、文档与发布要求。
- **可选章节**：仅在项目确有要求时加入架构、日志、调试、部署和数据治理。
- **开发计划与完成进度**：指定持续维护的计划与进度记录位置、状态格式、更新时间点和验证证据要求。
- **泳道图同步**：指定完整系统总览、模块图映射、代码审查依据、同步触发条件、浏览器点击闭环和完成门禁。
- **模块化执行日志**：指定小型索引、稳定模块键、`latest.md`、单次记录、执行与代码版本以及选择性读取路由。
- **前端交互验证**：规定桌面 PC 视口、应用内浏览器、Playwright/Cypress、人工式点击闭环和无 Bug 完成门禁；移动端仅在需求或支持范围明确涉及时加入。
- **需求追踪与交付门禁**：规定需求基线、稳定编号、风险等级、独立 UI/UX 与验收职责、变更控制和黑盒完成门禁。
- **自动代码审查**：规定每次模块修改后的自动命令、真实影响面、发现格式、修复回路、证据路径和失败关闭条件。
- **模块 Agent 所有权与调度**：规定 Dispatcher 用户入口、模块到稳定维护 Agent 与拥有边界的映射、层级中立的唯一活动模块协调租约、唯一实现写者、最小充分上下文交接、独立全流程验证和新模块先建 Agent 后实现。默认本地协调；严格模式才追加宿主证明。
- **本机受控授权**：默认宿主路径不变；只有 `project` 模式、本轮显式用户授权并选择 `authorization-mode=local-controlled-same-user` 时启用，绝不 fallback。bootstrap v1 保持旧义；v2 仅绑定并更新既有 `AGENTS.md` 与 `docs/agents/module-agent-governance.md`，签名两 target 的 pre/post hash+size、M11 registration、pre/post policy+authority hash 与 bootstrap candidate，缺失 owned leaf 只做最近祖先/case/symlink/overlap 验证且不创建。普通模块租约使用独立签名域、固定外部 registry、精确 identity/owned paths/targets/baseline/policy/authority/candidate/code/build、15 分钟 TTL，只代表同用户边界内授权与完整性，不证明 runtime、host-native、host-attested 或不可伪造。
- **租约 registry 与 guarded apply**：registry closed schema、no-follow lock、可重算 hash chain；receipt/nonce/lease ID 分别全局唯一，`(project,module)` 唯一 active，Agent/run 不跨模块 active，换 registry 在创建前失败。每次单文件 apply 重验签名/expiry/active/policy/authority/ownership/pre-post hash/fd-inode-parent，禁止 review/acceptance/black-box/aggregate/close。业务文件成功而 registry 失败必须 `PARTIAL/incomplete`，不得声称原子或成功。v1 无撤销字段，依靠不续签、唯一 active 与最短 TTL。
- **唯一 replay ledger**：签名 payload 闭集必须固定一个 canonical 外部 `replay_state_path`；CLI 参数和实际 guard 路径必须在任何 lock/ledger 创建或修改前精确匹配，禁止同一 envelope 换 ledger 再消费。

考虑创建子目录 `AGENTS.md` 的情况：

- 前端与后端使用不同测试、格式化或框架约定。
- 基础设施目录有高风险部署限制。
- 数据、模型或迁移目录有独立合规要求。
- 生成代码、第三方代码或 vendored 目录禁止手工修改。

拆分时：根文件声明共同规则；子文件只声明差异；路径必须清晰；不得把局部限制扩大到全仓库。

## 5. 已有文件更新门禁

修改前建立决策矩阵：

| 原规则 | 决策 | 依据 | 目标位置 |
|---|---|---|---|
| 示例 | 保留/改写/下沉/删除 | 仍有效/重复/冲突/过时/作用域错误 | 根/子目录/无 |

- 默认保留用户明确要求和仍有效的强制规则。
- 删除、弱化或改写必须有证据和原因。
- 子目录规则只允许下沉到覆盖相同文件范围的位置。
- 公共模板抽取不能反向覆盖或清空原项目文件。
- 查看最终 diff，确认没有静默丢失约束。

## 6. 脱敏门禁

公开化前搜索并人工复核：

```text
认证与会话材料、秘密变量、密钥材料
远程登录标识、IP 地址、非回环主机名
个人主目录、Windows 盘符、UNC 共享路径
客户名、人员名、数据批次名、工单号、内部项目代号
```

处理原则：

- 公共模板中的敏感认证材料直接删除，不提供示例值。
- 项目模式默认使用秘密引用。若用户本次明确要求受控敏感连接配置，改读专用策略文件并执行其边界和校验；本清单不承载该例外的具体字段、词形或命令。
- 机器和路径在公共模板中改为 `{{REMOTE_HOST}}`、`{{PROJECT_ROOT}}` 等通用占位符。
- 环境变量可以保留变量名，但不得保留真实值。
- 项目模式允许经确认的稳定基础设施引用，但自动校验应提示人工复核。
- 特殊授权只能用于真实项目，不能用于公共模板；未获授权时保持失败关闭。
- `--allow-pattern` 仅豁免匹配行的 IP、个人路径和远程登录标识误报；不影响认证材料、占位符或待办扫描，且拒绝空匹配和批量通配模式。

## 7. 需求追踪与交付门禁

根级 AGENTS.md 必须指定项目内的需求追踪矩阵，并把交付链闭合为：

根级文件还必须保留 `assets/AGENTS.template.md` 的 `Machine-Enforced Policy` 固定枚举块。该块是自动判定真实命令、原子记录更新、单写者、多 Agent 证据、自动审查、上下文清单、追踪、泳道、前端、移动端条件、UI/UX Agent 适用性和受控敏感配置授权的权威值；自然语言只能补充，不能削弱或覆盖。

```text
方案设计 → 系统/模块泳道 → 功能点 → UI/UX 原型 → 测试点/单元用例
→ 完整验收用例 → 代码实现与持续规范检查 → 独立黑盒验收 → 差异回写
```

- 需求基线至少包含目标、范围、非目标、约束和可量化验收标准。使用 `assets/requirement-questions.template.json` 记录机器可验证疑问：`question_id`、`impact_scope`、`risk`、`proposed_default`、`safe_fallback`、`answer_status=ANSWERED|NOT_PROVIDED`、`delivery_disposition=NON_BLOCKING_P2`、`assumption`、`owner`、`review_due`。所有人工未答项均作为 `P2 pending`，采用显式、可逆、最小影响且有回退的默认假设继续。`ANSWERED` 绑定人工答案、回答前后基线及影响范围重跑 receipt；默认验证结构和哈希，严格模式再宿主校验。
- 使用稳定的 `REQ-*`、`FLOW-*`、`FEAT-*`、`UI-*`、`UT-*`、`AT-*`、`MOD-*`、`BB-*` 编号，把每个下游产物追溯到原始需求。不适用项写明可验证理由，不能留空。同一产物可服务多项需求并复用编号，但同一编号不得映射到不同路径。
- 稳定交付是流程复杂度的唯一目的。新增 Agent、产物、门禁、上下文扩展或记录前，必须记录已核实风险/失败模式、事实证据、受影响验收点、预期可观测信号和停用条件；缺任一映射则不得启用。假设性担忧、通用“最佳实践”或无法复现的一次性经历不足以建立长期硬门禁。
- 所有任务先闭合最小可靠链：目标/范围/非目标/可量化验收 → 最小实现 → 受影响测试和现有相关静态检查 → 对照验收点记录当前证据。不适用环节只记可验证 `N/A` 理由，不生成空产物。
- 每项变更记录小型、标准或高风险等级及事实依据。小型变更必须影响面已知、不改变外部可观测行为/契约/流程且有目标验证；不创建新 Agent、原型、泳道或完整多产物链。标准任务只增加与改变行为直接映射的门禁。高风险、并发大模块或明确独立性/合规要求才启用完整多 Agent 治理。
- 风险由变更面设置最低等级：行为、用户可见、UI、API、移动 Web、原生移动至少为标准；公共 API、认证、安全、隐私、迁移、持久化、异步、跨模块、数据结构为高风险；未知变更面暂按高风险，但先做最小事实调查尽快收敛，不得长期以“未知”理由加载全部门禁。移动 Web 使用浏览器与 Playwright/Cypress，原生移动使用登记的原生测试命令；遗留 `mobile` 由 `frontend_applicable` 显式区分。
- 涉及 UI 时，由独立 UI/UX Agent 基于已批准需求、方案、泳道和功能点制作或审查原型；不得自行增加产品行为，也不得修改实现代码。
- 在实现前定义测试点和适用单元用例；由另一个独立验收 Agent 基于已批准基线编写完整的成功、拒绝、失败、重试、恢复、权限和边界用例。
- 实现只能覆盖已批准的 `REQ-*` 与 `FEAT-*`。新增或改变行为必须先更新编号、方案、泳道、UI、测试和验收产物，禁止“先写代码后补需求”。
- 格式、类型、Lint、复杂度、安全和架构规则在实现前与实现中持续执行，不得集中推迟到最后。
- 实现完成后，由独立黑盒 Agent 使用已批准验收用例和类发布接口执行验收；不得修改代码或接受实现 Agent 的自报结果。
- 仅适用的独立门禁才要求 Agent。非 UI、非用户可见任务的 UI_UX 门禁使用 `N/A: 可验证原因`、空 run ID 和 `not_applicable`，不得为节省 Token 启动无关 Agent；UI 或用户可见任务不得跳过。其他适用 Agent 无法启动时标记为 `blocked`，不得由实现 Agent 自证。
- 所有适用的独立门禁必须使用互不相同且不等于实现 Agent 的 `run_id`，并各自保存最小输入清单（逐工件绑定当前路径和 SHA-256）和输出证据；黑盒证据必须绑定当前需求基线 SHA、代码版本、构建编号、环境和验证时间。
- 只在多 Agent 确有风险映射时，持有匹配 module、Agent/run、owned paths 唯一活动协调租约的当前实现 Agent 才是模块代码与共享记录的唯一写者；主、父、子层级不授予固有写权，其他 Agent 只读。小型任务不启动额外 Agent；标准任务仅为改变的外部行为启动独立验收或黑盒；高风险任务才按独立风险映射增加角色。不得以多数票处理冲突；开放缺陷或门禁分歧阻断，机器疑问清单中的未答项一律 `P2 pending` 且不阻断。
- 用 `assets/multi-agent-evidence.template.json` 保存每个适用角色的 provider、focus、唯一 run ID、最小输入与输出路径/哈希和只读边界，并用 `scripts/validate_multi_agent_evidence.py` 校验。
- 失败先分类再回流：`implementation_defect` 返回实现，`requirement_ambiguity` 返回需求基线，`acceptance_case_defect` 返回验收用例，`environment_blocker` 阻断，`approved_requirement_change` 才建立新基线；不得用改需求掩盖实现缺陷。
- 新建结构时使用 `assets/requirement-traceability.template.md`；实现交接前运行 `python3 scripts/validate_traceability.py <matrix> --project-root <root> --stage implementation`，完成前改用 `--stage completion`；同阶段还要运行 `scripts/validate_delivery_bundle.py`，确认 AGENTS、追踪矩阵、工作集、真实命令、多 Agent 证据和适用前端证据绑定相同需求基线、代码版本与实现 run。跨模块任务必须逐模块生成 `assets/module-delivery-bundle.template.json`，再由独立 `SYSTEM_AGGREGATION` Sol 写者生成系统清单，Dispatcher 只读调用 `scripts/validate_system_delivery_bundle.py`。默认本地协调模式验证封闭结构、路径与哈希，不因缺少宿主校验器阻断；只有明确选择严格模式时，缺少不可由项目文件开启的宿主可信校验器才阻断。集合不全、跨文件漂移或命令不可用在两种模式下均阻断。

## 8. 自动代码审查

- 仅在模块形成闭环候选或人工主动触发时，自动运行确定性规划器选中的审查命令；普通代码增量只累计证据。命令缺失、被标为不适用、失败或不可用时将对应门禁标记为 `blocked`。
- 审查当前真实变更文件，并沿调用关系覆盖受影响调用方、被调用方、公共接口、配置、持久化/异步边界、测试、需求追踪和泳道图；禁止仅依据 diff 摘要或实现 Agent 自报下结论。
- 每项可执行发现记录严重度、精确文件和行号、触发条件、影响、复现或验证命令。需求歧义与实现缺陷分开分类。
- 实现缺陷返回实现；适用时先补失败回归测试，再做最小根因修复，自动重跑目标测试、代码规范、追踪校验、泳道校验和自动审查。
- 审查证据记录范围、代码版本、命令、发现、重跑结果和结论。任何可执行发现、无法解释错误或阻断状态存在时，不得进入黑盒验收或标记完成。

## 9. 上下文与 Token 预算

- 使用 `assets/context-manifest.template.md` 为当前执行建立小型工作集，风险字段恰好分为等级、风险原因、工作集扩展原因三段，并记录需求基线、代码版本、Build ID、受影响编号、模块、文件、直接依赖、命令、从根到各工作集文件目录的完整生效 AGENTS 链，以及代码/命令/配置/环境/输入指纹、组合缓存键、复用记录和证据路径。
- 默认只读进度索引、受影响模块 `latest.md`、当前 run、相关需求行和直接影响的代码/测试/配置/图；禁止默认加载全仓、全部历史、完整日志和无关文档。
- 只有高风险、跨模块、公共契约变更、影响未知，或目标测试/审查暴露未解析依赖时才扩展上下文，并记录原因。
- 验证缓存必须绑定需求、风险、依赖、代码、规则链、命令、配置、环境和输入；任务申请复用或扩展工作集时，完整读取并执行 `references/evidence-reuse-policy.md`，本清单不复制其证据 schema。
- 原始输出和大工件落项目路径；上下文仅传命令、状态、结果计数、指纹与路径。独立 Agent 只接收角色所需输入清单，不接收完整聊天、全仓文档或其他 Agent 推理。
- 指纹未变化时避免重复执行相同命令；但不得以 Token、时间或上下文限制跳过强制正确性、安全、追踪、审查、泳道和验收门禁。

## 10. 开发计划与完成进度

根级 AGENTS.md 必须指定开发计划和完成进度的项目内记录位置。优先复用现有文件；没有既有位置时，依据用户明确要求选择稳定路径，不得放在个人目录或临时目录。

- 开始实质开发前，计划记录目标、范围、顺序步骤、验收条件、依赖和风险。
- 工作状态使用 `pending`、`in_progress`、`completed`、`blocked` 或项目已有等价状态。
- 完成可验证工作后，进度记录日期、交付结果、验证证据和剩余事项。
- 只有实际执行并通过相应验证的工作才能标记为完成。
- 计划与进度是持续变化的项目状态，应保存在专用记录中；AGENTS.md 只规定维护方式，不复制当前任务快照。
- 共享计划、进度、追踪、工作集和证据索引必须通过 `scripts/update_project_record.py` 更新，并绑定根 AGENTS.md 的 canonical ownership、固定 `docs/governance/module-writer-registry.json` 中唯一活动维护 Agent/run、精确 target/owned paths、当前 AGENTS/authority-matrix SHA-256 和租约。默认 `delivery-first-local-coordination`；高风险、合规或人工明确要求才选 `strict-security` 宿主校验。Dispatcher/审查者身份、重复 module/Agent/run/lease 或 registry 漂移失败关闭；两者仍使用全局授权锁、目标锁、期望当前 SHA-256 和原子替换。

## 11. 模块化执行日志

根级 AGENTS.md 必须将详细完成记录按模块和单次执行分流，并维护一个小型索引。拆分文件本身不会减少上下文；必须同时规定默认只读索引和当前受影响模块。

- 优先复用现有进度目录。没有时可采用 `docs/progress/index.md`、`docs/progress/modules/<module>/latest.md`、`docs/progress/modules/<module>/run-<run_id>.md` 和 `docs/progress/system/`。
- 模块键必须稳定并可从仓库结构或已验证模块边界导出；不得为同一模块每次临时改名。
- `run_id` 标识单次 Agent 执行；`code_version` 标识 Git commit、tag 或构建版本。两者必须分开记录。
- 单次记录至少包含模块、状态、风险等级、追踪编号、变更文件、交付结果、验证与独立评审证据、泳道图路径和剩余风险。
- 每个已变更模块在验证后更新 `latest.md`；根索引只保留当前状态、简短结果和详细记录链接。
- 单次记录、模块 `latest.md` 和根索引未同步时，不得将该执行标记为 `completed`。
- 跨模块执行放入系统级目录，并从索引链接到每个受影响模块，不复制多份同一记录。
- 默认读取顺序是索引、受影响模块的 `latest.md`、当次 `run_id`。仅在排查回归、解决冲突或追溯历史决策时读旧记录。
- 原始测试输出、截图、大段 diff 和生成文件使用路径引用；不得粘贴到索引或模块摘要。
- 用 `assets/execution-log-index.template.md`、`assets/execution-run.template.md` 和 `assets/module-latest.template.md` 生成新结构，并在项目模式中解析全部占位符；自动审查使用 `assets/automated-review-evidence.template.md`，并由交付包绑定当前 run/code。

## 12. 泳道图同步

根级 AGENTS.md 必须规定：每次代码模块修改后只判定 `swimlane_applicable=true|false` 与 `flow_impact=none|changed|uncertain` 并写入现有审查或运行证据，不因单个文件、提交或时间间隔逐次写图。无适用泳道时不创建空图且不运行泳道门禁；有适用泳道时，`changed` 以模块、阶段、稳定候选为批次，在首次依赖该图的下游步骤或阶段/里程碑交接前（取较早者）更新；每个模块、每个阶段、每个稳定候选至多写图一次。阶段结束只对适用泳道做一致性与新鲜度检查，不无条件重画。

提取与生成时：

- 搜索 `docs/flows/`、`diagrams/`、`*.html`、`*.puml`、`*.bpmn`、`*.mmd` 以及包含 `swimlane`、`泳道`、`流程图` 的文件，核实现有入口和模块映射。
- 同时审查实现代码、入口、调用链、接口、配置和测试；文档只能作为补充证据。
- 没有既有位置时，为项目选择稳定路径，例如 `docs/flows/system-swimlanes.html` 与 `docs/flows/modules/`，并在项目模式中写成真实路径。
- `swimlane_applicable=false` 不创建空图、不运行 `swimlane_evidence` 或 `swimlane_freshness`；适用泳道的 `none` 不改写图文件并保留内容与 SHA-256，阶段结束在原有证据中记录复核结果；`uncertain` 先做入口、调用链、接口、配置和测试的最小调查，必须收敛为 `none` 或 `changed`，不得为保险起见重画。
- 只有系统/跨模块边界、模块归属、顶层入口/出口、跨模块交接或外部依赖确认变化时才先更新完整系统总览；模块内部语义流程变化只更新受影响模块图。仅为设计、交接、运维或验收依赖的稳定流程生成缺失图，不为 helper、临时切片或纯测试模块建图。
- 下游在阶段结束前需要依赖泳道，或过期泳道会误导正在进行的安全、权限、不可逆操作或公共契约工作时，必须在该使用点前提前完成本批次更新；否则延迟到稳定候选，禁止按文件、提交次数或固定时钟重画。
- 交互式 HTML 必须在浏览器中实际打开，通过人工式点击从总览进入受影响模块并返回；确认泳道头、连线、分支、模块内容和导航闭环可见且无错误。
- 交互式 HTML 的服务、入口身份、点击闭环和证据绑定按 `references/browser-validation-policy.md` 执行，完成后停止临时服务。
- 完成进度必须记录受影响模块、总览或模块图路径、代码审查依据、执行的验证方式与结果。
- 可用时优先使用 `$draw-project-swimlane-diagrams` 生成和审查，但规则不得依赖该 Skill 才能理解或执行。

## 13. 前端交互验证

项目包含前端或泳道时，根级 AGENTS.md 必须规定真实页面点击、项目原生 E2E、无 Bug 完成门禁以及条件式移动验证。完整读取并执行 `references/browser-validation-policy.md`；本清单只负责判断适用性，不复制浏览器、DOM、CSS、截图或原生报告 schema。

真实命令必须写入 `assets/project-commands.template.json` 对应的项目清单，包含 argv、声明来源、选择器、工作目录和适用性；执行前运行 `scripts/validate_project_commands.py`，不得以恒定成功、Shell 包装、吞错或臆造命令代替。

## 14. 质量门禁

所有模式：

- [ ] 文件为 UTF-8 Markdown，不是 RTF/HTML，也不含 NUL 字节。
- [ ] 所有硬规则都有证据来源和正确作用域。
- [ ] 没有重复、冲突、不可执行或无法判断完成条件的规则。
- [ ] 使用“必须/禁止”时有明确原因、范围和必要例外。
- [ ] 没有临时状态、聊天过程或过时结果。
- [ ] diff 只包含用户请求范围内的变更。
- [ ] 已指定开发计划与完成进度记录位置、更新时间点、状态格式和验证要求。
- [ ] 已指定需求追踪矩阵，并闭合 `REQ/FLOW/FEAT/UI/UT/AT/MOD/BB` 编号关系。
- [ ] 已规定风险分级、小型任务的跳过条件，以及标准/高风险任务的完整流程。
- [ ] 已分离 UI/UX、验收用例和黑盒 Agent 职责；禁止自行扩需求、修改实现或由实现 Agent 自证。
- [ ] 已规定主、父、子层级无固有写权，唯一实现写者必须持有匹配 module、Agent/run、owned paths 的唯一活动协调租约；独立 Agent 只读，并机器校验证据哈希与分歧关闭；严格模式才追加宿主证明。
- [ ] 已明确模块键、稳定维护 Agent 标题和拥有路径/边界的一一映射，且长期 AGENTS.md 不含 thread/session ID。
- [ ] 已限制 Dispatcher 角色始终只读，只做入口、路由、上下文传递、验证编排和新模块 Agent 创建，禁止写业务代码与共享记录；需要实现时使用不同的 implementation Agent/run，且不得复用 Dispatcher 的 Agent ID 或 run ID；严格模式才追加宿主证明。
- [ ] 系统清单由独立 `SYSTEM_AGGREGATION` 写者生成；其 run 与 Dispatcher、模块实现及门禁审查 run 均不同，默认本地模式绑定封闭 receipt，严格模式才由宿主可信运行时复核。
- [ ] 上下文交接包覆盖目标、批准需求/约束、模块边界、输入输出、依赖风险、验证验收和证据；不传完整聊天、无关历史或其他 Agent 推理。
- [ ] 稳定新模块在实现前已建立唯一键、非重叠 ownership 和独立长期维护 Agent/会话。
- [ ] 若启用本机受控治理 bootstrap，已有 project 模式、显式 authorization-mode 与风险接受；v1 未被解释为 v2；v2 精确绑定两份既有治理 target、M11 registration、pre/post policy+authority 与 bootstrap candidate，missing owned leaf 仅验证不创建，完成后只接受本机受控 module lease。
- [ ] 若启用本机受控普通模块租约，独立 domain/closed schema、固定外部 registry、15 分钟 TTL、全局独立 ID、唯一 active、跨模块 Agent/run 排斥、严格角色 deny、每次 apply 的 policy/authority/ownership/hash/path-race 重验与 PARTIAL 报告测试均通过；未虚构撤销。
- [ ] canonical matrix 中只有 `system-governance-bootstrap/bootstrap_system_governance/system-governance` 为 `external-explicit-only`；其他 bootstrap/actor 行固定 deny，普通角色分离、单 writer、review/acceptance/black-box 独立门禁没有降低。
- [ ] 已要求代码规范在实现前和实现中持续执行，新增行为先更新追踪产物。
- [ ] 已指定小型索引、模块日志和系统级日志路径。
- [ ] 已区分 `run_id` 与 `code_version`，并规定单次日志必填字段。
- [ ] 已要求完成后更新 `latest.md` 和索引，默认不扫描全部历史。
- [ ] 已建立最小工作集、证据指纹和缓存失效规则；独立 Agent 使用角色输入清单，原始输出只引用路径。
- [ ] 已规定每次代码变更先判定泳道适用性再判定三态影响；不适用时无图无门禁，适用时 `none` 保留图哈希、`uncertain` 先收敛、`changed` 每模块/阶段/稳定候选批量写图一次，并在首次下游依赖或阶段交接前完成。
- [ ] 已写明系统总览的更新触发条件、图路径、代码审查依据和浏览器点击闭环。
- [ ] 完成进度要求记录受影响模块、泳道图路径和验证证据。
- [ ] 前端项目已规定桌面 PC、应用内浏览器、Playwright/Cypress、人工式点击闭环和无 Bug 门禁；移动端只在明确适用时启用。
- [ ] 已核实真实命令清单、共享记录原子更新，以及适用前端的结构化浏览器/E2E 证据。

`project` 模式：

- [ ] 没有 `{{...}}`、`TODO`、`FIXME`、`TBD` 或模板注释。
- [ ] 所有路径、命令、脚本、环境变量和配置均已验证。
- [ ] 子级未重复父级规则，原有有效约束未丢失。
- [ ] 若本次任务包含受控敏感连接配置，已按专用策略记录明确授权和边界并执行专用校验。

`public-template` 模式：

- [ ] 占位符通用、命名清晰，不包含真实值。
- [ ] 没有敏感认证材料、IP、个人路径、客户或内部数据标识。
- [ ] 没有把项目阈值、版本、服务名或现场流程抽成公共规则。

执行静态门禁：

```bash
python3 scripts/validate_agents_md.py TARGET --mode project --strict
python3 scripts/validate_agents_md.py SCOPED_TARGET --mode project --scope scoped --strict
python3 scripts/validate_agents_md.py TEMPLATE --mode public-template --strict
```
