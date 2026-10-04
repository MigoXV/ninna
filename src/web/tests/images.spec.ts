import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("image asset navigation, registration and detail", async ({
  page,
  request,
}) => {
  test.setTimeout(180000);
  await page.goto("/assets/image");
  await expect(
    page.getByRole("heading", { name: "镜像资产", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "注册本地镜像", exact: true }).click();
  await expect(page.getByLabel("本地镜像")).toBeEnabled({ timeout: 30000 });
  const images = await (await request.get("/api/images/local")).json();
  const image = images.find((i: any) =>
    i.tags.includes("ninna/pytorch-runtime:v3"),
  );
  const name = `ui-image-${Date.now()}`;
  await page.getByLabel("本地镜像").selectOption(image.image_id);
  await page.getByLabel("资产名称", { exact: true }).fill(name);
  await page.getByRole("button", { name: "注册镜像资产", exact: true }).click();
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
  await expect(
    page.getByRole("status").filter({ hasText: "本地可用" }),
  ).toBeVisible();
  await expect(
    page.getByText(image.image_id, { exact: true }).first(),
  ).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
  await page.getByRole("button", { name: "创建运行环境", exact: true }).click();
  await expect(page.getByLabel("Runtime 名称")).toBeVisible();
  await page.getByLabel("Runtime 名称").fill(name + "-runtime");
  await page.getByRole("button", { name: "验证并创建", exact: true }).click();
  await expect(
    page.getByRole("link", { name: name + "-runtime / v1" }),
  ).toBeVisible({ timeout: 120000 });
});

test("image pages fit mobile and expose remote pull form", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/assets/image?action=pull");
  await expect(page.getByLabel("仓库地址")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "开始拉取", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});
