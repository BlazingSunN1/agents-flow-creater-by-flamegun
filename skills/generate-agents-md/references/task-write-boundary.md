# 任务写入边界

在项目任务准备写文件，或用户明确要求维护 Skill/插件时加载本文件。它用于防止项目 Agent 把普通模块租约误当成全局 Skill/插件写权限；不替代项目自身的模块 ownership、唯一写者和独立验收规则。

## 1. 两类互斥任务

- `project-agent`：只写规范项目根或分配的隔离 worktree 内、且属于当前模块 ownership 的目标。全局 Skill/插件源码、Codex 插件缓存和 Skill 直装目录一律只读。
- `skill-maintainer`：仅当当前用户请求明确要求修改 Skill/插件时启用。必须绑定一个精确维护源码根；历史授权、父子层级、项目模块租约、审查身份或同一 OS 用户身份都不能继承为授权。

任务开始时先解析规范绝对路径。目标位于精确根内还不代表拥有模块写权；项目 Agent 仍须满足项目 AGENTS.md 的 ownership 和唯一活动 writer 规则。两种角色不得在同一 run 中切换或混用。

## 2. 写入前校验

对本次准备修改的每个路径运行：

```bash
python3 scripts/validate_task_write_scope.py \
  --role project-agent \
  --project-root /absolute/project/root \
  --module-key m01 \
  --ownership-file AGENTS.md \
  --target relative/or/absolute/target
```

Skill/插件维护任务必须使用：

```bash
python3 scripts/validate_task_write_scope.py \
  --role skill-maintainer \
  --maintenance-root /absolute/authorized/source/root \
  --explicit-user-authorization \
  --authorization-source current-user-request \
  --target relative/or/absolute/target
```

校验器要求现有非宽泛项目根、规范 `AGENTS.md` 与已登记 module ownership，使用 `resolve(strict=False)` 规范化现有父路径，并拒绝绝对越界、`..` 等价越界和已有符号链接逃逸。调用方不能关闭默认保护或用 `/`、用户主目录、Skill/插件源码根冒充项目根；项目根内任何含现有源码标记的嵌套 Skill/插件目录，以及新建 `SKILL.md` 或 `.codex-plugin/plugin.json` 标记，也必须切换到精确根 `skill-maintainer`，不能靠扩大项目根或登记 ownership 放行。项目目录目标还会扫描后代源码标记和符号链接；维护目录目标同样拒绝后代符号链接；两者无法完整扫描时均失败关闭，避免递归工具越过声明边界。维护角色只允许写精确维护源码根，不能顺带修改兄弟 Skill、插件或其他受保护目录。`--explicit-user-authorization` 和 `--authorization-source` 是可审计声明，不是宿主对聊天来源的密码学证明。

## 3. 源码、缓存与安装副本

缓存和直装副本是派生产物，不是维护入口。只修改已授权的源码根，完成源码验证后再执行已登记的 cachebuster 与重装流程；不得直接编辑 `~/.codex/plugins`、`~/.codex/skills` 或其他安装副本来制造同步结果。发现副本漂移时，报告差异并从源码重建。

项目任务发现全局 Skill/插件有问题时，把它记录为独立维护建议并继续项目根内可安全完成的工作；不得借修项目之名修改全局能力。维护任务若发现目标根已有他人改动，先保留并核对 diff，只做请求范围内的最小修改，不覆盖或回退陌生变更。

## 4. 能力边界

`validate_task_write_scope.py` 只验证调用方声明的目标，不能拦截绕过它的直接 shell/文件 API，因此不能提供 OS 级隔离。只有宿主确实启用了 workspace 写沙箱、独立 worktree、容器或 OS 权限时，才可声明文件系统级强制；`audit-only` 运行会明确给出这一限制。

缺少宿主隔离不会阻塞项目根内的普通交付，但不得声称已经技术阻止同用户越权写入。越界目标和嵌套 Skill/插件源码目标必须在写前失败；不能通过扩大项目根、把插件目录登记成业务模块 ownership、复用旧授权或直接改缓存绕过。共享记录 updater 仅支持 POSIX 原子锁语义；原生 Windows 项目必须从 WSL 执行，禁止静默降级为无锁写入。
