---
name: strict-delivery-security
description: 为 Agents Flow 的项目交付显式启用同一用户边界内的签名租约、重放保护、宿主校验和 system-governance bootstrap。仅用于用户明确选择 local-controlled-same-user，或项目已有可验证高风险/合规映射要求宿主证明的场景；普通项目交付不得自动启用。
---

# Strict Delivery Security

这是 `$generate-agents-md` 的可选严格安全模块，不是默认流程。

## 启用条件

只在以下任一条件成立时继续：

- 当前用户明确要求 `authorization-mode=local-controlled-same-user`；或
- 项目内已有高风险/合规映射，明确要求宿主身份校验、签名租约或重放保护。

否则返回 `$generate-agents-md` 的 `delivery-first-local-coordination`。不得因“更安全”或通用最佳实践自行启用。

## 边界

- 仅用于 `project` 模式；公共模板不得包含真实主体、端点、路径或认证材料。
- 同一 OS 用户能访问本机签名材料时，这套机制只证明该用户边界内的授权与完整性，不证明 runtime 的实际宿主身份，也不等于不可伪造的 host-native attestation。
- 项目内公钥或调用方替换公钥都不是可信根；需要宿主证明时必须使用项目不可写的当前宿主校验器。
- 严格模式不得改变需求、验收条件、模块所有权或独立审查边界，也不得阻塞未映射的普通交付。

## 执行

完整读取同插件的 `../generate-agents-md/references/strict-security-governance.md`，按其中的 bootstrap、租约、guarded apply、receipt 与 replay 约束执行。统一入口为：

```bash
python3 ../generate-agents-md/scripts/flowctl.py strict --help
```

旧严格安全脚本路径仅作兼容，不作为文档入口。启用前记录触发证据和停用条件；完成后仍由 `$generate-agents-md` 的常规追踪、测试、独立黑盒和交付包门禁决定是否交付。
