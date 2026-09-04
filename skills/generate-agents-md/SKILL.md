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
- 公共模板脱敏。仅在已授权项目任务或明确要求只读审查该策略或隔离效果时读取 `references/sensitive-configuration-policy.md`；只读不授权写入或传播真实值。
- 优先级：需求闭环与稳定交付 > 效率。状态为 `result_candidate → affected_checks_passed → baseline_frozen → hardening → closure_candidate`；成果前只做执行、受影响验收或防不可逆损害检查，冻结后才加载映射的打磨。治理不能替代成果或以无事实收益的机制阻塞验收。
- 稳定交付是流程设计的唯一目的；无映射就不得新增或启动。

## 模式

- `project`：生成生效规则；禁止占位符、模板注释和待办。
- `public-template`：生成脱敏模板；允许 `{{PLACEHOLDER}}`，禁止真实主体、路径或基础设施标识。
- `review`：只报可复现问题；收到修复要求后再写。

## 工作流

### 1. 最小事实调查

1. 查找当前目录至仓库根及目标子目录的全部 `AGENTS.md`。
2. 按需读 `README*`、依赖、构建、CI、测试、部署和环境配置；优先 `rg --files`、`rg` 和只读命令。
3. 查找计划/进度、需求/追踪、模块日志、泳道和验收记录。
4. 泳道须审查实现入口、调用链、接口、配置和测试，不只复述文档。
5. 仅为解释历史约束读取 `git log`/`git blame`；默认不加载全仓、全历史或完整日志。

### 2. 建立证据与作用域矩阵

写前记录“候选规则、来源、作用域、稳定性、决定”。硬规则只来自用户要求或已验证代码/配置；冲突、临时状态和未知项不得升级为事实。按需读 `references/extraction-checklist.md`，不整段复制。

存在 Dispatcher/长期维护 Agent 体系时读 `references/module-agent-governance.md`。Dispatcher 只读；层级不授予写权；每模块仅匹配 module/Agent/run/owned paths 的活动租约持有者单写且不得自验。

写前依 `references/task-write-boundary.md` 运行 `scripts/validate_task_write_scope.py`；项目 Agent 只写项目根，Skill 维护须本轮授权和精确根；校验不代表 OS 隔离。

### 3. 安全组合与更新

- 根文件用 `assets/AGENTS.template.md`，子目录用 `assets/AGENTS.scoped.template.md`，按需取 `assets/AGENTS.optional-sections.md`。
- 保留根模板的 `Machine-Enforced Policy` 固定枚举；项目规则只能补充，不能删除、改为可选或冲突。
- 逐项处理既有规则；删除/弱化须有过时、重复、冲突或作用域错误证据。
- 共享记录仅由登记且租约匹配 module、Agent/run、路径和策略哈希的实现/维护 Agent 写；Dispatcher、审查者或重复写者失败关闭。`scripts/update_project_record.py` 校验边界并锁/CAS 原子更新；仅支持 POSIX，Windows 用 WSL。它不是 OS 隔离。

### 4. 建立稳定交付链

- 用 `assets/requirement-traceability.template.md` 建立需求至流程、功能、UI、单测、验收、模块和黑盒的追踪；歧义返回需求基线，不得为实现缺陷改需求。
- 最小可靠链是“目标/边界/验收 → 真实入口至业务结果 → 受影响检查 → 当前证据”。冻结版本和验收证据后才打磨；回归后重验。细则见 `references/delivery-orchestration.md`。
- 仅按已证实需求/风险加载方案、泳道、功能点、适用原型、单测、独立验收、实现/规范和独立黑盒；不适用只记理由，不建空产物。
- 实现/维护 Agent 用 `gpt-5.6-sol/high`；方案、审核、裁决和独立验收用 `gpt-5.6-sol/xhigh`。后者只读且不持租约；修订只由不同 Agent/run 的当前租约写者执行，写者不得自验。默认保存本地结构绑定，严格模式才要求宿主证明运行身份。
- 小型任务须影响已知、无行为/契约/流程变化且有定向验证；Dispatcher 复用已登记模块维护 Agent 为唯一写者，不新增独立 Agent 或全链产物。标准任务只加行为门禁；完整多 Agent 仅用于已证实高风险、并发大模块或独立/合规要求。未知先调查。
- 用 `assets/delivery-contract.template.json` 和 `assets/gate-receipt.template.json` 建立单一决策索引；规划器只读，租约 writer 经 CAS 合并，禁止手改或复用旧门禁。命令以 `assets/project-commands.template.json` 登记 argv、来源、选择器和目录；成果可先跑已核实入口，冻结前须登记。细则见 `references/delivery-orchestration.md`。
- receipt schema v2 要求实现独占租约、gate 只读同候选、outer 唯一来源、replay 失败关闭；strict 再加宿主证明。v1 仅兼容。见 `references/role-specific-local-receipts.md`。
- 聚合验证器仅在闭环候选或完成阶段实时执行且不互签；漂移、失败门禁或开放分歧阻断。
- 仅 `project` 模式显式选择 `authorization-mode=local-controlled-same-user` 时启用签名租约并读取 `references/strict-security-governance.md`；默认 `delivery-first-local-coordination` 不加载。项目内公钥或调用方替换公钥不是可信根。

### 5. 同步代码、证据与可视流程

- 开发前更新计划，验证后更新进度；计划绑定需求基线，进度绑定 run 和代码版本。未执行、未验证、失败门禁或开放缺陷不得标记 `completed`；未答疑问不是缺陷或门禁。
- AI 维护机器可验疑问清单。未答项统一为 `P2 pending`/`NON_BLOCKING_P2`；记录可逆最小影响的默认值、回退和假设后继续，答复到达再更新基线并只重跑受影响门禁。
- 代码增量只累计证据；仅模块闭环候选或人工触发时审查当前指纹，代码再变则结论失效。发现含严重度、文件行、触发、影响和复现；修复先补失败测试，再最小修因。
- 用 `assets/context-manifest.template.md` 维护最小工作集；扩展或复用证据时才读 `references/evidence-reuse-policy.md`。日志按模块/`run_id` 不可变保存，以索引和 `latest.md` 为入口；`run_id` 与 `code_version` 分离，默认不读历史和大型原始输出。
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

生成项目产物时运行对应 `scripts/validate_*.py --help` 声明的验证器；仅 `validate_agents_md.py` 可用 `--strict`。验证器故障、证据漂移、失败门禁或开放缺陷阻断；`P2 pending` 不阻断且不得伪装已答。

## 输出

- 说明模式、修改、范围、来源和待确认；审查按严重度给文件/行、触发、影响和复现。
- 给路径摘要，不粘贴日志或 diff。

## 资源路由

- 根/子级/可选规则用 `assets/AGENTS.template.md`、`assets/AGENTS.scoped.template.md`、`assets/AGENTS.optional-sections.md`；其他产物按证据类型取用，不建不适用项；复用输入用 `assets/reuse-source-context.template.md`。
- 事实提取和模块治理按需读 `references/extraction-checklist.md`、`references/module-agent-governance.md`。
- 严格安全/敏感配置只在触发时读 `references/strict-security-governance.md`、`references/sensitive-configuration-policy.md`。
- 原生复核、证据复用、浏览器验收按需读 `references/multi-model-review-policy.md`、`references/evidence-reuse-policy.md`、`references/browser-validation-policy.md`；交付细则见 `references/delivery-orchestration.md`。
