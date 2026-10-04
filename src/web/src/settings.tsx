import { Link, useLocation } from "react-router-dom";
import { ThemeSwitch } from "./theme";
import { PageHeader } from "./ui";

export function AppearanceSettingsPage() {
  const { state } = useLocation();
  const from =
    typeof state?.from === "string" &&
    state.from.startsWith("/") &&
    !state.from.startsWith("//") &&
    state.from !== "/settings/appearance"
      ? state.from
      : "/projects";
  return (
    <div className="appearance-settings">
      <Link to={from} className="back-link">
        ‹ 返回工作空间
      </Link>
      <PageHeader
        eyebrow="偏好设置"
        title="设置"
        description="管理界面外观与使用偏好。"
      />
      <section
        aria-labelledby="appearance-heading"
        className="appearance-section"
      >
        <h2 id="appearance-heading">外观</h2>
        <div className="appearance-theme-row">
          <div>
            <h3>界面主题</h3>
            <p>白垣适合日常工作，苍渊适合暗光环境。</p>
          </div>
          <ThemeSwitch />
        </div>
      </section>
    </div>
  );
}
