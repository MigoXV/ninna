import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("new workflow keeps sources, assets, and reusable environments separate", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  for (const [path, title] of [
    ["/settings/sources", "托管平台"],
    ["/library", "模型与数据"],
    ["/environments", "训练环境"],
    ["/work/new", "新建工作任务"],
  ]) {
    await page.goto(path);
    await expect(
      page.getByRole("heading", { name: title, exact: true }),
    ).toBeVisible();
    await expect(page.locator(".error-notice")).toHaveCount(0);
    const audit = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();
    expect(audit.violations).toEqual([]);
  }
  expect(errors).toEqual([]);
});

test("work context exposes real runs and survives theme and narrow viewport changes", async ({
  page,
  request,
}) => {
  const response = await request.get(
    "/api/v2/work-items?project_id=work-v2-acceptance",
  );
  test.skip(
    response.status() !== 200,
    "Requires opt-in real Docker acceptance fixture",
  );
  const work = (await response.json()).find((w: any) => w.ready);
  test.skip(!work, "Requires a prepared work item");
  await page.goto(`/work/${work.id}`);
  await expect(
    page.getByRole("heading", { name: work.title, exact: true }),
  ).toBeVisible();
  await expect(page.getByText("工作区已准备", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "设置", exact: true }).click();
  await page.getByRole("button", { name: "苍渊主题" }).click();
  await page.getByRole("link", { name: "返回工作空间" }).click();
  await expect(page.locator("body")).toHaveCSS(
    "background-color",
    "rgb(8, 10, 13)",
  );
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "abyssus");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});

test("create a work item, train in Docker, and return to the same work for retry", async ({
  page,
  request,
}) => {
  test.skip(
    process.env.NINNA_INTEGRATION !== "1",
    "Requires real Docker and seeded MNIST assets",
  );
  test.setTimeout(300000);
  const envs = await (await request.get("/api/v2/environments")).json();
  const env = envs.find(
    (e: any) => e.workspace_name === "demo-mnist-main-v3" && e.revisions.length,
  );
  expect(env).toBeTruthy();
  const assets = await (await request.get("/api/v2/assets")).json();
  const dataset = assets.find(
    (a: any) =>
      a.legacy_ref?.name === "mnist" && a.legacy_ref?.version === "smoke-v1",
  );
  const model = assets.find(
    (a: any) =>
      a.legacy_ref?.name === "mnist-config" &&
      a.legacy_ref?.version === "smoke-v1",
  );
  await page.goto("/work/new?project=work-v2-acceptance");
  await page.getByLabel("任务名称", { exact: true }).fill("浏览器真实训练");
  await page
    .getByLabel("想完成什么")
    .fill("用 MNIST 数据训练分类模型并保留工作区");
  await page
    .getByRole("combobox", { name: "训练环境", exact: true })
    .selectOption(env.revisions[0].id);
  await page.getByRole("button", { name: "创建工作任务", exact: true }).click();
  await expect(page).toHaveURL(/\/work\/work_item-/);
  const workUrl = page.url();
  await expect(page.getByText("工作区已准备", { exact: true })).toBeVisible({
    timeout: 120000,
  });
  for (const [label, value] of [
    ["任务类型", "classification"],
    ["数据集", dataset.id],
    ["模型", model.id],
    ["训练配方", "demo-mnist-classification-scratch-train/ninna-v3"],
  ]) {
    await page
      .getByRole("button", { name: `更改${label}`, exact: true })
      .click();
    await page.getByRole("dialog").getByRole("combobox").selectOption(value);
    await page.getByRole("button", { name: "确认更改" }).click();
  }
  await page.getByRole("button", { name: "检查并固定运行方案" }).click();
  await page
    .getByRole("button", { name: "开始运行", exact: true })
    .click({ timeout: 120000 });
  const runLink = page.locator('a[href^="/runs/run-"]').first();
  await expect(runLink).toBeVisible({ timeout: 120000 });
  const path = await runLink.getAttribute("href");
  await expect
    .poll(
      async () => (await (await request.get("/api" + path)).json()).status,
      { timeout: 120000 },
    )
    .toBe("SUCCESS");
  await runLink.click();
  await expect(
    page.getByRole("link", { name: "基于此 Run 新建" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "基于此 Run 新建" }).click();
  expect(page.url().split("?")[0]).toBe(workUrl);
  expect(new URL(page.url()).searchParams.get("parent")).toBe(
    path?.split("/").at(-1),
  );
});
