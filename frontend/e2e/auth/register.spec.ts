import { test, expect, createInviteCode } from "../conftest";
import { AppPage } from "../pages/app.page";

test("register succeeds and enters app @smoke", async ({ page, request }, testInfo) => {
  const app = new AppPage(page, testInfo);
  await app.gotoLoggedOut();

  const invite = await createInviteCode(request);
  const suffix = `${Date.now()}_${testInfo.workerIndex}`;
  const username = `ui_reg_${suffix}`;
  const password = "pw12345678";

  await page.click("#showRegisterBtn");
  await page.fill("#registerUsername", username);
  await page.fill("#registerPassword", password);
  await page.fill("#registerInvite", invite);
  await page.click("#registerBtn");

  await expect(page.locator("#authPage")).toBeHidden();
});
