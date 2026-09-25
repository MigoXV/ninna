import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Folder, Plus, Search, X } from "lucide-react";
import { api, useData } from "./api";
import type { Project } from "./types";
import { Empty, ErrorNotice, Loading, PageHeader, time } from "./ui";

export function ProjectsPage() {
  const query = useData<Project[]>("/projects", 4000);
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function create(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const project = await api<Project>("/projects", { name, description });
      navigate(`/projects/${project.id}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const projects =
    query.data?.filter((project) =>
      `${project.name} ${project.description}`
        .toLowerCase()
        .includes(search.toLowerCase()),
    ) || [];
  return (
    <section className="projects-page">
      <PageHeader
        eyebrow="Projects"
        title="项目"
        description="围绕一个训练目标，组织运行与实验。"
        actions={
          <button className="button primary" onClick={() => setCreating(true)}>
            <Plus size={16} />
            新建项目
          </button>
        }
      />
      <ErrorNotice error={query.error} onRetry={query.refresh} />
      {creating && (
        <form className="project-create" onSubmit={create}>
          <div className="section-heading">
            <h2>新建项目</h2>
            <button
              type="button"
              className="icon-button"
              aria-label="关闭新建项目"
              onClick={() => setCreating(false)}
            >
              <X size={16} />
            </button>
          </div>
          <label htmlFor="project-name">项目名称</label>
          <input
            id="project-name"
            autoFocus
            required
            maxLength={80}
            pattern="[a-z0-9][a-z0-9_-]*"
            placeholder="image-classification"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <p className="muted">
            使用小写字母、数字、短横线或下划线，名称也是项目标识。
          </p>
          <label htmlFor="project-description">
            说明 <span className="muted">可选</span>
          </label>
          <textarea
            id="project-description"
            maxLength={1000}
            rows={2}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="这个项目要解决什么问题？"
          />
          <ErrorNotice error={error} />
          <button className="button primary" disabled={busy}>
            {busy ? "正在创建…" : "创建项目"}
          </button>
        </form>
      )}
      <div className="table-toolbar">
        <span>{query.data?.length ?? 0} 个项目</span>
        <label className="search-field">
          <Search size={16} />
          <input
            aria-label="搜索项目"
            placeholder="搜索项目"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
      </div>
      {query.loading ? (
        <Loading />
      ) : projects.length ? (
        <div className="project-list">
          {projects.map((project) => (
            <Link
              className="project-row"
              key={project.id}
              to={`/projects/${project.id}`}
            >
              <Folder size={19} strokeWidth={1.5} />
              <div className="project-identity">
                <h2>{project.name}</h2>
                <p>{project.description || "尚未添加项目说明"}</p>
              </div>
              <div className="project-count">
                <strong>{project.run_count}</strong>
                <span>
                  次运行
                  {project.active_count
                    ? ` · ${project.active_count} 进行中`
                    : ""}
                </span>
              </div>
              <div className="project-updated">
                <span>最近运行</span>
                <span>
                  {project.last_run_at ? time(project.last_run_at) : "暂无运行"}
                </span>
              </div>
              <ArrowRight size={16} />
            </Link>
          ))}
        </div>
      ) : (
        <Empty
          title={search ? "没有匹配的项目" : "从一个项目开始"}
          description={
            search
              ? "修改搜索条件，或创建新的项目。"
              : "先创建项目，再组合数据集、模型与配方开始训练。"
          }
        />
      )}
    </section>
  );
}
