# 受控敏感连接配置策略

仅当用户在当前项目任务中明确要求并授权记录密码，或明确要求审查本策略及其隔离效果时读取本文件。普通生成、模板抽取和公共化任务不得加载；只读审查不得把审查权限扩展为记录、复述或传播真实值的授权。

## 允许边界

- 仅限 `project` 模式和用户指定的项目专属文件；`public-template` 始终禁止真实值。
- `password`、`passwd` 赋值及 URI 内嵌用户名/密码只由目标 AGENTS.md 内的有效授权章节放行；校验器自动识别，不要求重复传参。
- 授权不扩展到 Token、API Key、私钥、Cookie、会话材料或其他凭据；这些仍须使用秘密管理机制。
- 不得把真实值复制到回复、日志、公共模板、外部模型提示或无关文件。

## 授权记录

在目标 AGENTS.md 的 `Password Authorization` 章节记录：

- `Access boundary`（必填）：允许访问者和边界，不得写无限制、待定值或占位符。
- `Authorized endpoints`（仅 URI 内嵌用户名/密码时必填）：逗号分隔、不含凭据的 `scheme://host[:port][/path-prefix]` 列表。同源授权允许其全部路径；指定路径时仅允许该路径及其子路径。协议、主机和有效端口必须一致，HTTP 80 与 HTTPS 443 按默认端口归一。
- `Scope`、`Purpose`、`Update method`（可选说明）：旧文档继续兼容；一旦填写，同样不得使用待定值或占位符。

最小示例：

```markdown
## Password Authorization

- Access boundary: project maintainers only
- Authorized endpoints: https://service.example.test/api
```

授权依据必须可追溯到当前用户请求。不得猜测、恢复、扫描或输出未提供的秘密。

## 校验

```bash
python3 scripts/validate_agents_md.py TARGET --mode project --strict
```

完成交付包和系统聚合校验会从同一份 AGENTS.md 自动继承授权，不需再传开关。旧版 `--allow-passwords` 仍作为兼容参数接受，但参数本身不能授权或绕过缺失、无效、越界的授权记录。任何必要字段缺失、端点越界、模式不符或其他凭据类型命中都失败关闭。
