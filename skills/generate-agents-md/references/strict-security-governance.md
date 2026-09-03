# 可选严格安全治理合同

仅在选择 `strict-security`，或在 `project` 模式显式选择 `authorization-mode=local-controlled-same-user` 时完整加载。默认 `delivery-first-local-coordination` 不加载本文件。本文件不改变唯一写者、身份分离、独立验收或交付闭环要求。

## 1. 一次性 system-governance bootstrap

严格模式优先使用项目无法开启的宿主原生 trusted runtime verifier/receipt；人工明确授权并接受“同一 OS 用户可访问私钥”的残余风险时，才可使用 `local_controlled_same_user`。receipt 必须披露 `same_os_user_can_access_private_key_not_host_native_attestation`，不得命名为 host-attested、host-native 或 unforgeable。

canonical matrix 只给 `system-governance-bootstrap/bootstrap_system_governance/system-governance` 一行 `external-explicit-only`。它仅引导新稳定模块登记所需、由外部授权列出的精确治理目标；该 actor 的其他所有动作以及其他 actor 的 bootstrap 动作全部固定 `deny`。项目 prose、Dispatcher、普通 receipt 或项目内 validator 不能新增、复制或扩大该能力。

本机受控 envelope、bootstrap payload、普通模块写租约与 detached signature 分别使用 `assets/local-controlled-trust-envelope.schema.json`、`assets/system-governance-bootstrap-receipt.schema.json`、`assets/local-controlled-module-write-lease.schema.json` 和对应的独立 detached-signature schema。外部用户授权必须固定项目外公钥的 raw Ed25519 SHA-256；私钥不得读取、搜索、复制、进入 prompt/log/workspace。验证器只接受严格整数 schema version，以及精确表示 64-byte Ed25519 签名的 86 字符规范无填充 Base64URL。项目根、envelope/public key/payload/signature/replay/registry、owned paths 与 targets 必须与模板、schema、CLI 和运行时一致，且逐级大小写拼写精确、canonical、无 symlink/hard-link alias。外部工件与持久状态必须从实际 open fd 读取并把 fstat 身份绑定同时刻 lstat 名称；lock、ledger/registry、target 与父目录在读取、判重、替换和 fsync 的关键步骤前后复核 dev/ino，目录 fsync fd 必须匹配冻结 parent dev/ino。未知键、缺失工件、公钥替换、path alias、symlink-loop、无效事件链、独立 ID 复用、过期、越权、漂移及竞态都只输出稳定 JSON 错误代码，不泄漏 argparse、路径、Errno 或 traceback。

签名 bootstrap payload 的闭集必须包含唯一 `replay_state_path`；CLI 的 `--replay-state` 和实际 `FileReplayGuard.state_path` 必须与其逐字、canonical 身份一致。在比较通过前不得创建 lock、创建 ledger 或修改另一个 ledger；同一 envelope 改用 ledger B 必须在消费前失败关闭。

bootstrap v1 保持原 schema 与语义，只能按 v1 验证，不得解释或升级为 v2。bootstrap v2 使用独立签名域，只允许更新已存在的根 `AGENTS.md` 与 `docs/agents/module-agent-governance.md`；闭集 payload 必须逐项绑定两项 `governance_targets` 的项目相对 canonical 路径、pre/post SHA-256 与字节数，M11 的 module key、稳定标题与精确 owned paths 登记，pre/post policy SHA-256、pre/post authority-matrix SHA-256 及 `bootstrap_candidate_sha256`。缺失 owned leaf 只验证 canonical 项目相对路径、最近已存在祖先的真实大小写和目录身份、全链无 symlink、与现有模块边界无重叠；bootstrap 不创建任何业务 leaf。v2 成功后的 `next_authority` 固定为 `local-controlled-module-write-lease-required`。

bootstrap 顺序不可调换：

1. 外部用户授权精确项目、module key/title、治理目标、公钥指纹、时效与候选哈希；
2. 验证 detached Ed25519 签名和 closed schema，在外部持久 ledger 中原子消费唯一 nonce/receipt；
3. 一次事务只登记该模块稳定标题和无重叠 owned paths，并同步必须的治理索引；
4. 原子记录 operation/receipt 已消费，使 bootstrap 权限永久失效；
5. v1 重新按原合同取得宿主原生唯一活动 write lease；v2 只能取得下述显式本机受控普通模块租约。两者不得互相解释、自动 fallback 或扩大能力。

任一步失败都不得虚报完整登记；bootstrap 不授权业务代码、普通共享记录、review、acceptance、black-box、aggregate、release、close 或 completion，也不减免 writer/gate 的身份分离。

## 2. 显式本机受控普通模块写租约

`local_controlled_module_write_lease` 使用独立 envelope/signature domain、closed schema 与模板，并签名绑定：显式授权 ID、固定 caveat、项目外唯一 `registry_path`、项目/module/title/Agent/run/assigned model/reasoning/role、精确 project-relative `owned_paths` 与单文件 `targets`、baseline path/hash、policy 与 authority-matrix hash、base/post candidate SHA-256、code version、Build ID、receipt/nonce/lease ID 及有效期。assigned identity 仅是授权绑定，不证明实际 runtime。有效期从 `not_before` 起最多 15 分钟；v1 不提供撤销字段或伪造撤销状态，安全停止依靠不签发新租约、唯一 active 约束和最短 TTL，到期后必须新签发。

默认共享记录 updater 另固定读取项目内 `docs/governance/module-writer-registry.json`：每个 module 只能有一个 `module-maintainer` 活动条目，module、Agent、run、lease ID 全局唯一，并精确绑定 AGENTS ownership、稳定标题和 write lease；调用参数不能自行成为授权来源。写入前后均校验 registry SHA。它是协同完整性记录，不是同用户不可伪造的安全证明。

固定外部 registry 使用严格 closed schema、唯一 no-follow lock 与可重算的 SHA-256 事件链。`receipt_id`、`nonce`、`lease_id` 分别在该唯一已签名 registry 中全局不可复用；同一 `(project_root,module_key)` 同时最多一个未到期 active lease，且同一 Agent 或 run 不得跨 module 持有 active lease。CLI/实际 registry 与签名路径不一致时必须在创建 lock/registry 前失败，禁止换 registry 重放。activate 只登记验证通过的租约；validate 不修改 registry；每次 apply 都重新验证签名、有效期、registry active 状态、当前 baseline/policy/authority/ownership、目标 pre/post hash 和 fd/inode/parent 身份。

普通租约只允许 `implementation` 或 `module-maintainer` 对签名 targets 执行 `write`、`design`、`implement` 或 `write_module_artifacts`；固定禁止 review、acceptance、black-box、aggregate、issue-independent-verdict、release、close、completion 与 system manifest。guarded apply 一次只替换一个已存在普通文件，不创建业务路径；replacement 必须是项目外 canonical 单链接普通文件，目标必须在 owned path 内且签名 target 精确匹配。写文件与 registry 追加使用两个持久步骤，不能宣称跨文件原子：若文件已成功落盘并 fsync、但 registry 记录失败，CLI 必须返回 `status=PARTIAL`、`complete=false` 和稳定错误码，后续不得把该次操作报告为成功或自动重试。

现有宿主证明租约/更新路径保持不变。只有 `project` 模式并且当前调用显式选择 `authorization-mode=local-controlled-same-user` 才能进入本机受控 CLI；缺少该选择或任何合同字段时失败关闭，绝不自动从宿主路径回退。
