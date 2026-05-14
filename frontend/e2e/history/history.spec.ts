import { test, expect, selectors } from "../conftest";

test("history page lists jobs after generate @smoke", async ({ page, user }, testInfo) => {
  const sel = selectors(testInfo.project.name);
  await page.addInitScript((t: string) => localStorage.setItem("you2music.jwt", t), user.token);
  await page.goto("/");
  await expect(page.locator(sel.authPage)).toBeHidden();

  await page.locator(sel.prompt).fill("history test");
  await page.locator(sel.generateBtn).click();
  await expect(page.locator(sel.jobId)).not.toHaveText("-");

  const jobId = (await page.locator(sel.jobId).textContent())?.trim() || "";
  if (testInfo.project.name === "mobile") {
    await page.locator('#mobileTabBar [data-tab="history"]').click();
  }
  await expect(page.locator(`[data-job-id="${jobId}"]`)).toBeVisible({ timeout: 30_000 });
});
