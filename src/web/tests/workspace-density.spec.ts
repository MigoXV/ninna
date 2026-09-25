import { test, expect } from "@playwright/test";

test("real runs own their scroll positions and keep task controls visible", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/runs");
  const rows = page.locator(".runs-table tbody tr");
  await expect(rows).toHaveCount(10);
  await page.evaluate(() => document.fonts.ready);
  const region = page.getByRole("region", { name: "训练运行记录" });
  const visible = await rows.evaluateAll((nodes) => {
    const bottom = document
      .querySelector(".work-scroll")!
      .getBoundingClientRect().bottom;
    return nodes.filter((n) => n.getBoundingClientRect().bottom <= bottom)
      .length;
  });
  expect(visible).toBeGreaterThanOrEqual(7);
  const titleY = (await page.locator("h1").boundingBox())!.y;
  await region.evaluate((e) => {
    e.scrollTop = 140;
  });
  await expect.poll(() => region.evaluate((e) => e.scrollTop)).toBe(140);
  expect((await page.locator("h1").boundingBox())!.y).toBe(titleY);
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
  // Select an already visible row so clicking does not alter the saved list position.
  const runLink = rows.nth(4).getByRole("link", { name: /查看/ });
  await runLink.click();
  const detail = page.getByRole("region", { name: "运行详情内容" });
  await expect(detail).toBeVisible();
  expect(await detail.evaluate((e) => e.scrollTop)).toBe(0);
  await detail.evaluate((e) => {
    e.scrollTop = 100;
  });
  await expect.poll(() => detail.evaluate((e) => e.scrollTop)).toBe(100);
  await page.getByRole("button", { name: /^产物/ }).click();
  expect(await detail.evaluate((e) => e.scrollTop)).toBe(0);
  await page.getByRole("button", { name: "训练", exact: true }).click();
  await expect.poll(() => detail.evaluate((e) => e.scrollTop)).toBe(100);
  await page.locator(".back-link").click();
  await expect.poll(() => region.evaluate((e) => e.scrollTop)).toBe(140);
  await rows.nth(5).getByRole("link", { name: /查看/ }).click();
  await expect(detail).toBeVisible();
  expect(await detail.evaluate((e) => e.scrollTop)).toBe(0);
  await page.locator(".back-link").click();
  await page.getByRole("button", { name: "下一页", exact: true }).click();
  await expect.poll(() => region.evaluate((e) => e.scrollTop)).toBe(0);
  await page
    .locator(".sidebar")
    .getByRole("link", { name: "中心存储" })
    .click();
  await page
    .locator(".sidebar")
    .getByRole("link", { name: "训练运行" })
    .click();
  await expect(page.locator(".pagination")).toContainText(/2 \/ \d+/);
});

test("fonts are served locally and narrow layouts retain reachable content", async ({
  page,
}) => {
  const fonts: string[] = [];
  page.on("response", (r) => {
    if (/\.woff2?/.test(r.url())) fonts.push(r.url());
  });
  await page.goto("/runs");
  await expect(page.locator("tbody tr")).toHaveCount(10);
  await page.evaluate(() => document.fonts.ready);
  expect(fonts.some((url) => url.includes("inter"))).toBe(true);
  expect(fonts.some((url) => url.includes("noto-sans-sc"))).toBe(true);
  expect(fonts.some((url) => url.includes("ibm-plex-mono"))).toBe(true);
  expect(
    fonts.every((url) => new URL(url).origin === new URL(page.url()).origin),
  ).toBe(true);
  for (const width of [320, 720, 1280, 1920]) {
    await page.setViewportSize({ width, height: width === 720 ? 450 : 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    if (width < 1000) {
      expect(
        await page.evaluate(() => getComputedStyle(document.body).overflow),
      ).not.toBe("hidden");
      await page
        .getByRole("button", { name: "下一页", exact: true })
        .scrollIntoViewIfNeeded();
      await expect(
        page.getByRole("button", { name: "下一页", exact: true }),
      ).toBeInViewport();
    }
  }
});
