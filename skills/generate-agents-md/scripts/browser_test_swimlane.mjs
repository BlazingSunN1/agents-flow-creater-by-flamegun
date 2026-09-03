function validateBrowserUrl(url) {
  const parsed = new URL(url);
  const credentials = parsed.username || parsed.password;
  if (!["http:", "https:"].includes(parsed.protocol) || credentials || !parsed.hostname) {
    throw new Error(`unsupported browser URL: ${parsed.protocol || "missing protocol"}`);
  }
}

export async function runSwimlaneBrowserTest(tab, url) {
  validateBrowserUrl(url);
  await tab.goto(url);
  await tab.playwright.waitForLoadState({ state: "domcontentloaded", timeoutMs: 10000 });
  const results = [];
  for (const id of ["module-m00", "module-m01", "module-m02", "module-m03", "module-m04"]) {
    await tab.playwright.locator(`nav [data-open-module="${id}"]`).click();
    const state = await tab.playwright.evaluate((wanted) => {
      const detail = document.getElementById(wanted);
      return {
        opened: detail?.open === true,
        openCount: document.querySelectorAll("details.module-detail[open]").length,
        headers: detail?.querySelectorAll(".lane-head").length || 0,
        connectors: detail?.querySelectorAll(".module-flow").length || 0,
      };
    }, id);
    if (!state.opened || state.openCount !== 1 || state.headers < 3 || state.connectors < 1) {
      throw new Error(`module closure failed: ${id} ${JSON.stringify(state)}`);
    }
    results.push({ id, ...state });
    await tab.playwright.locator(`#${id} .back-link`).click();
    const afterBack = await tab.playwright.evaluate(() => document.querySelectorAll("details.module-detail[open]").length);
    if (afterBack !== 0) throw new Error(`back closure failed: ${id}`);
  }
  const keyboardBackResults = [];
  for (const key of ["Enter", " "]) {
    await tab.playwright.locator('nav [data-open-module="module-m02"]').click();
    await tab.playwright.locator('#module-m02 .back-link').press(key);
    const state = await tab.playwright.evaluate(() => ({
      hash: location.hash,
      openCount: document.querySelectorAll("details.module-detail[open]").length,
    }));
    keyboardBackResults.push({ key, ...state });
    if (state.hash !== "#system-overview" || state.openCount !== 0) {
      throw new Error(`keyboard back closure failed: ${key} ${JSON.stringify(state)}`);
    }
  }
  await tab.playwright.locator('nav [data-open-module="module-m03"]').press("Enter");
  const finalState = await tab.playwright.evaluate(() => {
    const m02Text = document.getElementById("module-m02")?.textContent || "";
    const m03Text = document.getElementById("module-m03")?.textContent || "";
    const overviewText = document.getElementById("system-overview")?.textContent || "";
    const pageText = document.body.textContent || "";
    const visibleInViewport = (element) => {
      const rect = element.getBoundingClientRect();
      return rect.bottom > 0 && rect.top < innerHeight && rect.right > 0 && rect.left < innerWidth;
    };
    const requiredM03Edges = [
      ["m03-minimum-result", "m03-affected-checks"],
      ["m03-affected-checks", "m03-freeze-result"],
      ["m03-freeze-result", "m03-harden-after-freeze"],
      ["m03-harden-after-freeze", "m03-mapped-verification"],
      ["m03-mapped-verification", "m03-regression-preservation"],
    ];
    return ({
    keyboardOpened: document.getElementById("module-m03")?.open === true,
    overviewHeaders: document.querySelectorAll("#system-overview .lane-head").length,
    overviewConnectors: document.querySelectorAll("#system-overview .flow").length,
    horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
    m03VisibleLaneHeads: [...document.querySelectorAll("#module-m03 .lane-head")].filter(visibleInViewport).length,
    m03VisibleConnectors: [...document.querySelectorAll("#module-m03 .module-flow")].filter(visibleInViewport).length,
    m03OrderedTopology: requiredM03Edges.every(([from, to]) => Boolean(
      document.querySelector(`#module-m03 .module-flow[data-from="${from}"][data-to="${to}"]`),
    )),
    maxRoundStop: m02Text.includes("最多 6 轮")
      && m02Text.includes("incomplete")
      && m02Text.includes("同候选哈希门禁")
      && m02Text.includes("哈希链接 checkpoint")
      && m02Text.includes("恢复 receipt 模式校验")
      && m02Text.includes("缺失/漂移则 blocked")
      && m02Text.includes("冻结 canonical locator/SHA")
      && m02Text.includes("同 current baseline"),
    roleNeutralWriterLease: m02Text.includes("父/主/子层级不授予写权")
      && m02Text.includes("协调裁决者始终只读且不持 writer lease")
      && m02Text.includes("Agent ID 与 run ID 均不同")
      && m02Text.includes("canonical 实现/维护 Agent")
      && m02Text.includes("唯一活动模块协调租约")
      && m02Text.includes("默认本地协调，严格模式才追加宿主证明")
      && m02Text.includes("同一身份不得通过切换角色或 run 自审自写")
      && m02Text.includes("Dispatcher 也始终只读")
      && m02Text.includes("写者不得自审/黑盒/验收/裁决/关闭")
      && !m02Text.includes("父维护 Agent 只裁决并写本模块"),
    moduleClosure: document.getElementById("module-m00")?.textContent.includes("绑定唯一维护 Agent")
      && document.getElementById("module-m00")?.textContent.includes("不同 Agent 审查")
      && document.getElementById("module-m00")?.textContent.includes("所有受影响模块")
      && document.getElementById("module-m00")?.textContent.includes("独立写系统清单")
      && document.getElementById("module-m00")?.textContent.includes("Dispatcher 只读重验"),
    standardDecisionBranches: document.getElementById("m00-branch-yes")?.textContent.trim() === "是"
      && document.getElementById("m00-branch-no")?.textContent.includes("否")
      && Boolean(document.getElementById("m00-system-delivery"))
      && Boolean(document.getElementById("m00-module-return")),
    overviewSystemAggregate: Boolean(document.getElementById("overview-system-aggregate"))
      && Boolean(document.getElementById("overview-to-system-aggregate"))
      && Boolean(document.getElementById("overview-system-aggregate-to-delivery"))
      && document.getElementById("overview-system-aggregate")?.nextElementSibling?.textContent.includes("独立写系统清单")
      && document.getElementById("overview-system-aggregate")?.nextElementSibling?.textContent.includes("Dispatcher 只读重验"),
    gateOutputAttestation: Boolean(document.getElementById("m04-output-result"))
      && Boolean(document.getElementById("m04-output-result-to-decision"))
      && document.getElementById("module-m04")?.textContent.includes("codex-native-output-result")
      && document.getElementById("module-m04")?.textContent.includes("严格模式追加宿主证明"),
    semanticSwimlaneBatching: pageText.includes("flow_impact=none|changed|uncertain")
      && pageText.includes("首次下游依赖或阶段交接前至多写图一次")
      && pageText.includes("阶段结束只对适用泳道校验新鲜度")
      && m03Text.includes("先判定 swimlane_applicable")
      && m03Text.includes("无适用泳道时无图无门禁")
      && m03Text.includes("稳定候选批量写图"),
    triggeredReview: Boolean(document.getElementById("m03-review-trigger"))
      && Boolean(document.getElementById("m03-trigger-review"))
      && Boolean(document.getElementById("m03-trigger-continue"))
      && Boolean(document.getElementById("m03-review-pass-decision"))
      && m03Text.includes("闭环候选或人工")
      && m03Text.includes("继续实现，仅累计增量")
      && m03Text.includes("审查当前指纹")
      && m03Text.includes("结论失效后重审"),
    deterministicGateIntegrity: m03Text.includes("门禁规划器只读输出")
      && m03Text.includes("唯一租约写者 CAS 合并")
      && m03Text.includes("每个可执行门禁 receipt 绑定当前输入指纹")
      && m03Text.includes("最终聚合校验只在闭环或完成阶段接收同一交付契约")
      && m03Text.includes("实时执行且无自引用 receipt")
      && m03Text.includes("移动 Web 运行浏览器移动门禁")
      && m03Text.includes("原生移动运行 native_mobile_tests")
      && m03Text.includes("跨端变更同时运行两套门禁")
      && m03Text.includes("逐项绑定实际工件")
      && m03Text.includes("人工触发由独立审查者执行")
      && m03Text.includes("不提前触发最终聚合")
      && m03Text.includes("有适用泳道且无流程变化才运行 swimlane_freshness")
      && m03Text.includes("普通用户可见文本不自动启动 UI/UX 原型 Agent"),
    resultFirstHardening: Boolean(document.getElementById("m03-minimum-result"))
      && Boolean(document.getElementById("m03-affected-checks"))
      && Boolean(document.getElementById("m03-freeze-result"))
      && Boolean(document.getElementById("m03-harden-after-freeze"))
      && Boolean(document.getElementById("m03-mapped-verification"))
      && Boolean(document.getElementById("m03-regression-preservation"))
      && m03Text.includes("真实入口跑通最小业务流程")
      && m03Text.includes("冻结代码版本、Build ID、验收命令、可观测结果和证据 SHA-256")
      && m03Text.includes("冻结后才启动非必要门禁")
      && m03Text.includes("发生回归时先恢复最小业务闭环")
      && m03Text.includes("治理完整或门禁通过不能替代业务成果"),
    validationTiers: overviewText.includes("validate_skill.py --quick")
      && overviewText.includes("validate_skill.py --affected")
      && overviewText.includes("validate_skill.py --full")
      && pageText.includes("快速检查不能作为闭环、发布或安装验收")
      && pageText.includes("严格安全正文按触发条件独立加载")
      && m03Text.includes("quick / affected / full")
      && m03Text.includes("未知影响自动升 full")
      && m03Text.includes("最多3轮/同错2次"),
    });
  });
  if (!finalState.keyboardOpened || finalState.overviewHeaders !== 4 || finalState.overviewConnectors < 1 || finalState.horizontalOverflow || finalState.m03VisibleLaneHeads < 1 || finalState.m03VisibleConnectors < 1 || !finalState.m03OrderedTopology || !finalState.maxRoundStop || !finalState.roleNeutralWriterLease || !finalState.moduleClosure || !finalState.standardDecisionBranches || !finalState.overviewSystemAggregate || !finalState.gateOutputAttestation || !finalState.semanticSwimlaneBatching || !finalState.triggeredReview || !finalState.deterministicGateIntegrity || !finalState.resultFirstHardening || !finalState.validationTiers) {
    throw new Error(`overview or keyboard closure failed: ${JSON.stringify(finalState)}`);
  }
  const logs = await tab.dev.logs({ levels: ["error", "warn"], limit: 100 });
  if (logs.length) throw new Error(`page console errors: ${JSON.stringify(logs)}`);
  return { results, keyboardBackResults, finalState, logs };
}
