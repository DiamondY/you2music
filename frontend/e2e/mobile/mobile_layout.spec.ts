import { test, expect, selectors } from "../conftest";

test("mobile layout shows mobile panels and hides pc layout", async ({ page, user }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile", "mobile-only");
  const sel = selectors(testInfo.project.name);
  await page.addInitScript((t: string) => localStorage.setItem("you2music.jwt", t), user.token);
  await page.goto("/");

  await expect(page.locator(sel.authPage)).toBeHidden();
  await expect(page.locator(sel.mobilePanels)).toBeVisible();
  await expect(page.locator(sel.mobileTabBar)).toBeVisible();
  await expect(page.locator(sel.pcLayout)).toBeHidden();
});
