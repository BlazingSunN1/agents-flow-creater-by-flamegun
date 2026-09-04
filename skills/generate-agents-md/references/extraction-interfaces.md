# 前端与泳道提取清单

仅在项目存在 Web 前端、交互式 HTML 或适用泳道时读取；细节以 `references/browser-validation-policy.md` 为准。

## 泳道

- 从实现入口、调用链、接口、配置和测试提取流程，文档仅作补充。先确认系统总览、模块图和外部依赖边界。
- 每次代码模块修改后只判定 `swimlane_applicable` 与 `flow_impact`：`none`, `changed`, or `uncertain`。无适用泳道不建空图；`none` 不改写图文件（do not rewrite the diagram file）；`uncertain` 做最小调查，不得为保险起见重画（must not redraw just in case）。
- `changed` 以模块、阶段和 stabilized candidate 批量更新，在首次依赖该图的下游步骤（first downstream consumer）或阶段交接前取较早者；每个模块、每个阶段、每个稳定候选至多写图一次。阶段结束只对适用泳道做一致性与新鲜度检查。
- 只有系统/跨模块边界、归属、顶层入口/出口、跨模块交接或外部依赖变化才更新总览；模块内部流程只更新模块图。
- 写图后通过本地回环 HTTP(S) 打开交互页面，人工式点击总览 → 模块 → 返回，并验证泳道头、连线、分支、内容与导航。

## 前端

- 每次前端代码变更必须从真实入口用应用内浏览器执行人工式点击闭环，并运行项目原生 Playwright/Cypress E2E；两者均通过才可验收。
- 覆盖状态/数据变化至可见结果，以及适用的校验、失败、重试和恢复分支；检查控制台、必要网络请求、控件可用性、关键内容裁切和横向溢出。
- 仅当批准范围明确包含移动 Web、触控或响应式行为时增加移动浏览器验证；原生移动使用登记的原生测试命令。无相关范围不强制移动适配。
- 入口 URL、服务根、DOM/截图/操作记录、E2E 命令和结果必须绑定同一候选与当前证据。任何 Bug、不可解释错误、失败请求或未通过原生 E2E 都不得标记完成。

## 统一入口

- `python3 scripts/flowctl.py check frontend ...`
- `python3 scripts/flowctl.py check swimlane ...`
- 泳道写入频率按语义候选控制；前端验证频率按前端代码变更控制，两者不要混淆。
