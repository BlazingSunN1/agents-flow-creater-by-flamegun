# 浏览器与前端验收契约

泳道或前端代码适用时完整读取本文件。

## 泳道

- 工作集声明 module→Changed files 映射并纳入缓存键；每张模块图精确绑定所属文件，系统图和模块图不得复用 path/inode。
- 阶段同步或流程触发更新后，验证泳道头、连线、模块进入、返回和键盘闭环。
- 本地 HTML 先通过已登记开发服务或仅绑定回环地址的静态服务暴露为 HTTP(S)，健康后再打开；`file://` 不作为自动化证据。
- URL 路径、预览根、系统图工件、入口哈希和实时响应体哈希必须一致。

## 前端

- 每次前端修改同时使用 `browser:control-in-app-browser` 做人工式点击闭环，并运行项目真实 Playwright/Cypress。
- 使用 `assets/frontend-evidence.template.json` 记录实时入口、预览根、入口工件与哈希、实时响应哈希、同字节 UTF-8 DOM 快照、CSS id 点击/断言目标、run/time/viewport、转录、PNG、argv 哈希和原生 E2E 报告。
- 入口身份必须等于命令清单权威声明；入口是项目内普通文件且验证时在线。DOM/CSS/ARIA/inert/disabled 必须证明目标可见可用，项目相对 CSS 按文档顺序、优先级和 `!important` 重放，无法稳定处理的 `@import` 失败关闭。
- 每个动作记录应用内浏览器计算的 `visible=true`、`enabled=true`。点击绑定前后 UTF-8 DOM 快照路径/哈希，证明声明的断言节点发生可见语义变化；全部点击与断言按声明顺序和次数执行。
- PNG 必须完整解码，拒绝非法关键块和不连续 IDAT，扫描线与尺寸一致且像素覆盖视口；原生报告绑定真实 runner、测试身份和终态。
- completion 绑定当前原生独立 BLACK_BOX Agent。桌面 PC 默认适用；仅当批准范围包含移动、触控或响应式时增加独立移动证据。
