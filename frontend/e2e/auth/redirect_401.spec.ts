import { test, expect, selectors } from "../conftest";

test("401 on /api/auth/me clears session and returns to login", async ({ page, user }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "desktop-only");
  const sel = selectors(testInfo.project.name);
  await page.addInitScript((t: string) => localStorage.setItem("you2music.jwt", t), user.token);

  // Force the session check to fail once.
  await page.route(
    "**/api/auth/me",
    async (route) => {
      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ detail: "token expired" }),
      });
    },
    { times: 1 }
  );

  await page.goto("/");
  await expect(page.locator(sel.authPage)).toBeVisible();
});
