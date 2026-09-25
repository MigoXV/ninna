import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  timeout: 45000,
  use: {
    baseURL: process.env.NINNA_WEB_URL || "http://127.0.0.1:8000",
    headless: true,
    launchOptions: { args: ["--no-sandbox"] },
  },
  workers: 1,
  reporter: "list",
});
