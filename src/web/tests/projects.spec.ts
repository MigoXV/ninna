import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("projects organize runs and keep training metrics inside run detail", async ({
  page,
  request,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "项目", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("最佳测试准确率")).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "系统验收", exact: true }),
  ).toHaveCount(0);
  const name = `ui-project-${Date.now()}`;
  await page.getByRole("button", { name: "新建项目", exact: true }).click();
  await page.getByLabel("项目名称").fill(name);
  await page.getByLabel("说明 可选").fill("Project 浏览器回归");
  await page.getByRole("button", { name: "创建项目", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/projects/${name}$`));
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
  await expect(page.getByText("最佳测试准确率")).toHaveCount(0);
  await expect(page.getByRole("columnheader", { name: "准确率" })).toHaveCount(
    0,
  );
  await page
    .getByRole("link", { name: "创建训练", exact: true })
    .first()
    .click();
  await expect(page.getByLabel("所属项目")).toHaveValue(name);
  await page.goto(`/projects/${name}/experiments`);
  await expect(
    page.getByRole("heading", { name: "等待第一个实验" }),
  ).toBeVisible();
  const members = await request.get(`/api/projects/${name}/runs`);
  expect(await members.json()).toEqual([]);
  await page.goto("/projects/legacy");
  await expect(page.locator(".run-title").first()).toBeVisible();
  await page.locator(".run-title").first().click();
  await expect(page.locator(".back-link")).toHaveAttribute(
    "href",
    "/projects/legacy",
  );
  await expect(
    page.getByText("测试准确率", { exact: true }).first(),
  ).toBeVisible();
  await page.getByRole("link", { name: "基于此 Run 新建" }).click();
  await expect(page.getByLabel("所属项目")).toHaveValue("legacy");
  await expect(page.getByLabel("所属项目")).toBeDisabled();
});

test("project navigation and forms remain accessible at desktop and mobile widths", async ({
  page,
}) => {
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/projects");
    await expect(
      page.getByRole("heading", { name: "项目", exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "新建项目", exact: true }).click();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    const result = await new AxeBuilder({ page }).analyze();
    expect(result.violations).toEqual([]);
  }
});
