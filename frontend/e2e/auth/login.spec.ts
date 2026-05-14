import { test, expect, createInviteCode, registerViaApi } from "../conftest";

test("login via UI works @smoke", async ({ page, request }, testInfo) => {
  const invite = await createInviteCode(request);
  const suffix = `${Date.now()}_${testInfo.workerIndex}`;
  const username = `ui_login_${suffix}`;
  const password = "pw12345678";
  await registerViaApi(request, { username, password, inviteCode: invite });

  await page.goto("/");
  await page.click("#showLoginBtn");
  await page.fill("#loginUsername", username);
  await page.fill("#loginPassword", password);
  await page.click("#loginBtn");

  await expect(page.locator("#authPage")).toBeHidden();
});
