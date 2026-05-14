import { test, expect, selectors } from "../conftest";

test("server error shows backend detail", async ({ page, user }, testInfo) => {
  // Only mock the first attempt; second click should hit real backend.
  await page.route(
    "**/api/generate",
    async (route) => {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "服务器错误" }),
      });
    },
    { times: 1 }
  );

  const sel = selectors(testInfo.project.name);
  await page.addInitScript((t: string) => localStorage.setItem("you2music.jwt", t), user.token);
  await page.goto("/");
  await expect(page.locator(sel.authPage)).toBeHidden();

  await page.locator(sel.prompt).fill("boom");
  await page.locator(sel.generateBtn).click();

  const toast = page.locator(sel.toast).first();
  await expect(toast).toBeVisible();
  await expect(toast).toContainText("服务器错误");
});
