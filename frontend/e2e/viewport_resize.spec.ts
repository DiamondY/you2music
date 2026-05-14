import { test, expect, selectors } from "./conftest";

test("viewport resize re-renders lists without breaking", async ({ page, user }, testInfo) => {
  const sel = selectors(testInfo.project.name);
  await page.addInitScript((t: string) => localStorage.setItem("you2music.jwt", t), user.token);
  await page.goto("/");
  await expect(page.locator(sel.authPage)).toBeHidden();

  // Trigger a job so history has at least one card to render.
  await page.locator(sel.prompt).fill("resize test");
  await page.locator(sel.generateBtn).click();
  await expect(page.locator(sel.jobId)).not.toHaveText("-");

  await page.setViewportSize({ width: 1200, height: 900 });
  await page.waitForTimeout(300);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(300);
});
