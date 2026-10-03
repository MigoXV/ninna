import { expect, test } from "@playwright/test";
import { formatBytes } from "../src/format";

test("image sizes select decimal units and handle missing metadata", () => {
  for (const [bytes, label] of [
    [0, "0 B"],
    [999, "999 B"],
    [1000, "1 KB"],
    [1_234_000, "1.23 MB"],
    [15_420_000_000, "15.42 GB"],
    [1_000_000_000_000, "1 TB"],
    [999_999_999, "1 GB"],
    [undefined, "—"],
    [null, "—"],
    [-1, "—"],
    [NaN, "—"],
    [Infinity, "—"],
  ] as const) {
    expect(formatBytes(bytes)).toBe(label);
  }
});
