# 受控敏感连接配置策略

仅当用户在当前项目任务中明确要求并授权记录密码，或明确要求审查本策略及其隔离效果时读取本文件。普通生成、模板抽取和公共化任务不得加载；只读审查不得把审查权限扩展为记录、复述或传播真实值的授权。

## 允许边界

- 仅限 `project` 模式和用户指定的项目专属文件；`public-template` 始终禁止真实值。
- `password`、`passwd` 赋值及 URI 内嵌用户名/密码可在明确授权后使用 `--allow-passwords` 放行。
- 授权不扩展到 Token、API Key、私钥、Cookie、会话材料或其他凭据；这些仍须使用秘密管理机制。
- 不得把真实值复制到回复、日志、公共模板、外部模型提示或无关文件。

## 必填授权记录

在目标 AGENTS.md 的 `Password Authorization` 章节逐项记录非空字段：

- `Scope`：允许存储的位置和对象。
- `Purpose`：限定用途。
- `Update method`：轮换或更新方式。
- `Access boundary`：允许访问者和边界，不得写无限制或待定值。
- `Authorized endpoints`：每个含 URI userinfo 的端点都按 `scheme://host:port/path` 规范化后逐项列出。

授权依据必须可追溯到当前用户请求。不得猜测、恢复、扫描或输出未提供的秘密。

## 校验

```bash
python3 scripts/validate_agents_md.py TARGET --mode project --allow-passwords --strict
```

若生成完成交付包，同时给 `validate_delivery_bundle.py` 传入 `--allow-passwords`。任何授权字段缺失、端点未登记、模式不符或其他凭据类型命中都失败关闭。
