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
  for (const id of ["module-m01", "module-m02", "module-m03", "module-m04"]) {
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
  await tab.playwright.locator('nav [data-open-module="module-m03"]').press("Enter");
  const finalState = await tab.playwright.evaluate(() => ({
    keyboardOpened: document.getElementById("module-m03")?.open === true,
    overviewHeaders: document.querySelectorAll("#system-overview .lane-head").length,
    overviewConnectors: document.querySelectorAll("#system-overview .flow").length,
    horizontalOverflow: document.body.scrollWidth > document.documentElement.clientWidth,
    maxRoundStop: document.getElementById("module-m02")?.textContent.includes("最多 6 轮")
      && document.getElementById("module-m02")?.textContent.includes("incomplete")
      && document.getElementById("module-m02")?.textContent.includes("同候选哈希门禁"),
  }));
  if (!finalState.keyboardOpened || finalState.overviewHeaders !== 4 || finalState.overviewConnectors < 1 || finalState.horizontalOverflow || !finalState.maxRoundStop) {
    throw new Error(`overview or keyboard closure failed: ${JSON.stringify(finalState)}`);
  }
  const logs = await tab.dev.logs({ levels: ["error", "warn"], limit: 100 });
  if (logs.length) throw new Error(`page console errors: ${JSON.stringify(logs)}`);
  return { results, finalState, logs };
}
