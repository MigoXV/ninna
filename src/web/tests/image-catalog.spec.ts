import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.beforeEach(() =>
  test.skip(
    process.env.NINNA_CATALOG_INTEGRATION !== "1",
    "Requires the configured private registry catalog",
  ),
);

test("browse actual migo catalog, preserve paths and separate tasks", async ({
  page,
  request,
}) => {
  const before = await (await request.get("/api/assets/image")).json();
  await page.goto("/assets/image");
  await page
    .getByRole("link", {
      name: "registry.cn-hangzhou.aliyuncs.com",
      exact: true,
    })
    .click();
  await page.getByRole("link", { name: "migo-dl", exact: true }).click();
  const rows = page.locator("tbody tr");
  await expect(rows).toHaveCount(3);
  for (const [name, count] of [
    ["pytorch", 6],
    ["pytorch-train", 1],
    ["preludio2", 4],
  ] as const) {
    await expect(
      rows
        .filter({ has: page.getByRole("link", { name, exact: true }) })
        .locator("td")
        .nth(2),
    ).toHaveText(String(count));
  }
  await page.getByRole("link", { name: "pytorch", exact: true }).click();
  await expect(page.locator("tbody tr")).toHaveCount(6);
  await expect(
    page.getByText("2.8.0-cu128-amd64", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(page.locator("tbody tr")).toHaveCount(6);
  await page
    .getByRole("navigation", { name: "镜像目录路径" })
    .getByRole("link", { name: "migo-dl", exact: true })
    .click();
  await expect(page.locator("tbody tr")).toHaveCount(3);
  await page.goBack();
  await expect(page.locator("tbody tr")).toHaveCount(6);
  await page.getByLabel("搜索镜像").fill("2.8.0-cu128");
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  await expect(page.locator("tbody tr")).toHaveCount(2);
  await expect(page.locator("tbody")).toContainText(
    "registry.cn-hangzhou.aliyuncs.com / migo-dl / pytorch",
  );
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.getByRole("link", { name: "清除", exact: true }).click();
  await page.getByRole("link", { name: /拉取任务/ }).click();
  await expect(
    page.getByRole("heading", { name: "拉取任务", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "拉取远端镜像", exact: true }).click();
  await expect(page.getByLabel("仓库地址")).toHaveValue(
    "registry.cn-hangzhou.aliyuncs.com/migo-dl/pytorch:",
  );
  await page.getByRole("link", { name: "返回列表", exact: true }).click();
  await expect(page.locator("tbody tr")).toHaveCount(6);
  expect(await (await request.get("/api/assets/image")).json()).toEqual(before);
});

test("catalog has mobile access, scoped empty results and no global overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(
    "/assets/image?registry=registry.cn-hangzhou.aliyuncs.com&namespace=migo-dl",
  );
  await expect(
    page.getByRole("link", { name: "preludio2", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.getByLabel("搜索镜像").fill("no-match-image");
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  await expect(page.getByText("没有匹配的镜像", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "清除", exact: true }).click();
  await expect(page.locator("tbody tr")).toHaveCount(3);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});
