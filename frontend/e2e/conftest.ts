import { expect, type APIRequestContext, type Page, test as base } from "@playwright/test";

export type TestUser = {
  username: string;
  password: string;
  token: string;
};

export function isMobileProject(projectName: string): boolean {
  return projectName.toLowerCase().includes("mobile");
}

export function selectors(projectName: string) {
  const mobile = isMobileProject(projectName);
  return {
    prompt: mobile ? "#promptMobile" : "#prompt",
    generateBtn: mobile ? "#generateBtnMobile" : "#generateBtn",
    jobId: mobile ? "#jobIdMobile" : "#jobId",
    status: mobile ? "#statusMobile" : "#status",
    historyList: mobile ? "#list" : "#list",
    toast: "#toastContainer .toast",
    error: mobile ? "#errorMobile" : "#error",
    authPage: "#authPage",
    showRegisterBtn: "#showRegisterBtn",
    showLoginBtn: "#showLoginBtn",
    loginUsername: "#loginUsername",
    loginPassword: "#loginPassword",
    registerUsername: "#registerUsername",
    registerPassword: "#registerPassword",
    registerInvite: "#registerInvite",
    pcLayout: "#pcLayout",
    mobilePanels: "#mobilePanels",
    mobileTabBar: "#mobileTabBar",
  };
}

export async function waitForAppReady(page: Page, projectName: string) {
  const sel = selectors(projectName);
  await expect(page.locator(sel.authPage)).toBeHidden();
  if (isMobileProject(projectName)) {
    await expect(page.locator(sel.mobilePanels)).toBeVisible();
  } else {
    await expect(page.locator(sel.pcLayout)).toBeVisible();
  }
  await expect(page.locator(sel.prompt)).toBeVisible();
}

export async function fillPrompt(page: Page, projectName: string, value: string) {
  const prompt = page.locator(selectors(projectName).prompt);
  await expect(prompt).toBeVisible();
  await prompt.evaluate((element, text) => {
    const input = element as HTMLTextAreaElement | HTMLInputElement;
    input.value = String(text);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }, value);
  await expect(prompt).toHaveValue(value);
}

async function adminLogin(request: APIRequestContext): Promise<string> {
  const r = await request.post("/api/auth/login", {
    data: { username: "admin", password: "adminpw" },
  });
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  expect(typeof j.token).toBe("string");
  return String(j.token);
}

export async function createInviteCode(request: APIRequestContext): Promise<string> {
  const token = await adminLogin(request);
  const r = await request.post("/api/admin/invite-codes", {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  return String(j.invite_code.code);
}

export async function registerViaApi(
  request: APIRequestContext,
  user: { username: string; password: string; inviteCode: string }
): Promise<TestUser> {
  const r = await request.post("/api/auth/register", {
    data: {
      username: user.username,
      password: user.password,
      invite_code: user.inviteCode,
    },
  });
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  return {
    username: user.username,
    password: user.password,
    token: String(j.token),
  };
}

export async function loginViaApi(
  request: APIRequestContext,
  user: { username: string; password: string }
): Promise<TestUser> {
  const r = await request.post("/api/auth/login", { data: user });
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  return { username: user.username, password: user.password, token: String(j.token) };
}

export async function setToken(page: Page, token: string) {
  await page.addInitScript((t: string) => {
    localStorage.setItem("you2music.jwt", t);
  }, token);
}

export const test = base.extend<{ user: TestUser }>({
  user: async ({ request }, use, testInfo) => {
    const inviteCode = await createInviteCode(request);
    const password = "pw12345678";
    const suffix = `${Date.now()}_${testInfo.workerIndex}_${Math.random().toString(16).slice(2, 8)}`;
    const username = `e2e_${suffix}`;
    const user = await registerViaApi(request, { username, password, inviteCode });
    await use(user);
  },
});

export { expect };
