/** Decimal byte units, matching the KB/MB/GB labels used by image registries. */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || !Number.isFinite(bytes) || bytes < 0) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1000 && unit < units.length - 1) {
    value /= 1000;
    unit++;
  }
  // Promote rounded boundary values as well, avoiding labels such as 1000 MB.
  if (Number(value.toFixed(2)) >= 1000 && unit < units.length - 1) {
    value /= 1000;
    unit++;
  }
  return `${Number(value.toFixed(2))} ${units[unit]}`;
}
