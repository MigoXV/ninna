import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("theme follows the locked palette, survives reload, and synchronizes desktop/mobile controls", async ({
  page,
}) => {
  await page.goto("/projects/legacy");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "vallum");
  await expect(page.locator("body")).toHaveCSS(
    "background-color",
    "rgb(248, 247, 242)",
  );
  await page.getByRole("button", { name: "苍渊主题" }).click();
  await expect(page.locator("body")).toHaveCSS(
    "background-color",
    "rgb(8, 10, 13)",
  );
  await expect(page.locator(".button.primary").first()).toHaveCSS(
    "color",
    "rgb(8, 10, 13)",
  );
  await expect(page.locator(".button.primary").first()).toHaveCSS(
    "background-color",
    "rgb(159, 196, 226)",
  );
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "abyssus");
  await page.setViewportSize({ width: 375, height: 800 });
  await expect(page.getByRole("button", { name: "苍渊主题" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.getByRole("button", { name: "白垣主题" }).focus();
  await page.keyboard.press("Enter");
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.getByRole("button", { name: "白垣主题" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.locator('meta[name="theme-color"]')).toHaveAttribute(
    "content",
    "#F8F7F2",
  );
});

test("theme switches retain draft fields, selected runs and scroll positions", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/runs/new?project=legacy");
  await expect(page.locator("#recipe option")).not.toHaveCount(1);
  await page.locator("#threads").fill("6");
  const recipe = await page.locator("#recipe").inputValue();
  await page.getByRole("button", { name: "苍渊主题" }).click();
  await expect(page.locator("#threads")).toHaveValue("6");
  await expect(page.locator("#recipe")).toHaveValue(recipe);
  await page.goto("/projects/legacy");
  await expect(page.locator(".runs-table tbody tr")).toHaveCount(10);
  const check = page.locator('.runs-table input[type="checkbox"]').first();
  await check.check();
  const region = page.getByRole("region", { name: "训练运行记录" });
  await region.evaluate((el) => {
    el.scrollTop = 100;
  });
  const scroll = await region.evaluate((el) => el.scrollTop);
  await page.getByRole("button", { name: "白垣主题" }).click();
  await expect(check).toBeChecked();
  expect(await region.evaluate((el) => el.scrollTop)).toBe(scroll);
});

test("blocked preference storage falls back to a usable Vallum theme", async ({
  page,
}) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, "localStorage", {
      get() {
        throw new Error("blocked");
      },
    });
  });
  await page.goto("/projects");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "vallum");
  await page.getByRole("button", { name: "苍渊主题" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "abyssus");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "vallum");
});

test("invalid stored theme falls back before the first paint", async ({
  page,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem("ninna.theme", "unknown"),
  );
  await page.goto("/projects");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "vallum");
  await expect(page.locator("body")).toHaveCSS(
    "background-color",
    "rgb(248, 247, 242)",
  );
});

for (const theme of ["vallum", "abyssus"] as const) {
  test(`${theme} key pages stay accessible and fit narrow viewports`, async ({
    page,
  }) => {
    await page.addInitScript(
      (value) => localStorage.setItem("ninna.theme", value),
      theme,
    );
    for (const width of [320, 768, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      for (const path of [
        "/projects/legacy",
        "/runs/new?project=legacy",
        "/assets/dataset",
        "/assets/image",
        "/hub",
        "/runs/run-b196f3593b05",
      ]) {
        await page.goto(path);
        await expect(page.locator(".loading")).toHaveCount(0);
        await page.evaluate(() => document.fonts.ready);
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        ).toBe(true);
        const results = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
          .analyze();
        expect(
          results.violations.map((v) => ({
            id: v.id,
            nodes: v.nodes.map((n) => n.target),
          })),
        ).toEqual([]);
      }
    }
  });
}
