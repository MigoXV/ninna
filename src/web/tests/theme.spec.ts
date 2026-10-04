import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("theme follows the locked palette, survives reload, and synchronizes desktop/mobile controls", async ({
  page,
}) => {
  await page.goto("/settings/appearance");
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

test("theme controls live in settings and return to the originating page", async ({
  page,
}) => {
  await page.goto("/work/new?project=legacy");
  await expect(page.getByRole("button", { name: "苍渊主题" })).toHaveCount(0);
  await page.getByRole("link", { name: "设置", exact: true }).click();
  await page.getByRole("button", { name: "苍渊主题" }).click();
  await page.getByRole("link", { name: "返回工作空间" }).click();
  await expect(page).toHaveURL(/work\/new\?project=legacy/);
  await expect(page.locator("html")).toHaveAttribute("data-theme", "abyssus");
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
  await page.goto("/settings/appearance");
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
  await page.goto("/settings/appearance");
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
        "/settings/agent",
        "/settings/appearance",
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
