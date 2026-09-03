---
name: generate-agents-md
description: 从仓库事实和项目需求提取可验证约束，生成、更新、拆分、公共化或审查 UTF-8 AGENTS.md；建立需求追踪、风险分级、独立验收、计划进度、模块日志、前端点击验证和阶段泳道门禁。用于稳定项目规则、约束需求偏移、脱敏模板、减少无谓 Token，或审查安全性与可执行性。
---

# Agents Flow Creater by FlameGun

## 不可削弱的原则

- 先调查；不得猜测命令、路径、技术栈、版本、环境或部署方式。
- 只写会稳定改变 Agent 行为的项目规则；系统、开发者和用户指令始终更高优先级。
- 根级只放全仓共同规则，子级 `AGENTS.md` 只写作用域差异，避免重复。
- 产物使用 UTF-8；不得把 RTF、HTML 或含 NUL 的内容当 Markdown。
- 公共模板脱敏。敏感连接仅在用户授权的项目任务，或明确要求只读审查该策略或隔离效果时读取 `references/sensitive-configuration-policy.md`；只读不授权写入/传播真实值。
- 优先级：需求闭环与稳定交付 > 效率。状态为 `result_candidate → affected_checks_passed → baseline_frozen → hardening → closure_candidate`；成果前仅做正确执行、受影响验收或防不可逆损害检查，冻结 receipt 后才加载有映射的打磨。治理门禁不得替代成果，也不得用无事实收益的安全、性能或 Token 机制阻塞适用验收。
- 稳定交付是流程设计的唯一目的；无映射就不得新增或启动。

## 模式

- `project`：生成可直接生效的真实项目规则；禁止占位符、模板注释和待办。
- `public-template`：生成可复用脱敏模板；允许 `{{PLACEHOLDER}}`，禁止真实人员、机器、客户、路径或基础设施标识。
- `review`：只报告可复现问题，不修改；用户要求修复后再进入对应写入模式。

## 工作流

### 1. 最小事实调查

1. 查找从当前目录到仓库根及目标子目录内的全部 `AGENTS.md`。
2. 按需读取 `README*`、依赖、构建、CI、测试、部署和环境配置；优先 `rg --files`、`rg` 和只读命令。
3. 查找计划、进度、需求基线、追踪矩阵、模块日志、系统/模块泳道和验收记录。
4. 泳道流程必须同时审查实现入口、调用链、接口、配置和测试，不得只复述文档。
5. 仅为解释历史约束读取 `git log` 或 `git blame`；默认不加载全仓、全历史或完整日志。

### 2. 建立证据与作用域矩阵

写入前记录“候选规则、来源、作用域、稳定性、处理决定”。硬规则只来自用户明确要求或已验证代码/配置；文档冲突、临时状态和未知项必须显式标记，不得升级为事实。详细提取项按需读取 `references/extraction-checklist.md`，不要把该文件整段复制进上下文或 AGENTS.md。

用户要求或仓库已有 Dispatcher/长期维护 Agent 体系时读取 `references/module-agent-governance.md`。Dispatcher 只读；层级不授予写权；每模块仅一个匹配 module/Agent/run/owned paths 的活动租约持有者单写且不得自验。

### 3. 安全组合与更新

- 根文件从 `assets/AGENTS.template.md` 开始，子目录使用 `assets/AGENTS.scoped.template.md`，按需取用 `assets/AGENTS.optional-sections.md`。
- 保留根模板的 `Machine-Enforced Policy` 固定枚举；项目规则只能补充，不能删除、改为可选或冲突。
- 逐项处理既有规则；删除或弱化须有过时、重复、冲突或作用域错误证据。
- 共享记录仅由 `docs/governance/module-writer-registry.json` 中持匹配 module、Agent/run、路径、策略哈希活动租约的实现/维护 Agent 写；Dispatcher、审查者或重复写者失败关闭，层级不授权。默认 `delivery-first-local-coordination` 由 `scripts/update_project_record.py` 校验边界并锁/CAS 原子更新；严格模式按风险或人工启用。它不能拦截绕过入口的同用户写入，不得冒充 OS 隔离。

### 4. 建立稳定交付链

- 用 `assets/requirement-traceability.template.md` 绑定 `REQ-*` 至 `FLOW-*`、`FEAT-*`、`UI-*`、`UT-*`、`AT-*`、`MOD-*`、`BB-*`；歧义返回需求基线，禁止为实现缺陷改变需求。
- 最小可靠链：目标/边界/验收 → 真实入口至业务结果 → 受影响检查 → 当前证据。冻结版本与验收证据后才打磨；回归恢复重验。细则见 `references/delivery-orchestration.md`。
- 仅按需求和风险映射加载必要阶段：方案 → 系统/模块泳道 → 功能点 → 适用 UI/UX 原型 → 测试点/单元用例 → 独立验收用例 → 实现/规范 → 独立黑盒。不适用只记可验证理由，不生成空产物。
- 实现/维护 Agent 用 `gpt-5.6-sol/high`；方案、审核、裁决和独立验收用 `gpt-5.6-sol/xhigh`。后者只读且不持租约；修订只由不同 Agent/run 的当前租约写者执行，写者不得自验。默认保存本地结构绑定，严格模式才要求宿主证明运行身份。
- 小型任务须影响已知、无外部行为/契约/流程变化且有定向验证，不新增 Agent、原型、泳道或全链产物。标准任务只加行为对应门禁；完整多 Agent 治理仅用于已证实高风险、并发大模块或明确独立/合规要求。未知影响先调查收敛。
- 用 `assets/delivery-contract.template.json`、`assets/gate-receipt.template.json` 建立单一决策索引；规划器只读，持租约 writer 经 CAS 合并，禁止手改或复用旧门禁。细则见 `references/delivery-orchestration.md`。
- 用 `assets/project-commands.template.json` 登记真实 argv、来源、选择器和目录。首次成果可先跑仓库已核实入口；形成 receipt、冻结或完成前必须登记校验。前端另记权威预览 URL、根和入口。拒绝恒定成功、吞错、伪 runner 和证据侧改入口。
- receipt 绑定角色/run/基线/工件/输入输出哈希/verdict。三类聚合验证器仅在闭环候选或完成阶段实时执行；普通增量不运行。列入 `aggregate_command_ids` 且不互签 receipt。默认校验结构、哈希和身份分离，严格模式再宿主复核；漂移、失败门禁或开放分歧阻断。
- 仅在 `project` 模式显式选择 `authorization-mode=local-controlled-same-user` 时启用 same-user bootstrap/签名租约并读取 `references/strict-security-governance.md`。默认 `delivery-first-local-coordination` 不加载；禁止回退或冒充 runtime 证明。
- `项目内公钥或调用方替换公钥`不是可信根。

### 5. 同步代码、证据与可视流程

- 开发前更新计划，验证后更新进度；计划绑定需求基线，进度绑定 run 和代码版本。未执行、未验证、失败门禁或开放缺陷不得标记 `completed`；未答疑问不是缺陷或门禁。
- AI 维护机器可验疑问清单。未答项标为 `P2 pending`、`delivery_disposition=NON_BLOCKING_P2`，推送人工但不等待；记录可逆最小影响的 `proposed_default`、`safe_fallback`、`assumption` 后继续。答复到达时更新基线并仅重跑受影响门禁。
- 普通代码增量只累计证据；仅模块形成闭环候选或人工触发时审查当前指纹，后续代码变化令结论失效。发现须含严重度、文件行、触发、影响和复现；修复先补失败测试，再做最小根因修改。
- 使用 `assets/context-manifest.template.md` 维护最小工作集。仅当任务扩展工作集或申请复用既有证据时，完整读取并执行 `references/evidence-reuse-policy.md`。
- 执行日志按模块与 `run_id` 保存不可变记录，以小型索引和 `latest.md` 为默认入口；`run_id` 与 `code_version` 分开，默认不读历史运行和大型原始输出。
- 每次修改只判定 `swimlane_applicable=true|false` 和 `flow_impact=none|changed|uncertain`。无适用泳道不建图、不查新鲜度；适用的 `none` 保留，`uncertain` 调查，`changed` 按稳定候选合并，首次依赖或阶段交接前至多更新一次；仅系统边界变化更新总览。
- 泳道或 Web 前端适用时读取 `references/browser-validation-policy.md`，执行应用内浏览器人工式闭环和真实 Playwright/Cypress。移动 Web 在相关范围启用浏览器门禁；原生移动执行 `native_mobile_tests`，跨端两套并行；遗留 `mobile` 由 `frontend_applicable` 区分。
- 仅处理受控敏感配置或明确只读审查其策略/隔离时加载 `references/sensitive-configuration-policy.md`；写入授权以目标 AGENTS.md 为单一来源。

## 失败关闭验证

迭代检查：

```bash
python3 scripts/validate_skill.py --quick
```

它不能证明闭环。已知标准影响可用 `--affected --changed-file <相对路径>`；未知映射自动升级 full。最终验收运行 full：

```bash
python3 scripts/validate_skill.py --full
```

full 含回归与 mutation。重装后运行 `python3 scripts/validate_skill.py --full --distribution --require-direct-skills`；源码、缓存或直装副本不同步/缺失不得发布。无直装时省略 `--require-direct-skills`。

生成项目产物时，再按适用性运行各验证器：

```bash
python3 scripts/validate_agents_md.py /path/to/AGENTS.md --mode project
python3 scripts/validate_context_manifest.py /path/to/context.md --project-root /path/to/project
python3 scripts/validate_requirement_questions.py docs/requirements/questions.json --project-root .
python3 scripts/validate_traceability.py /path/to/traceability.md --project-root /path/to/project --stage completion
python3 scripts/validate_project_commands.py /path/to/project-commands.json --project-root /path/to/project
python3 scripts/validate_multi_agent_evidence.py /path/to/multi-agent.json --trace /path/to/traceability.md --context /path/to/context.md --project-root /path/to/project --stage completion
python3 scripts/validate_swimlane_evidence.py /path/to/swimlane.json --trace /path/to/traceability.md --context /path/to/context.md --project-root /path/to/project
python3 scripts/validate_frontend_evidence.py /path/to/frontend.json --trace /path/to/traceability.md --command-manifest /path/to/project-commands.json --project-root /path/to/project
python3 scripts/validate_delivery_bundle.py --help
python3 scripts/validate_system_delivery_bundle.py --help  # 仅跨模块只读聚合
```

`validate_agents_md.py` 可用 `--strict`；其他验证器不追加未声明参数。验证器故障、证据漂移、失败门禁或开放缺陷阻断；疑问清单 `P2 pending` 不阻断且不得伪装已回答。

## 输出

- 说明模式、修改、作用域、来源与待确认；审查按严重度给出文件/行、触发、影响和复现。
- 只给路径与摘要，不粘贴日志或 diff。

## 资源路由

- 根/子级/可选规则：`assets/AGENTS.template.md`、`assets/AGENTS.scoped.template.md`、`assets/AGENTS.optional-sections.md`。
- 按证据类型从 `assets/` 取模板；证据复用输入用 `assets/reuse-source-context.template.md`。不生成不适用产物。
- 详细事实提取：`references/extraction-checklist.md`，只在对应章节适用时读取。
- 模块 Agent 治理：`references/module-agent-governance.md`，仅在用户要求或仓库已有 Dispatcher/长期维护 Agent 体系时读取。
- 严格安全治理：仅选择严格模式时读取 `references/strict-security-governance.md`；默认不加载。
- 受控敏感配置：仅本次明确授权或只读审查时读取 `references/sensitive-configuration-policy.md`。
- 原生 GPT 复核、证据复用、浏览器验收：分别按触发条件读取 `references/multi-model-review-policy.md`、`references/evidence-reuse-policy.md`、`references/browser-validation-policy.md`。
- 统一交付契约、分层门禁、证据失效与有限自动修复：`references/delivery-orchestration.md`。
