import { test, expect, selectors } from "./conftest";

test("toast is visible even when sticky player is present", async ({ page, user }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "desktop-only");
  const sel = selectors(testInfo.project.name);
  await page.addInitScript((t: string) => localStorage.setItem("you2music.jwt", t), user.token);
  await page.goto("/");
  await expect(page.locator(sel.authPage)).toBeHidden();

  await page.locator(sel.prompt).fill("sticky player");
  await page.locator(sel.generateBtn).click();
  await expect(page.locator(sel.jobId)).not.toHaveText("-");

  // Trigger an error toast without depending on backend by mocking one API call.
  await page.route(
    "**/api/jobs/history**",
    async (route) => {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "history error" }),
      });
    },
    { times: 1 }
  );
  await page.reload();
  const toast = page.locator(sel.toast).first();
  await expect(toast).toBeVisible();
});
