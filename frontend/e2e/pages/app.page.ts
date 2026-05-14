import { expect, type Page, type TestInfo } from "@playwright/test";
import { selectors, setToken, type TestUser } from "../conftest";

export class AppPage {
  constructor(
    private readonly page: Page,
    private readonly testInfo: TestInfo
  ) {}

  private sel() {
    return selectors(this.testInfo.project.name);
  }

  async gotoLoggedOut() {
    await this.page.goto("/");
    await expect(this.page.locator(this.sel().authPage)).toBeVisible();
  }

  async gotoWithToken(user: TestUser) {
    await setToken(this.page, user.token);
    await this.page.goto("/");
    // Both desktop + mobile should hide auth page.
    await expect(this.page.locator(this.sel().authPage)).toBeHidden();
  }

  async fillPrompt(text: string) {
    await this.page.locator(this.sel().prompt).fill(text);
  }

  async clickGenerate() {
    await this.page.locator(this.sel().generateBtn).click();
  }

  async waitForJobId() {
    const jobIdEl = this.page.locator(this.sel().jobId);
    await expect(jobIdEl).toBeVisible();
    await expect(jobIdEl).not.toHaveText("-");
    return (await jobIdEl.textContent())?.trim() || "";
  }

  async waitForJobSucceeded(jobId: string) {
    const sel = this.sel();
    if (sel.status === "#statusMobile") {
      await expect(this.page.locator(sel.status)).toContainText("已完成", { timeout: 30_000 });
      return;
    }
    const card = this.page.locator(`[data-job-id="${jobId}"]`);
    await expect(card).toBeVisible({ timeout: 30_000 });
    await expect(card.locator(".job-status")).toContainText("已完成", { timeout: 30_000 });
  }

  async expectToastContains(text: string) {
    const toast = this.page.locator(this.sel().toast).first();
    await expect(toast).toBeVisible();
    await expect(toast).toContainText(text);
  }
}
