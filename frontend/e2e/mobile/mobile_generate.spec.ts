import { test, expect, selectors } from "../conftest";

test("mobile generate flow works @smoke", async ({ page, user }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile", "mobile-only");
  const sel = selectors(testInfo.project.name);
  await page.addInitScript((t: string) => localStorage.setItem("you2music.jwt", t), user.token);
  await page.goto("/");

  await expect(page.locator(sel.authPage)).toBeHidden();
  await page.locator(sel.prompt).fill("mobile generate");
  await page.locator(sel.generateBtn).click();
  await expect(page.locator(sel.jobId)).not.toHaveText("-");
});
