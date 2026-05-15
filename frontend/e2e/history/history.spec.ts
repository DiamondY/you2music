import { fillPrompt, test, expect, selectors, waitForAppReady } from "../conftest";

test("history page lists jobs after generate @smoke", async ({ page, user }, testInfo) => {
  const sel = selectors(testInfo.project.name);
  await page.addInitScript((t: string) => localStorage.setItem("you2music.jwt", t), user.token);
  await page.goto("/");
  await waitForAppReady(page, testInfo.project.name);

  await fillPrompt(page, testInfo.project.name, "history test");
  const [generateResponse] = await Promise.all([
    page.waitForResponse((response) => response.url().includes("/api/generate") && response.request().method() === "POST"),
    page.locator(sel.generateBtn).click(),
  ]);
  expect(generateResponse.ok()).toBeTruthy();
  const jobId = String((await generateResponse.json()).job_id);

  if (testInfo.project.name === "mobile") {
    await page.locator('#mobileTabBar [data-tab="history"]').click();
  }
  await expect(page.locator(`[data-job-id="${jobId}"]`)).toBeVisible({ timeout: 30_000 });
});
