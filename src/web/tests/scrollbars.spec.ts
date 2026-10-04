import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// These are UI contract fixtures; they do not execute or simulate training.
test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", (route) => route.fulfill({ json: [] }));
});

for (const theme of ["vallum", "abyssus"]) {
  test(`${theme}: long asset lists scroll independently and remain keyboard accessible`, async ({
    page,
  }) => {
    await page.addInitScript(
      (t) => localStorage.setItem("ninna.theme", t),
      theme,
    );
    await page.route("**/api/v2/assets", (route) =>
      route.fulfill({
        json: Array.from({ length: 30 }, (_, i) => ({
          id: `asset-${i}`,
          name: `model-${i}`,
          kind: "model",
          revision: "v1",
          local_status: "DOWNLOADED",
          source: {},
        })),
      }),
    );
    await page.goto("/library");
    const list = page.getByRole("region", { name: "本地资产列表" });
    for (const width of [1440, 768, 320]) {
      await page.setViewportSize({ width, height: 900 });
      await expect(list.locator(".work-row")).toHaveCount(30);
      const style = await list.evaluate((el) => ({
        overflow: getComputedStyle(el).overflowY,
        color: getComputedStyle(el, "::-webkit-scrollbar-thumb")
          .backgroundColor,
        gutter: getComputedStyle(el).scrollbarGutter,
        content: el.scrollHeight,
        viewport: el.clientHeight,
      }));
      expect(style.overflow).toBe("scroll");
      expect(style.color).not.toBe("rgba(0, 0, 0, 0)");
      expect(style.gutter).toBe("stable");
      expect(style.content).toBeGreaterThan(style.viewport);
      await list.evaluate((el) => {
        el.scrollTop = 0;
      });
      await list.focus();
      const headingY = (await page
        .getByRole("heading", { name: "模型与数据", exact: true })
        .boundingBox())!.y;
      await page.keyboard.press("End");
      await expect
        .poll(() => list.evaluate((el) => el.scrollTop))
        .toBeGreaterThan(100);
      expect(
        (await page
          .getByRole("heading", { name: "模型与数据", exact: true })
          .boundingBox())!.y,
      ).toBe(headingY);
      await expect(
        list.getByText("model-29", { exact: true }),
      ).toBeInViewport();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    }
    const audit = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();
    expect(audit.violations).toEqual([]);
    await page.setViewportSize({ width: 1440, height: 900 });
    await list.evaluate((el) => {
      el.scrollTop = 0;
    });
    await page
      .getByRole("heading", { name: "模型与数据", exact: true })
      .click();
    await page.screenshot({ path: `/tmp/ninna-scroll-${theme}.png` });
  });
}

test("artifact scrolling keeps every download reachable without moving the outer detail", async ({
  page,
  request,
}) => {
  const ref = { name: "mnist", version: "v1" };
  const run = {
    id: "scroll-test",
    project_id: "legacy",
    status: "SUCCESS",
    created_at: "2026-10-04T00:00:00Z",
    started_at: null,
    finished_at: null,
    training_spec: { dataset: ref, model: ref, recipe: ref },
    execution_spec: {
      runtime: ref,
      workspace: { name: "workspace", snapshot: "v1" },
      resources: {
        device: "cpu",
        cpu_threads: 4,
        memory_mb: 4096,
        gpu_count: 0,
      },
    },
    metrics: {},
    assets: {
      recipe: { epochs: 3, optimizer: { name: "Adam", params: { lr: 0.001 } } },
    },
    events: [],
    metadata: {},
  };
  await page.route(`**/api/runs/${run.id}`, (route) =>
    route.fulfill({
      json: {
        ...run,
        artifacts: Array.from({ length: 24 }, (_, i) => ({
          name: `result-${i}.json`,
          size: 1024,
          sha256: "1234567890abcdef",
        })),
      },
    }),
  );
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/runs/${run.id}`);
  await page.getByRole("button", { name: /^产物/ }).click();
  const outer = page.getByRole("region", { name: "运行详情内容" });
  const list = page.getByRole("region", { name: "训练产物", exact: true });
  await expect(list.locator(".artifact-row")).toHaveCount(25);
  await list.focus();
  const outerTop = await outer.evaluate((el) => el.scrollTop);
  await page.keyboard.press("End");
  await expect(
    list.locator(".artifact-row").last().getByRole("link", { name: "下载" }),
  ).toBeInViewport();
  expect(await outer.evaluate((el) => el.scrollTop)).toBe(outerTop);
  await expect(
    list.locator(".artifact-row").last().getByRole("link", { name: "下载" }),
  ).toHaveAttribute("href", `/api/runs/${run.id}/artifacts/run.json`);
});
