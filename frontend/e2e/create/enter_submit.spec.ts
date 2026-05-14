import { test, expect, selectors } from "../conftest";

test("pressing Enter in prompt submits generate", async ({ page, user }, testInfo) => {
  // Desktop only: mobile relies on form submit behavior.
  test.skip(testInfo.project.name === "mobile", "Enter submit is desktop-only UX");

  const sel = selectors(testInfo.project.name);
  await page.addInitScript((t: string) => localStorage.setItem("you2music.jwt", t), user.token);
  await page.goto("/");
  await expect(page.locator(sel.authPage)).toBeHidden();

  await page.locator(sel.prompt).fill("enter submit");
  await page.locator(sel.prompt).press("Enter");

  await expect(page.locator(sel.jobId)).not.toHaveText("-");
});
