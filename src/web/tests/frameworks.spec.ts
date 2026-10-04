import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("registered frameworks, task-specific metrics and task forms are accessible", async ({
  page,
  request,
}) => {
  test.skip(
    process.env.NINNA_INTEGRATION !== "1",
    "Requires the isolated real framework registry",
  );
  const response = await request.get(
    "/api/runs?project_id=framework-integration",
  );
  const run = (await response.json()).find(
    (r: any) =>
      r.task_spec?.framework.name === "demo-mnist" &&
      r.task_spec.operation === "train" &&
      r.status === "SUCCESS",
  );
  expect(run).toBeTruthy();
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/assets/framework");
    await expect(
      page.getByRole("heading", { name: "训练框架", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("demo-mnist / ninna-v1", { exact: true }),
    ).toBeVisible();
    await page.goto(`/runs/${run.id}`);
    await expect(
      page.getByText("train_loss_step", { exact: true }).first(),
    ).toBeVisible();
    await expect(
      page.getByText("完整测试集 · 10,000 样本", { exact: true }),
    ).toHaveCount(0);
    await page.getByRole("link", { name: "基于此 Run 新建" }).click();
    await expect(page).toHaveURL(/work\/work_item-/);
    await page.getByLabel("任务类型").selectOption("classification");
    await page.getByRole("combobox", { name: "操作", exact: true }).selectOption("prepare");
    await expect(page.getByLabel("模型 · model")).toHaveCount(0);
    await expect(page.getByLabel("数据集 · dataset")).toBeVisible();
    const accessibility = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(accessibility.violations).toEqual([]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
  }
});
