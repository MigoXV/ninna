import { test, expect } from "@playwright/test";

// These are UI transport states only; training and Run data are never mocked.
test("Hub loading is neutral, real failure is actionable, retry recovers", async ({
  page,
}) => {
  let respond!: () => void;
  const gate = new Promise<void>((resolve) => {
    respond = resolve;
  });
  let state = "waiting";
  await page.route("**/api/hub/status", async (route) => {
    if (state === "waiting") await gate;
    await route.fulfill({
      json:
        state === "failed"
          ? {
              status: "UNAVAILABLE",
              error: "连接失败，请检查地址、凭据和服务状态。",
            }
          : { status: "CONNECTED", account: "ui-state-test" },
    });
  });
  await page.goto("/hub");
  await expect(page.locator(".connection-state")).toContainText("正在检查连接");
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.getByText("按需连接中心存储", { exact: true })).toHaveCount(
    0,
  );
  state = "failed";
  respond();
  await expect(page.getByRole("alert")).toContainText("连接失败");
  await expect(page.getByRole("button", { name: "发布到 Hub" })).toBeDisabled();
  state = "connected";
  await page
    .getByRole("alert")
    .getByRole("button", { name: "重试", exact: true })
    .click();
  await expect(page.locator(".connection-state")).toContainText("已连接");
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("disabled Hub preserves settings save errors beside the form", async ({
  page,
}) => {
  const settings = await (await page.request.get("/api/integrations")).json();
  await page.route("**/api/integrations", (route) =>
    route.request().method() === "POST"
      ? route.fulfill({ status: 503, json: { detail: "保存设置失败" } })
      : route.fulfill({
          json: { ...settings, hub: { ...settings.hub, enabled: false } },
        }),
  );
  await page.route("**/api/hub/status", (route) =>
    route.fulfill({ json: { status: "DISABLED" } }),
  );
  await page.goto("/hub");
  await page.getByRole("button", { name: "连接设置", exact: true }).click();
  await page.getByRole("button", { name: "保存并检查连接" }).click();
  await expect(
    page.locator(".integration-settings").getByRole("alert"),
  ).toHaveText(/保存设置失败/);
});

test("Hub settings pending never flashes disabled; disabled is not an error", async ({
  page,
}) => {
  const settings = await (await page.request.get("/api/integrations")).json();
  let respond!: () => void;
  const gate = new Promise<void>((resolve) => {
    respond = resolve;
  });
  await page.route("**/api/integrations", async (route) => {
    await gate;
    await route.fulfill({
      json: { ...settings, hub: { ...settings.hub, enabled: false } },
    });
  });
  await page.route("**/api/hub/status", (route) =>
    route.fulfill({ json: { status: "DISABLED" } }),
  );
  await page.goto("/hub");
  await expect(page.locator(".connection-state")).toContainText("正在检查连接");
  await expect(page.getByText("按需连接中心存储", { exact: true })).toHaveCount(
    0,
  );
  respond();
  await expect(page.locator(".connection-state")).toContainText("未启用");
  await expect(
    page.getByText("按需连接中心存储", { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("Hub refresh keeps prior state while checking and exposes refresh/repository errors", async ({
  page,
}) => {
  let refreshing = false;
  let respond!: () => void;
  const gate = new Promise<void>((resolve) => {
    respond = resolve;
  });
  await page.route("**/api/hub/status", async (route) => {
    if (refreshing) {
      await gate;
      await route.fulfill({ status: 503, json: { detail: "状态服务不可用" } });
    } else
      await route.fulfill({
        json: { status: "CONNECTED", account: "ui-state-test" },
      });
  });
  await page.route("**/api/hub/repositories?*", (route) =>
    route.fulfill({ status: 503, json: { detail: "仓库读取失败" } }),
  );
  await page.goto("/hub");
  await expect(page.locator(".connection-state")).toContainText("已连接");
  await expect(page.locator(".hub-repositories")).toContainText("仓库读取失败");
  await expect(page.getByText("没有匹配的仓库", { exact: true })).toHaveCount(
    0,
  );
  refreshing = true;
  await page.getByRole("button", { name: "刷新", exact: true }).click();
  await expect(page.locator(".connection-state")).toContainText(
    "已连接 · ui-state-test · 检查中",
  );
  respond();
  await expect(page.locator(".connection-state")).toHaveText("暂不可用");
  await expect(
    page.getByRole("alert").filter({ hasText: "状态服务不可用" }),
  ).toBeVisible();
});
