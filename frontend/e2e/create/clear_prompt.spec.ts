import { test, expect, selectors } from "../conftest";

test("clear prompt button resets input", async ({ page, user }, testInfo) => {
  const sel = selectors(testInfo.project.name);
  await page.addInitScript((t: string) => localStorage.setItem("you2music.jwt", t), user.token);
  await page.goto("/");
  await expect(page.locator(sel.authPage)).toBeHidden();

  await page.locator(sel.prompt).fill("will be cleared");
  const clearBtn = sel.prompt === "#promptMobile" ? "#clearPromptBtnMobile" : "#clearPromptBtn";
  await page.locator(clearBtn).click();
  await expect(page.locator(sel.prompt)).toHaveValue("");
});
