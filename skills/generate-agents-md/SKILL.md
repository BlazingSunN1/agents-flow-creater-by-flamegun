---
name: generate-agents-md
description: 从仓库事实、项目需求、README、构建测试配置和既有 AGENTS.md 中提取可验证工程约束，生成、更新、拆分、公共化或审查 UTF-8 AGENTS.md；同时建立需求追踪、风险分级、自动审查、最小工作集、独立验收、计划进度、模块日志、前端点击验证，以及阶段完成或流程变化触发的泳道同步门禁。用于创建或完善项目规则、约束需求偏移、脱敏公共模板、减少无谓 Token，或审查 AGENTS.md 的安全性、稳定性与可执行性。
---

# Agents Flow Creater by FlameGun

## 不可削弱的原则

- 先调查再生成；不得猜测命令、路径、技术栈、版本、环境或部署方式。
- 只写会稳定改变 Agent 行为的项目规则；系统、开发者和用户指令始终更高优先级。
- 根级只放全仓共同规则，子级 `AGENTS.md` 只写作用域差异，避免重复。
- 所有产物使用 UTF-8；不得把 RTF、HTML 或含 NUL 的内容当 Markdown。
- 公共模板必须脱敏。涉及受控敏感连接配置时，仅在用户明确授权的项目任务中，或用户明确要求只读审查该策略或隔离效果时，完整读取 `references/sensitive-configuration-policy.md`；只读审查不授予写入或传播真实值的权限，普通任务不得加载该文件。
- 需求实现稳定性优先于 Token 节省；不得因节省上下文跳过追踪、测试、审查、安全或验收门禁。

## 模式

- `project`：生成可直接生效的真实项目规则；禁止占位符、模板注释和待办。
- `public-template`：生成可复用脱敏模板；允许 `{{PLACEHOLDER}}`，禁止真实人员、机器、客户、路径或基础设施标识。
- `review`：只报告可复现问题，不修改；用户要求修复后再进入对应写入模式。

新建、完善、重构和作用域拆分使用 `project`；从现有文件抽取公共结构使用 `public-template`。

## 工作流

### 1. 最小事实调查

1. 查找从当前目录到仓库根及目标子目录内的全部 `AGENTS.md`。
2. 按需读取 `README*`、依赖清单、构建脚本、CI、测试、部署和环境配置；优先 `rg --files`、`rg` 和只读命令。
3. 查找计划、进度、需求基线、追踪矩阵、模块日志、系统/模块泳道和验收记录。
4. 泳道流程必须同时审查实现入口、调用链、接口、配置和测试，不得只复述文档。
5. 只有需要解释历史约束时才读取 `git log` 或 `git blame`；默认不加载全仓、全历史或完整日志。

### 2. 建立证据与作用域矩阵

写入前记录“候选规则、来源、作用域、稳定性、处理决定”。硬规则只来自用户明确要求或已验证代码/配置；文档冲突、临时状态和未知项必须显式标记，不得升级为事实。详细提取项按需读取 `references/extraction-checklist.md`，不要把该文件整段复制进上下文或 AGENTS.md。

### 3. 安全组合与更新

- 根文件从 `assets/AGENTS.template.md` 开始，子目录使用 `assets/AGENTS.scoped.template.md`，按需取用 `assets/AGENTS.optional-sections.md`。
- 保留根模板的 `Machine-Enforced Policy` 固定枚举；项目规则只能补充，不能删除、改为可选或冲突。
- 修改既有规则前逐项决定保留、改写、下沉或删除；删除/弱化必须有过时、重复、冲突或作用域错误的证据。
- 计划、进度、追踪、工作集和证据索引等共享记录只能由实现 Agent 写入，并用 `scripts/update_project_record.py` 的锁、期望 SHA-256 和原子替换防并发覆盖。

### 4. 建立稳定交付链

- 使用 `assets/requirement-traceability.template.md` 把 `REQ-*` 依次绑定到 `FLOW-*`、`FEAT-*`、`UI-*`、`UT-*`、`AT-*`、`MOD-*`、`BB-*`；歧义返回需求基线，禁止为实现缺陷改变需求。
- 标准/高风险任务依次经过：方案设计 → 系统/模块泳道 → 功能点 → 适用时独立 UI/UX 原型 → 测试点/单元用例 → 独立验收用例 → 实现与持续代码规范 → 独立黑盒验收。
- 用户明确启用外部多模型评审时，完整读取 `references/multi-model-review-policy.md`，再调用 `$multi-model-review-loop`；未启用时不得加载该契约。
- 小型任务只跳过确实不适用的重型门禁；验收用例、阶段适用的黑盒、追踪、测试和泳道同步不得省略。未知变更面默认高风险，直到证据排除。
- 使用 `assets/project-commands.template.json` 登记从真实配置提取的完整 argv、声明来源、选择器和工作目录；前端项目还必须登记权威预览 URL、预览根目录和入口工件。拒绝恒定成功、Shell/间接 `env` 吞错、项目内同名伪 runner 和证据侧自行改写入口。
- 使用 `assets/multi-agent-evidence.template.json` 实施单写者和只读独立 Agent；用 `assets/independent-agent-input.template.json` 绑定角色、run、基线、当前需求 ID，以及每个最小角色工件的路径和当前 SHA-256，并明确排除聊天、推理和实现自报；用 `assets/independent-agent-output.template.json` 绑定输入清单 SHA-256、独立结论和 findings。run ID、输入、输出及文件身份/规范化内容必须独立，输出不得复用 Changed/config/input 文件；输入清单或任一工件漂移、出现重复/未知字段、类型别名或分歧未关闭都不得通过。

### 5. 同步代码、证据与可视流程

- 实质开发前更新计划，验证后更新完成进度；计划必须绑定当前需求基线，进度必须绑定当前实现 run 和代码版本，交付包校验文件存在且绑定一致。未执行、未验证或仍有开放问题的工作不得标记 `completed`。
- 每次代码模块修改后自动审查真实变更、调用方/被调用方、接口、配置、测试、追踪和泳道。发现必须含严重度、文件行号、触发、影响和复现；修复时先补失败测试，再做最小根因修复并重跑门禁。
- 使用 `assets/context-manifest.template.md` 维护最小工作集。仅当任务扩展工作集或申请复用既有证据时，完整读取并执行 `references/evidence-reuse-policy.md`。
- 执行日志按模块与 `run_id` 保存不可变记录，以小型索引和 `latest.md` 为默认入口；`run_id` 与 `code_version` 分开，默认不读历史运行和大型原始输出。
- 在阶段性任务或里程碑完成、准备交接/验收时同步所有受影响模块泳道；阶段中间仅当修改改变入口、流程、分支、跨模块交接、外部依赖、持久化、异步/恢复路径或最终输出时立即更新，普通流程无关内部修改不逐次重画。跨模块或系统边界变化先更新系统总览。
- 泳道或前端代码适用时，完整读取 `references/browser-validation-policy.md`，执行应用内浏览器人工式点击闭环和项目真实 Playwright/Cypress；桌面 PC 默认适用，移动证据仅在批准范围明确包含移动、触控或响应式时启用。
- 仅当用户明确要求处理受控敏感连接配置，或明确要求只读审查该策略或隔离效果时，才读取 `references/sensitive-configuration-policy.md`；专用写入校验命令只在前一种情形使用。

## 失败关闭验证

在本 Skill 根目录运行一键自检：

```bash
python3 scripts/validate_skill.py
```

它统一执行 Skill 包校验、文件/函数大小与循环依赖、全部公开 CLI 启动 smoke、全量回归、关键语义 mutation 和泳道浏览器脚本语法检查。修改本 Skill 时必须通过；失败输出只保留末尾摘要，减少无效 Token。

生成项目产物时，再按适用性运行各验证器：

```bash
python3 scripts/validate_agents_md.py /path/to/AGENTS.md --mode project
python3 scripts/validate_context_manifest.py /path/to/context.md --project-root /path/to/project
python3 scripts/validate_traceability.py /path/to/traceability.md --project-root /path/to/project --stage completion
python3 scripts/validate_project_commands.py /path/to/project-commands.json --project-root /path/to/project
python3 scripts/validate_multi_agent_evidence.py /path/to/multi-agent.json --trace /path/to/traceability.md --context /path/to/context.md --project-root /path/to/project --stage completion
python3 scripts/validate_swimlane_evidence.py /path/to/swimlane.json --trace /path/to/traceability.md --context /path/to/context.md --project-root /path/to/project
python3 scripts/validate_frontend_evidence.py /path/to/frontend.json --trace /path/to/traceability.md --command-manifest /path/to/project-commands.json --project-root /path/to/project
python3 scripts/validate_delivery_bundle.py --agents /path/to/AGENTS.md --trace /path/to/traceability.md --context /path/to/context.md --command-manifest /path/to/project-commands.json --multi-agent-evidence /path/to/multi-agent.json --swimlane-evidence /path/to/swimlane.json --project-root /path/to/project --stage completion
```

`validate_agents_md.py` 可用 `--strict`；其他验证器不要追加未声明参数。任一验证器缺失、崩溃、证据过期、跨文件漂移或开放发现都记为 `blocked`，不得以人工判断替代。

## 输出

- 说明模式、修改文件、作用域、事实来源、待确认项和脱敏类别。
- 更新既有文件时概述规则的保留、下沉、改写或删除及原因。
- 审查模式按严重度给出文件/行、触发、影响和复现；无问题时明确说明。
- 不粘贴完整大型文件、日志、截图或 diff，只给可点击路径与紧凑证据摘要。

## 资源路由

- 根/子级/可选规则：`assets/AGENTS.template.md`、`assets/AGENTS.scoped.template.md`、`assets/AGENTS.optional-sections.md`。
- 计划、进度与审查：`assets/development-plan.template.md`、`assets/completion-progress.template.md`、`assets/automated-review-evidence.template.md`、`assets/automated-review-output.template.json`；交付包会校验完整字段、结构化命令执行、当前 run/code 和阶段状态。
- 交付证据模板：`assets/requirement-traceability.template.md`、`assets/context-manifest.template.md`、`assets/reuse-source-context.template.md`、`assets/reuse-evidence.template.json`、`assets/project-commands.template.json`、`assets/multi-agent-evidence.template.json`、`assets/independent-agent-input.template.json`、`assets/independent-agent-output.template.json`、`assets/frontend-evidence.template.json`、`assets/swimlane-evidence.template.json`。
- 模块日志：`assets/execution-log-index.template.md`、`assets/execution-run.template.md`、`assets/module-latest.template.md`；完成门绑定当前 run、模块 `latest.md` 与紧凑索引。
- 系统与模块泳道：`assets/generate-agents-md-swimlanes.html`、`scripts/browser_test_swimlane.mjs`。
- 详细事实提取：`references/extraction-checklist.md`，只在对应章节适用时读取。
- 受控敏感配置：`references/sensitive-configuration-policy.md`，仅在用户本次明确授权处理，或明确要求只读审查该策略或隔离效果时完整读取。
- 外部多模型、证据复用、浏览器验收：分别按触发条件读取 `references/multi-model-review-policy.md`、`references/evidence-reuse-policy.md`、`references/browser-validation-policy.md`。
- 失败关闭实现：`scripts/validate_*.py`；回归：`scripts/test_*.py`；mutation：`scripts/run_mutation_checks.py`；一键自检：`scripts/validate_skill.py`。
