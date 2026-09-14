# scripts/ 作用域规则（Codex Sol 维护者）

## 作用域

- 本文件仅约束 `skills/generate-agents-md/scripts/**` 内的实现、脚本与测试规则；它是 `generate-agents-md` 维护任务在唯一授权源码根 `/Users/kinglone/plugins/agents-flow-creater-by-flamegun` 内的子目录作用域文件，不是仓库根治理文件，也不把无关的 GencamApp `AGENTS.md` 当作父级。
- 不虚构模块登记表、租约登记册或永久 agent/session 编号；角色只按“活动写者/只读审查者”描述。
- 覆盖 `scripts/**` 之外的路径（含 `SKILL.md`、`assets/`、`references/`、插件清单、缓存与直装副本）必须回到 dispatcher 另行取得显式授权；插件缓存与直装目录在本作用域内一律只读。

## 写者边界

- 唯一活动写者是本任务实际调用的 Codex 原生 `gpt-5.6-sol`、`reasoning_effort=medium` 实现运行；它只能写入本轮已分配且已通过写前校验的作用域目标，不授予对插件缓存、安装目录或其他派生产物的直接写入权。
- GPT-6 审查者与 Dispatcher 严格只读：只做编排、最小上下文、检查与评审；不得创建、编辑、应用、复制、格式化任何代码、记录或产物。用户明确选择 Local Qwen 写者模式时才按专项参考切换，不得自动回退或混用 Sol/Qwen 身份。
- 写前读取：从目标向上直至仓库根的全部生效 `AGENTS.md` 祖先，以及目标目录之下所有适用的更深层级 `AGENTS.md`（不止一级），并在输出中报告实际读取路径与文件 SHA-256；不得静态断言“当前无父级 AGENTS”永远成立，每次运行都需实际重新检查祖先链。
- 写前对本轮每个目标运行：

```bash
python3 -B skills/generate-agents-md/scripts/validate_task_write_scope.py \
  --role skill-maintainer \
  --maintenance-root /Users/kinglone/plugins/agents-flow-creater-by-flamegun \
  --explicit-user-authorization \
  --authorization-source current-user-request \
  --target skills/generate-agents-md/scripts/AGENTS.md
```

- 以上命令从插件根目录（`/Users/kinglone/plugins/agents-flow-creater-by-flamegun`）运行；每个实际授权文件各运行一次校验，`--target` 替换为该文件的实际作用域相对路径（例如本轮仅 `skills/generate-agents-md/scripts/AGENTS.md`）。
- 该校验器只验证调用方声明的目标路径，不构成 OS 级隔离；不得声称已技术性阻止同用户越权写入。
- 本任务的作用域授权（用户已显式给出）持续有效：`scripts/**` 之外的路径如需工作，路由到使用既有用户授权的另一受限 run，不要求用户重复同意；本文件不授予任何缓存或安装写入。
- Sol 写者的 provider、精确模型、推理强度、session/turn、agent/run 与不可变本地 source snapshot 必须来自实际结构化运行记录，不得把一次性运行 ID 硬编码进本规则；型号或强度不符时停止依赖它的写入，禁止静默替换或降级。

## 输入与继承

- 子 agent 不会自动继承父会话完整聊天；下发输入仅限：最小用户目标、已批准约束、受影响路径、受影响测试、候选证据。
- 不传完整聊天、密钥、令牌、私钥或凭据明文；需要凭据时引用受控文档中的授权记录，不复制值。

## 验证与测试

- 测试优先跑受影响的最近测试：先确定改动映射到的测试文件，从插件根直接运行并捕获退出码与计数，不使用 `| tail` 等管道掩盖非零退出。updater 专属示例（仅当改动映射到 updater 记录逻辑时）：

```bash
python3 -B skills/generate-agents-md/scripts/test_update_project_record.py -q
```

- 全量 `unittest discover` 或 `validate_skill.py --json` 仅在改动确实映射到对应范围、目标已冻结且获得授权时才运行；本类仅文档/作用域任务只做 scoped 校验，不默认跑全量。

- 涉及 AGENTS 规则改动时，用 `validate_agents_md.py` 的 `--scope scoped` 校验对应子级文档；scoped 校验不可用时如实说明，不得宣称完成了根级或全项目验证，也不得为通过根级 schema 而伪造根治理或削弱检查。
- 测试必须直接运行：记录退出码、用例计数与当前候选 SHA-256；写者不得自评独立验收，独立验收由不同只读 Agent/run 执行。
- 合成/fixture 数据只允许显式出现在 `test_*` 或 `fixtures/` 中；不得用虚构 fixture 冒充真实模型/运行证据。

## 修复纪律

- 修复先保留失败测试，再最小修因；不得弱化门禁、删除断言或降低阈值来“通过”。
- 同一失败指纹（同测试+同错误码/断言）最多 2 次重复尝试，整体修复最多 3 轮；达到上限即停止并如实报告，不得扩大改动范围兜底。
- 存在未修复的相关缺陷或失败测试时，不得宣布完成；仅记录证据与未完成状态。

## 仓库卫生

- 保留脏工作区：不得执行未被请求的 `git stash/reset/stage/commit/push`、安装、部署或缓存重建；发现他人改动先保留并核对 diff，只做请求范围内的最小修改。
- 完成后报告：实际写入路径、SHA-256、执行的校验命令与退出码、未覆盖的验收项。

## 继承规则差距说明

- 本文件只收录与 `scripts/**` 直接相关的稳定规则；父级模板中的前端点击门禁、移动端、泳道图与进度日志等节并非一概豁免：仅本次纯文档、无流程影响的变更不适用泳道图/计划；未来凡涉及代码或流程影响的改动，必须基于事实评估是否适用。
- 不得静态断言本仓库“永远无生效的根级 `AGENTS.md`”；祖先链每次运行需实际检查。与 `SKILL.md`/`references/` 中历史条款冲突时，以本轮用户明确选择的 `gpt-5.6-sol/medium` 唯一写者策略为准，并同步修复冲突条款。
