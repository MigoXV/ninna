import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("Hub and Aim use Ninna UI with real data, responsive layout and accessible controls", async ({
  page,
}) => {
  const requests: string[] = [];
  page.on("request", (r) => requests.push(r.url()));
  for (const path of ["/hub", "/projects/legacy/experiments"]) {
    await page.goto(path);
    await page.waitForTimeout(1500);
    await expect(page.locator("iframe")).toHaveCount(0);
    if (path === "/hub") {
      await expect(page.getByText(/已连接 ·/)).toBeVisible();
      await page.getByRole("button", { name: "连接设置", exact: true }).click();
      await expect(page.getByLabel("访问令牌", { exact: true })).toHaveValue(
        "",
      );
    } else {
      await expect(page.locator(".aim-chart")).toBeVisible();
      await page
        .getByLabel("显示指标", { exact: true })
        .selectOption("test_accuracy");
      await page.getByText("查看原始数值 · 测试准确率").click();
      await expect(page.locator(".aim-values table")).toBeVisible();
    }
    const result = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();
    expect(
      result.violations.map((v) => ({
        id: v.id,
        nodes: v.nodes.map((n) => n.target),
      })),
    ).toEqual([]);
    for (const width of [320, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        path + " " + width,
      ).toBe(true);
      await page.screenshot({
        path:
          "../../outputs/ui-evidence/" +
          width +
          path.replace("/", "-") +
          ".png",
        fullPage: true,
      });
    }
  }
  expect(
    requests.some(
      (url) => url.includes("/api/experiments/") && url.includes("/metrics"),
    ),
  ).toBe(true);
  expect(requests.some((url) => /aim.*:43800|\/aim\/ui/.test(url))).toBe(false);
});

test("publish and import a real HF model through the Hub page", async ({
  page,
}) => {
  test.setTimeout(180000);
  const config = await (await page.request.get("/api/integrations")).json();
  await page.goto("/hub");
  const publish = page.locator(".hub-operations form").first();
  const receive = page.locator(".hub-operations form").nth(1);
  await publish
    .getByRole("combobox", { name: "本地资产", exact: true })
    .selectOption({ label: "mnist-cnn / v2" });
  await publish
    .getByLabel("目标仓库", { exact: true })
    .fill(config.hub.namespace + "/mnist-cnn");
  const published = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/hub/publish") && r.request().method() === "POST",
  );
  await publish.getByRole("button", { name: "发布到 Hub" }).click();
  const job = await (await published).json();
  await expect(
    page.locator('[data-transfer-id="' + job.id + '"] .status'),
  ).toHaveText("已完成", { timeout: 60000 });
  const transfers = await (await page.request.get("/api/hub/transfers")).json();
  const receipt = transfers.find((t: any) => t.id === job.id).result;
  await receive.getByLabel("远端仓库", { exact: true }).fill(receipt.repo_id);
  await receive
    .getByLabel("Commit / branch", { exact: true })
    .fill(receipt.revision);
  await receive.getByLabel("本地名称", { exact: true }).fill("mnist-cnn");
  await receive
    .getByLabel("新版本", { exact: true })
    .fill("ui-hub-" + Date.now());
  const imported = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/hub/import") && r.request().method() === "POST",
  );
  await receive.getByRole("button", { name: "下载并注册" }).click();
  const downloaded = await (await imported).json();
  const row = page.locator('[data-transfer-id="' + downloaded.id + '"]');
  await expect(row.locator(".status")).toHaveText("已完成", { timeout: 60000 });
  await row.getByRole("link", { name: "查看资产" }).click();
  await expect(
    page.getByRole("heading", { name: "mnist-cnn", exact: true }).first(),
  ).toBeVisible();
  await expect(page.getByText("HF · Safetensors")).toBeVisible();
});
