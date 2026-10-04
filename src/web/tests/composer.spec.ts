import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// UI contract fixtures only: no training process or Docker execution is simulated.
async function fixture(page: Page) {
  const submissions: any[] = [];
  let fail = true;
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname.slice(4);
    if (path === "/v2/run-plans") {
      submissions.push(route.request().postDataJSON());
      if (fail) {
        fail = false;
        return route.fulfill({
          status: 503,
          json: { detail: "暂时不可用，请重试" },
        });
      }
      return route.fulfill({ json: { id: "plan-1", status: "CHECKING" } });
    }
    const responses: Record<string, unknown> = {
      "/v2/work-items/ui-test": {
        work_item: {
          id: "ui-test",
          title: "MNIST 分类训练",
          project_id: "legacy",
          environment_revision_id: "revision-1",
          ready: true,
          status: "ACTIVE",
        },
        plans: [],
        runs: [],
        jobs: [],
      },
      "/assets/framework": [],
      "/assets/recipe": [
        {
          name: "mnist-adam",
          version: "v1",
          optimizer: { name: "Adam", params: { lr: 0.001 } },
          epochs: 3,
          batch_size: 128,
          loss: "CrossEntropyLoss",
        },
      ],
      "/v2/assets": [
        {
          id: "dataset-1",
          kind: "dataset",
          name: "mnist",
          revision: "v2",
          local_status: "DOWNLOADED",
        },
        {
          id: "model-1",
          kind: "model",
          name: "mnist-cnn",
          revision: "v2",
          local_status: "DOWNLOADED",
        },
      ],
      "/resources/gpus": [],
      "/v2/environments": [
        {
          id: "env-1",
          name: "mnist-pytorch-runtime",
          revisions: [{ id: "revision-1" }],
        },
      ],
      "/v2/workspaces/ui-test/files": { files: [] },
      "/v2/jobs": [],
      "/v2/capabilities": {},
    };
    if (path in responses) return route.fulfill({ json: responses[path] });
    return route.continue();
  });
  await page.goto("/work/ui-test?parent=parent-run");
  return submissions;
}
async function select(page: Page, label: string, value: string) {
  await page.getByRole("button", { name: `更改${label}`, exact: true }).click();
  await page.getByRole("dialog").getByRole("combobox").selectOption(value);
  await page.getByRole("button", { name: "确认更改" }).click();
}

test("object editors isolate drafts and preserve resources, parent and retry identity", async ({
  page,
}) => {
  const submissions = await fixture(page);
  const check = page.getByRole("button", { name: "检查并固定运行方案" });
  await expect(check).toBeDisabled();
  await page.getByRole("button", { name: "更改数据集", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("combobox")
    .selectOption("dataset-1");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "更改数据集", exact: true }),
  ).toBeFocused();
  await expect(page.locator(".composer-summary-assets")).toContainText(
    "尚未选择数据集",
  );
  await select(page, "数据集", "dataset-1");
  await select(page, "模型", "model-1");
  await select(page, "训练配方", "mnist-adam/v1");
  expect(submissions).toHaveLength(0);
  await expect(
    page.locator(".object-description").filter({ hasText: "CrossEntropyLoss" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "更改配置" }).click();
  await page.getByLabel("CPU 线程").fill("8");
  await page.getByLabel("内存 / MiB").fill("8192");
  await page.getByRole("button", { name: "确认配置" }).click();
  await expect(page.locator(".composer-summary-environment")).toContainText(
    "8 线程 · 8 GiB 内存",
  );
  await check.click();
  await expect(
    page.getByText("暂时不可用，请重试", { exact: true }),
  ).toBeVisible();
  await expect(check).toBeEnabled();
  await check.click();
  await expect.poll(() => submissions.length).toBe(2);
  expect(submissions[0]).toMatchObject({
    work_item_id: "ui-test",
    parent_run_id: "parent-run",
    inputs: { dataset: "dataset-1", model: "model-1" },
    recipe: { name: "mnist-adam", version: "v1" },
    resources: { device: "cpu", cpu_threads: 8, memory_mb: 8192, gpu_ids: [] },
  });
  expect(submissions[0].request_id).toBe(submissions[1].request_id);
});

test("composer remains accessible without row borders across themes and widths", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await fixture(page);
  await select(page, "数据集", "dataset-1");
  await select(page, "模型", "model-1");
  await select(page, "训练配方", "mnist-adam/v1");
  for (const theme of ["vallum", "abyssus"]) {
    await page.evaluate(
      (t) => (document.documentElement.dataset.theme = t),
      theme,
    );
    for (const width of [1440, 768, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      const audit = await new AxeBuilder({ page })
        .include(".run-composer")
        .withTags(["wcag2a", "wcag2aa"])
        .analyze();
      expect(audit.violations).toEqual([]);
      if (width === 1440 && theme === "vallum")
        await page.screenshot({
          path: "/tmp/ninna-code-composer.png",
          fullPage: true,
        });
    }
  }
  expect(errors).toEqual([]);
});

test("framework tasks without train can select their supported operation and recipe", async ({ page }) => {
  await fixture(page);
  await page.route("**/api/v2/work-items/ui-test", route => route.fulfill({ json: {
    work_item: { id: "ui-test", title: "模型评估", project_id: "legacy", environment_revision_id: "revision-1", framework: { name: "framework", version: "v1" }, ready: true, status: "ACTIVE" }, plans: [], runs: [], jobs: [],
  } }));
  await page.route("**/api/assets/framework", route => route.fulfill({ json: [{ name: "framework", version: "v1", tasks: { classification: { description: "分类评估", operations: { evaluate: { required_inputs: { dataset: "dataset" }, needs_source: true } } } } }] }));
  await page.route("**/api/assets/recipe", route => route.fulfill({ json: [{ name: "evaluate", version: "v1", framework: { name: "framework", version: "v1" }, task: "classification", operation: "evaluate" }] }));
  await page.reload();
  await select(page, "任务类型", "classification");
  await expect(page.locator(".object-row").filter({ hasText: "本次运行要执行的任务" })).toContainText("评估");
  await select(page, "数据集", "dataset-1");
  await select(page, "训练配方", "evaluate/v1");
  await expect(page.getByLabel("来源运行", { exact: true })).toBeVisible();
  await page.getByLabel("来源运行", { exact: true }).fill("run-source");
  await page.getByLabel("来源产物路径", { exact: true }).fill("checkpoint/model.pt");
  await expect(page.getByRole("button", { name: "检查并固定运行方案" })).toBeEnabled();
});
