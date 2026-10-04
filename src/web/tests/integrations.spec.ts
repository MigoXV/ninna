import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("Codex setup and sources stay inside the platform and fit both viewports", async ({
  page,
}) => {
  for (const path of ["/settings/agent", "/settings/sources"]) {
    for (const width of [390, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.goto(path);
      await expect(page.locator("h1")).toBeVisible();
      await expect(page.locator("iframe")).toHaveCount(0);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBeTruthy();
      expect(
        (
          await new AxeBuilder({ page })
            .withTags(["wcag2a", "wcag2aa"])
            .analyze()
        ).violations,
      ).toEqual([]);
    }
  }
});
