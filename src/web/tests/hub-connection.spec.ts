import { test, expect } from "@playwright/test";

// Only transport states are simulated; no training evidence is mocked.
const sources = [
  {
    id: "source-internal",
    name: "公司内网",
    endpoint: "https://internal.example",
    protocol: "hf",
    enabled: true,
    token_env: null,
    version: 1,
  },
  {
    id: "source-public",
    name: "公开平台",
    endpoint: "https://huggingface.co",
    protocol: "hf",
    enabled: true,
    token_env: null,
    version: 1,
  },
];
test("a source failure does not replace another source's connection state", async ({
  page,
}) => {
  await page.route("**/api/v2/sources", (route) =>
    route.fulfill({ json: sources }),
  );
  await page.route("**/api/v2/sources/source-internal/status", (route) =>
    route.fulfill({ json: { status: "UNAVAILABLE" } }),
  );
  await page.route("**/api/v2/sources/source-public/status", (route) =>
    route.fulfill({ json: { status: "CONNECTED" } }),
  );
  await page.goto("/settings/sources");
  const internal = page.locator(".work-row").filter({ hasText: "公司内网" });
  const publicSource = page
    .locator(".work-row")
    .filter({ hasText: "公开平台" });
  await internal.getByRole("button", { name: "检查连接" }).click();
  await expect(internal).toContainText("连接失败");
  await publicSource.getByRole("button", { name: "检查连接" }).click();
  await expect(publicSource).toContainText("连接正常");
  await expect(internal).toContainText("连接失败");
});

test("source form preserves values and shows errors on HTTP LAN installations", async ({
  page,
}) => {
  await page.addInitScript(() =>
    Object.defineProperty(crypto, "randomUUID", { value: undefined }),
  );
  await page.route("**/api/v2/sources", async (route) => {
    if (route.request().method() === "POST") {
      expect(route.request().postDataJSON().request_id).toMatch(
        /^[a-f0-9]{32}$/,
      );
      await route.fulfill({
        status: 409,
        json: { detail: { message: "平台配置冲突" } },
      });
    } else await route.fulfill({ json: [] });
  });
  await page.goto("/settings/sources");
  await page.getByLabel("名称", { exact: true }).fill("内网");
  await page.getByLabel("平台地址").fill("http://internal.example");
  await page.getByRole("button", { name: "添加平台", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("平台配置冲突");
  await expect(page.getByLabel("平台地址")).toHaveValue(
    "http://internal.example",
  );
});

test("the old Hub route leads to multiple hosting platforms", async ({
  page,
}) => {
  await page.goto("/hub");
  await expect(page).toHaveURL(/\/settings\/sources$/);
  await expect(
    page.getByRole("heading", { name: "托管平台", exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("访问令牌", { exact: true })).toHaveCount(0);
});

test("retry after a lost mutation response keeps the same request identity", async ({
  page,
}) => {
  const identities: string[] = [];
  await page.route("**/api/v2/sources", async (route) => {
    if (route.request().method() !== "POST") return route.fulfill({ json: [] });
    identities.push(route.request().postDataJSON().request_id);
    if (identities.length === 1) return route.abort("failed");
    await route.fulfill({ json: { id: "source-created" } });
  });
  await page.goto("/settings/sources");
  await page.getByLabel("名称", { exact: true }).fill("重试验证");
  await page.getByLabel("平台地址").fill("https://hosting.example");
  await page.getByRole("button", { name: "添加平台", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await page.getByRole("button", { name: "添加平台", exact: true }).click();
  await expect(page.getByLabel("名称", { exact: true })).toHaveValue("");
  expect(identities).toHaveLength(2);
  expect(identities[0]).toBe(identities[1]);
});
