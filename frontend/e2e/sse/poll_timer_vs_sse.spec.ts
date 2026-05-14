import { test, expect, selectors } from "../conftest";

test("pollTimer does not spam /api/jobs when SSE is active", async ({ page, user }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "desktop-only");
  const sel = selectors(testInfo.project.name);
  await page.addInitScript((t: string) => localStorage.setItem("you2music.jwt", t), user.token);

  let calls = 0;
  page.on("request", (req) => {
    if (req.url().includes("/api/jobs?ids=")) calls += 1;
  });

  await page.goto("/");
  await expect(page.locator(sel.authPage)).toBeHidden();
  await page.waitForTimeout(500);

  await page.locator(sel.prompt).fill("poll vs sse");
  await page.locator(sel.generateBtn).click();

  await page.waitForTimeout(3500);
  expect(calls).toBeLessThanOrEqual(2);
});
