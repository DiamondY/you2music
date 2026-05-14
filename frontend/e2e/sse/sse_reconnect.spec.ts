import { test, expect, selectors } from "../conftest";

test("SSE reconnects after abort and avoids aggressive polling", async ({ page, user }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "keep SSE test on desktop for stability");

  const sel = selectors(testInfo.project.name);
  await page.addInitScript((t: string) => localStorage.setItem("you2music.jwt", t), user.token);

  let eventsReq = 0;
  await page.route("**/api/events", async (route) => {
    eventsReq += 1;
    if (eventsReq === 1) {
      await route.abort();
      return;
    }
    await route.continue();
  });

  let refreshReq = 0;
  page.on("request", (req) => {
    const url = req.url();
    if (url.includes("/api/jobs?ids=")) refreshReq += 1;
  });

  await page.goto("/");
  await expect(page.locator(sel.authPage)).toBeHidden();

  // Give the reconnect loop time to fire (1500ms in UI code).
  await page.waitForTimeout(2500);
  expect(eventsReq).toBeGreaterThanOrEqual(2);

  // Trigger a job and ensure polling doesn't spam (SSE running => interval ~8000ms).
  await page.locator(sel.prompt).fill("poll check");
  await page.locator(sel.generateBtn).click();
  await page.waitForTimeout(3000);
  expect(refreshReq).toBeLessThanOrEqual(2);
});
