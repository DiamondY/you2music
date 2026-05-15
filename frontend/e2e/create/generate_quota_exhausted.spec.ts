import { fillPrompt, test, expect, selectors, waitForAppReady } from "../conftest";

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
  await waitForAppReady(page, testInfo.project.name);

  await fillPrompt(page, testInfo.project.name, "quota exhausted");
  await page.locator(sel.generateBtn).click();

  await expect(page.locator(sel.error)).toBeVisible();
  await expect(page.locator(sel.error)).toContainText("今日配额已用完");
});
