import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("real workspace navigation, filtering, form and responsive pages", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/projects/legacy");
  await expect(
    page.getByRole("heading", { name: "legacy", exact: true }),
  ).toBeVisible();
  await page.keyboard.press("/");
  await expect(page.getByPlaceholder("搜索运行、模型或 Recipe")).toBeFocused();
  await page
    .getByRole("link", { name: "创建训练", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: "训练定义", exact: true }),
  ).toBeVisible();
  await expect(page.locator("#dataset")).not.toHaveValue("");
  await page.locator("#recipe").selectOption({ label: "mnist-sgd / v1" });
  await expect(page.getByText("5 epochs")).toBeVisible();
  await page.goto("/assets/workspace");
  await page.getByRole("button", { name: /mnist-hf.*v1/ }).click();
  await expect(page.getByText("只读预览")).toBeVisible();
  for (const width of [320, 768, 1280, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const path of [
      "/projects/legacy",
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
    "/projects/legacy",
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
  await page.goto("/projects/legacy");
  const toggle = page.getByRole("button", { name: "打开导航" });
  await toggle.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator(".sidebar")).toHaveClass(/open/);
  await page.keyboard.press("Escape");
  await expect(toggle).toBeFocused();
});

test("create a real training Run from the UI and download its checkpoint", async ({
  page,
}) => {
  test.setTimeout(240000);
  await page.goto("/runs/new?project=legacy");
  await page
    .locator("#recipe")
    .selectOption({ label: "mnist-adam / quick-v1" });
  await expect(page.locator("#recipe option:checked")).toHaveText(
    "mnist-adam / quick-v1",
  );
  const created = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/runs") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "开始训练", exact: true }).click();
  const record = await (await created).json();
  expect(record.training_spec.recipe.version).toBe("quick-v1");
  expect(record.training_spec.model.version).toBe("v2");
  await expect(page).toHaveURL(/\/runs\/run-/);
  await expect(page.locator(".run-context .status")).toHaveText("已完成", {
    timeout: 180000,
  });
  await expect(
    page.getByText("Training complete. Checkpoint and metrics saved.", {
      exact: false,
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: /^产物/ }).click();
  const row = page
    .locator(".artifact-row")
    .filter({ hasText: "checkpoint.pt" });
  const downloadPromise = page.waitForEvent("download");
  await row.getByRole("link", { name: "下载" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("checkpoint.pt");
  await expect(
    page.getByRole("heading", { name: "让结果成为下一次训练的起点" }),
  ).toBeVisible();
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
    await expect(page.locator("#model")).not.toHaveValue("");
    await expect(page.locator(".failure-banner")).toHaveCount(0);
  }
});
