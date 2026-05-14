import { test } from "../conftest";
import { AppPage } from "../pages/app.page";

test("generate produces a playable job @smoke", async ({ page, user }, testInfo) => {
  const app = new AppPage(page, testInfo);
  await app.gotoWithToken(user);

  await app.fillPrompt("e2e generate");
  await app.clickGenerate();

  const jobId = await app.waitForJobId();
  await app.waitForJobSucceeded(jobId);
});
