import { test, expect, selectors, isMobileProject, waitForAppReady } from "../conftest";

test("published job appears in community list @smoke", async ({ page, request, user }, testInfo) => {
  test.setTimeout(60_000);

  const sel = selectors(testInfo.project.name);
  const prompt = `community publish ${Date.now()} ${testInfo.workerIndex}`;
  const authHeaders = { Authorization: `Bearer ${user.token}` };

  const create = await request.post("/api/generate", {
    headers: authHeaders,
    data: { prompt, duration_sec: 5, vocals: true },
  });
  expect(create.ok()).toBeTruthy();
  const jobId = String((await create.json()).job_id);

  await expect
    .poll(
      async () => {
        const job = await request.get(`/api/jobs/${jobId}`, { headers: authHeaders });
        if (!job.ok()) return `HTTP ${job.status()}`;
        return String((await job.json()).status);
      },
      { timeout: 45_000 }
    )
    .toBe("succeeded");

  const publish = await request.post(`/api/jobs/${jobId}/publish`, {
    headers: authHeaders,
    data: { share_permission: "listen_only" },
  });
  expect(publish.ok()).toBeTruthy();

  await page.addInitScript((t: string) => localStorage.setItem("you2music.jwt", t), user.token);
  await page.goto("/");
  await waitForAppReady(page, testInfo.project.name);

  // Switch to Discover (desktop) or Discover tab (mobile) and refresh.
  if (isMobileProject(testInfo.project.name)) {
    await page.locator('#mobileTabBar [data-tab="discover"]').click();
    await page.locator("#refreshCommunityBtnMobile").click();
    await expect(page.locator("#communityList")).toContainText(prompt, { timeout: 30_000 });
  } else {
    await page.locator("#navDiscover").click();
    await page.locator("#refreshCommunityBtn").click();
    await expect(page.locator("#communityList2")).toContainText(prompt, { timeout: 30_000 });
  }
});
