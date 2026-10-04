import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("real workspace navigation, filtering, form and responsive pages", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/projects/work-v2-acceptance");
  await expect(
    page.getByRole("heading", { name: "work-v2-acceptance", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "新建工作任务", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "新建工作任务", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "项目", exact: true }),
  ).toHaveValue("work-v2-acceptance");
  for (const width of [320, 768, 1280, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const path of [
      "/projects/work-v2-acceptance",
      "/runs/new",
      "/projects",
      "/assets/dataset",
    ]) {
      await page.goto(path);
      await page.waitForTimeout(300);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
        `${path} at ${width}`,
      ).toBe(true);
      await page.screenshot({
        path: `../../outputs/ui-evidence/${width}-${path.replaceAll("/", "-")}.png`,
        fullPage: true,
      });
    }
  }
  expect(errors).toEqual([]);
});

test("key routes have no serious accessibility violations", async ({
  page,
}) => {
  for (const path of [
    "/projects/work-v2-acceptance",
    "/runs/new",
    "/projects",
    "/assets/dataset",
  ]) {
    await page.goto(path);
    await page.waitForTimeout(500);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();
    expect(
      results.violations,
      JSON.stringify(
        results.violations.map((v) => ({
          id: v.id,
          nodes: v.nodes.map((n) => ({
            target: n.target,
            summary: n.failureSummary,
          })),
        })),
        null,
        2,
      ),
    ).toEqual([]);
  }
});

test("mobile keyboard navigation opens and closes with restored focus", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/projects/work-v2-acceptance");
  const toggle = page.getByRole("button", { name: "打开导航" });
  await toggle.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator(".sidebar")).toHaveClass(/open/);
  await page.keyboard.press("Escape");
  await expect(toggle).toBeFocused();
});

test("run detail, failure recovery and reduced motion remain accessible", async ({
  page,
}) => {
  const records = await (await page.request.get("/api/runs")).json();
  const success = records.find((r: any) => r.status === "SUCCESS");
  const failure = records.find((r: any) => r.status === "FAILED");
  expect(success).toBeTruthy();
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/runs/" + success.id);
  await page.waitForTimeout(500);
  for (const width of [320, 768, 1280]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `../../outputs/ui-evidence/${width}-run-detail.png`,
      fullPage: true,
    });
  }
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(
    results.violations.map((v) => ({
      id: v.id,
      targets: v.nodes.map((n) => n.target),
    })),
  ).toEqual([]);
  // A 640 CSS-pixel viewport is the layout viewport of a 1280px window at 200% zoom.
  await page.setViewportSize({ width: 640, height: 500 });
  await page.getByRole("button", { name: "执行与诊断" }).click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  if (failure) {
    await page.goto("/runs/" + failure.id);
    await expect(page.locator(".failure-banner")).toBeVisible();
    await page.getByRole("link", { name: "基于此 Run 新建" }).click();
    await expect(page).toHaveURL(/\/work\//);
    await expect(
      page.getByRole("heading", { name: "用什么数据，训练什么模型，怎么训练" }),
    ).toBeVisible();
    await expect(page.locator(".failure-banner")).toHaveCount(0);
  }
});
