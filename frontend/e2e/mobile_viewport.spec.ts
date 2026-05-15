import { test, expect } from "./conftest";

test("mobile viewport switch preserves mobile layout", async ({ page, user }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile", "mobile viewport check runs only in mobile project");

  await page.addInitScript((token: string) => localStorage.setItem("you2music.jwt", token), user.token);
  await page.goto("/");
  await expect(page.locator("#authPage")).toBeHidden();

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator("#mobilePanels")).toBeVisible();
  await expect(page.locator("#mobileTabBar")).toBeVisible();
  await expect(page.locator("#pcLayout")).toBeHidden();

  await page.setViewportSize({ width: 430, height: 932 });
  await expect(page.locator("#mobilePanels")).toBeVisible();
  await expect(page.locator("#mobileTabBar")).toBeVisible();
  await expect(page.locator("#panelCreate")).toBeVisible();
});
