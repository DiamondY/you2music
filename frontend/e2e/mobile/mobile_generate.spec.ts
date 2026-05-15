import { fillPrompt, test, expect, selectors, waitForAppReady } from "../conftest";

test("mobile generate flow works @smoke", async ({ page, user }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile", "mobile-only");
  const sel = selectors(testInfo.project.name);
  await page.addInitScript((t: string) => localStorage.setItem("you2music.jwt", t), user.token);
  await page.goto("/");

  await waitForAppReady(page, testInfo.project.name);
  await fillPrompt(page, testInfo.project.name, "mobile generate");
  const [generateResponse] = await Promise.all([
    page.waitForResponse((response) => response.url().includes("/api/generate") && response.request().method() === "POST"),
    page.locator(sel.generateBtn).click(),
  ]);
  expect(generateResponse.ok()).toBeTruthy();
  await expect(page.locator(sel.status)).toContainText(/排队中|生成完成|已完成/, { timeout: 30_000 });
});
