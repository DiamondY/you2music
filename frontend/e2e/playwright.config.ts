import { defineConfig, devices } from "@playwright/test";
import path from "path";

const repoRoot = path.resolve(__dirname, "../..");
const port = Number(process.env.YOU2MUSIC_E2E_PORT || "8000");
const baseURL = `http://127.0.0.1:${port}`;
const reuseExistingServer = process.env.YOU2MUSIC_E2E_REUSE_SERVER === "1" && !process.env.CI;
const workers = Number(process.env.YOU2MUSIC_E2E_WORKERS || "1");
const externalServer = process.env.YOU2MUSIC_E2E_EXTERNAL_SERVER === "1";

// Fresh data dir per test run to avoid stale DB/jobs leaking across runs.
const dataDir = path.resolve(repoRoot, ".tmp", `you2music_e2e_${Date.now()}`);

export default defineConfig({
  testDir: ".",
  testMatch: ["**/*.spec.ts"],
  timeout: 30_000,
  expect: { timeout: 5_000 },
  retries: process.env.CI ? 1 : 0,
  workers,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL,
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    trace: "on-first-retry",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["iPhone 13"] } },
  ],
  webServer: externalServer ? undefined : {
    command: "python backend/main.py",
    cwd: repoRoot,
    url: `${baseURL}/`,
    reuseExistingServer,
    timeout: 30_000,
    env: {
      AI_MUSIC_DATA_DIR: dataDir,
      AI_MUSIC_JWT_SECRET: "e2e-test-secret",
      AI_MUSIC_ADMIN_USERNAME: "admin",
      AI_MUSIC_ADMIN_PASSWORD: "adminpw",
      AI_MUSIC_DEFAULT_DAILY_QUOTA: "999",
      AI_MUSIC_HOST: "127.0.0.1",
      AI_MUSIC_PORT: String(port),
      ACESTEP_API_KEY: "fake-key",
      ACESTEP_BASE_URL: "http://localhost:0",
      AI_MUSIC_TEST_MODE: "1"
    },
  },
});
