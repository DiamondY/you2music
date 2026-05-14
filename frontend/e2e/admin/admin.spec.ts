import { test, expect } from "../conftest";

test("admin page loads for admin user @smoke", async ({ page, request }) => {
  // Login as admin via API and inject token.
  const r = await request.post("/api/auth/login", { data: { username: "admin", password: "adminpw" } });
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  await page.addInitScript((t: string) => localStorage.setItem("you2music.jwt", t), String(j.token));
  await page.goto("/admin");
  await expect(page.locator("#adminApp")).toBeVisible();
});
