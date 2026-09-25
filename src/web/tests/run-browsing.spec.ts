import { test, expect } from "@playwright/test";

test("paginate real runs, compare across pages and recover an empty search", async ({
  page,
}) => {
  await page.goto("/projects/legacy");
  const rows = page.locator(".runs-table tbody tr");
  await expect(rows).toHaveCount(10);
  const first = rows.first().locator('input[type="checkbox"]');
  const firstLabel = await first.getAttribute("aria-label");
  await first.check();
  await page.getByRole("button", { name: "下一页", exact: true }).click();
  await expect(
    rows.first().locator('input[type="checkbox"]'),
  ).not.toHaveAttribute("aria-label", firstLabel!);
  await rows.first().locator('input[type="checkbox"]').check();
  await expect(page.getByRole("link", { name: "比较 2 个 Run" })).toBeVisible();
  await page.getByRole("button", { name: "上一页", exact: true }).click();
  await expect(page.getByRole("checkbox", { name: firstLabel! })).toBeChecked();
  await page.getByRole("button", { name: "清空选择", exact: true }).click();
  await expect(page.getByLabel("比较选择")).toHaveCount(0);
  await page.getByRole("button", { name: "已取消", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "已取消", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(rows.first().locator(".status")).toHaveText("已取消");
  await page
    .getByRole("textbox", { name: "搜索训练运行" })
    .fill("no-such-training-run");
  await expect(page.getByText("没有匹配的训练", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "清空筛选", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "搜索训练运行" })).toHaveValue(
    "",
  );
  await expect(rows).toHaveCount(10);
  await expect(
    page.getByRole("button", { name: "上一页", exact: true }),
  ).toBeDisabled();
});
