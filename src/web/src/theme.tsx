import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

export type Theme = "vallum" | "abyssus";

export function ThemeSwitch() {
  const [theme, setTheme] = useState<Theme>(
    document.documentElement.dataset.theme === "abyssus" ? "abyssus" : "vallum",
  );
  useEffect(() => {
    const sync = () =>
      setTheme(
        document.documentElement.dataset.theme === "abyssus"
          ? "abyssus"
          : "vallum",
      );
    window.addEventListener("ninna:theme", sync);
    return () => window.removeEventListener("ninna:theme", sync);
  }, []);
  function change(next: Theme) {
    document.documentElement.dataset.theme = next;
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute(
        "content",
        getComputedStyle(document.documentElement)
          .getPropertyValue("--bg-primary")
          .trim(),
      );
    try {
      localStorage.setItem("ninna.theme", next);
    } catch {
      // The current tab remains usable when preference storage is unavailable.
    }
    setTheme(next);
    window.dispatchEvent(new Event("ninna:theme"));
  }
  return (
    <div className="theme-switch" role="group" aria-label="界面主题">
      <button
        type="button"
        aria-label="白垣主题"
        aria-pressed={theme === "vallum"}
        onClick={() => change("vallum")}
      >
        <Sun size={14} aria-hidden="true" />
        <span>白垣</span>
      </button>
      <button
        type="button"
        aria-label="苍渊主题"
        aria-pressed={theme === "abyssus"}
        onClick={() => change("abyssus")}
      >
        <Moon size={14} aria-hidden="true" />
        <span>苍渊</span>
      </button>
    </div>
  );
}
