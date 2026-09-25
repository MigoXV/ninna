import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("desktop rail preserves navigation, keyboard focus and preference across routes and reload", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/runs");
  const toggle = page.getByRole("button", { name: "收起侧边栏" });
  await toggle.focus();
  await page.keyboard.press("Enter");
  const expand = page.getByRole("button", { name: "展开侧边栏" });
  await expect(expand).toBeFocused();
  await expect(expand).toHaveAttribute("aria-expanded", "false");
  const models = page
    .locator(".sidebar")
    .getByRole("link", { name: "模型", exact: true });
  await models.focus();
  await expect(models.locator(".nav-tooltip")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(models.locator(".nav-tooltip")).not.toBeVisible();
  await expect(models).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/assets\/model$/);
  await expect(models).toHaveAttribute("aria-current", "page");
  await page.reload();
  await expect(expand).toBeVisible();
  await expect(models).toHaveAttribute("aria-current", "page");
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(results.violations).toEqual([]);
  await expand.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await page.reload();
  await expect(toggle).toBeVisible();
});

test("collapsed desktop preference does not hide mobile labels or leave the desktop inert", async ({
  page,
}) => {
  await page.goto("/runs");
  await page.getByRole("button", { name: "收起侧边栏" }).click();
  await page.setViewportSize({ width: 320, height: 740 });
  await expect(page.locator(".sidebar")).not.toBeVisible();
  await page.getByRole("button", { name: "打开导航" }).click();
  await expect(page.locator(".sidebar .nav-text").first()).toBeVisible();
  await expect(
    page.getByRole("button", { name: "展开侧边栏" }),
  ).not.toBeVisible();
  await page.getByRole("button", { name: "关闭导航" }).focus();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "打开导航" })).toBeFocused();
  await page.getByRole("button", { name: "打开导航" }).click();
  await page.setViewportSize({ width: 768, height: 1000 });
  await expect(page.locator(".main-shell")).not.toHaveAttribute("inert");
  await expect(page.getByRole("button", { name: "展开侧边栏" })).toBeVisible();
  await page
    .locator(".sidebar")
    .getByRole("link", { name: "中心存储", exact: true })
    .click();
  await expect(page).toHaveURL(/\/hub$/);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
