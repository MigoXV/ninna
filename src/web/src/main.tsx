import { StrictMode, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  BrowserRouter,
  Link,
  NavLink,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import {
  Activity,
  ArrowUpRight,
  Award,
  Box,
  Boxes,
  ChevronRight,
  Database,
  FolderCode,
  Github,
  Menu,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { useData } from "./api";
import { RunsPage, CreatePage, RunPage, ComparePage } from "./runs";
import { AssetsPage, CertificationPage } from "./pages";
import "./style.css";
const nav = [
  { label: "训练运行", path: "/runs", icon: Activity },
  { label: "系统验收", path: "/certification", icon: Award },
];
const definitions = [
  { label: "数据集", code: "Dataset", kind: "dataset", icon: Database },
  { label: "模型", code: "Model", kind: "model", icon: Boxes },
  {
    label: "训练配方",
    code: "Recipe",
    kind: "recipe",
    icon: SlidersHorizontal,
  },
];
const environments = [
  { label: "运行环境", code: "Runtime", kind: "runtime", icon: Box },
  { label: "代码空间", code: "Workspace", kind: "workspace", icon: FolderCode },
];
function Shell() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const menu = useRef<HTMLButtonElement>(null);
  const sidebar = useRef<HTMLElement>(null);
  const health = useData<{ docker: string; initialized: boolean }>(
    "/health",
    10000,
  );
  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement;
    sidebar.current?.querySelector<HTMLElement>("a")?.focus();
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        menu.current?.focus();
      }
      if (e.key === "Tab") {
        const nodes =
          sidebar.current?.querySelectorAll<HTMLElement>("a,button");
        if (!nodes?.length) return;
        const first = nodes[0],
          last = nodes[nodes.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", handler);
    return () => {
      document.removeEventListener("keydown", handler);
      previous?.focus();
    };
  }, [open]);
  return (
    <div className="app">
      <a href="#main" className="skip-link">
        跳到主要内容
      </a>
      <header className="mobile-top">
        <button
          ref={menu}
          className="icon-button"
          aria-label="打开导航"
          aria-expanded={open}
          onClick={() => setOpen(true)}
        >
          <Menu size={20} />
        </button>
        <Link to="/runs" className="brand">
          ninna<span className="brand-period">.</span>
        </Link>
        <span className="mono">WORKSPACE</span>
      </header>
      {open && <div className="nav-backdrop" onClick={() => setOpen(false)} />}
      <aside
        ref={sidebar}
        className={"sidebar " + (open ? "open" : "")}
        aria-label="主导航"
      >
        <div className="brand-row">
          <Link className="brand" to="/runs">
            ninna<span className="brand-period">.</span>
          </Link>
          <span className="edition">LAB / 01</span>
          <button
            className="icon-button close-nav"
            aria-label="关闭导航"
            onClick={() => setOpen(false)}
          >
            <X size={18} />
          </button>
        </div>
        <div className="workspace-identity">
          <span className="workspace-mark">N</span>
          <div>
            <strong>训练工作空间</strong>
            <small>Local workspace</small>
          </div>
          <ChevronRight size={14} />
        </div>
        <nav>
          <p className="nav-label">工作台</p>
          {nav.map((n) => (
            <NavLink
              key={n.path}
              to={n.path}
              className={({ isActive }) =>
                "nav-item " + (isActive ? "active" : "")
              }
            >
              <n.icon size={17} />
              <span>{n.label}</span>
              {n.path === "/runs" && <span className="nav-dot" />}
            </NavLink>
          ))}
          {[
            { title: "训练定义", items: definitions },
            { title: "执行环境", items: environments },
          ].map((group) => (
            <div className="nav-group" key={group.title}>
              <p className="nav-label">{group.title}</p>
              {group.items.map((n) => (
                <NavLink
                  key={n.kind}
                  to={"/assets/" + n.kind}
                  className={({ isActive }) =>
                    "nav-item " + (isActive ? "active" : "")
                  }
                >
                  <n.icon size={17} />
                  <span>{n.label}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="daemon-health">
            <span
              className={
                "health-dot " +
                (health.data?.docker === "available" ? "good" : "")
              }
            />
            <span>
              {health.error
                ? "平台连接中断"
                : health.data?.docker === "available"
                  ? "Docker 已连接"
                  : "检查 Docker 连接"}
            </span>
            <span className="mono">CPU</span>
          </div>
          <a
            href="https://github.com/MigoXV/ninna"
            target="_blank"
            rel="noreferrer"
          >
            <Github size={14} />
            Ninna / v0.1
            <ArrowUpRight size={13} />
          </a>
        </div>
      </aside>
      <div className="main-shell" inert={open ? true : undefined}>
        <div className="topbar">
          <span>Ninna</span>
          <ChevronRight size={12} />
          <span>训练工作空间</span>
          <div className="topbar-right">
            <span className="local-marker" />
            本地执行 <span className="topbar-separator" /> Docker Engine
          </div>
        </div>
        <main id="main">
          <Routes>
            <Route path="/" element={<RunsPage />} />
            <Route path="/runs" element={<RunsPage />} />
            <Route path="/runs/new" element={<CreatePage />} />
            <Route path="/runs/compare" element={<ComparePage />} />
            <Route path="/runs/:id" element={<RunPage />} />
            <Route path="/assets/:kind" element={<AssetsPage />} />
            <Route path="/certification" element={<CertificationPage />} />
            <Route
              path="*"
              element={
                <div className="empty">
                  <h1>页面不存在</h1>
                  <Link to="/runs">返回训练运行</Link>
                </div>
              }
            />
          </Routes>
        </main>
        <footer className="page-footer">
          <span>Ninna · 每一次训练，有迹可循。</span>
          <span className="mono">DATASET × MODEL × RECIPE</span>
        </footer>
      </div>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  </StrictMode>,
);
