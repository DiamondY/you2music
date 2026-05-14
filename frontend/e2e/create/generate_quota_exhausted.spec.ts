import { test, expect, selectors } from "../conftest";

test("quota exhausted shows server detail @smoke", async ({ page, user }, testInfo) => {
  await page.route("**/api/generate", async (route) => {
    await route.fulfill({
      status: 429,
      contentType: "application/json",
      body: JSON.stringify({ detail: "今日配额已用完" }),
    });
  });

  const sel = selectors(testInfo.project.name);
  await page.addInitScript((t: string) => localStorage.setItem("you2music.jwt", t), user.token);
  await page.goto("/");
  await expect(page.locator(sel.authPage)).toBeHidden();

  await page.locator(sel.prompt).fill("quota exhausted");
  await page.locator(sel.generateBtn).click();

  const toast = page.locator(sel.toast).first();
  await expect(toast).toBeVisible();
  await expect(toast).toContainText("配额");
  await expect(toast).toContainText("今日配额已用完");
});
