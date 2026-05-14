import { test, expect, selectors, isMobileProject } from "../conftest";

test("published job appears in community list @smoke", async ({ page, user }, testInfo) => {
  const sel = selectors(testInfo.project.name);
  await page.addInitScript((t: string) => localStorage.setItem("you2music.jwt", t), user.token);
  await page.goto("/");
  await expect(page.locator(sel.authPage)).toBeHidden();

  // Generate one job.
  await page.locator(sel.prompt).fill("community publish");
  await page.locator(sel.generateBtn).click();
  await expect(page.locator(sel.jobId)).not.toHaveText("-");
  const jobId = (await page.locator(sel.jobId).textContent())?.trim() || "";

  // Wait until succeeded so Publish button is present.
  await expect(page.locator(`[data-job-id="${jobId}"] .job-status`)).toContainText("已完成", { timeout: 30_000 });

  // Publish from history list (desktop). Mobile list uses the same DOM list (#list),
  // so this selector works for both projects.
  if (isMobileProject(testInfo.project.name)) {
    await page.locator('#mobileTabBar [data-tab="history"]').click();
  }
  await page.locator(`[data-job-id="${jobId}"] button:has-text("发布")`).click();

  // Switch to Discover (desktop) or Discover tab (mobile) and refresh.
  if (isMobileProject(testInfo.project.name)) {
    await page.locator('#mobileTabBar [data-tab="discover"]').click();
    await page.locator("#refreshCommunityBtnMobile").click();
    await expect(page.locator("#communityList")).toContainText(jobId, { timeout: 30_000 });
  } else {
    await page.locator("#navDiscover").click();
    await page.locator("#refreshCommunityBtn").click();
    await expect(page.locator("#communityList2")).toContainText(jobId, { timeout: 30_000 });
  }
});
