import { useEffect, useRef, useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import {
  ArrowDown,
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronDown,
  CircleHelp,
  Copy,
  Download,
  FileCode2,
  GitCompareArrows,
  LoaderCircle,
  Pause,
  Play,
  Plus,
  Search,
  Square,
  Terminal,
  X,
} from "lucide-react";
import { api, useData } from "./api";
import type { Asset, Run } from "./types";
import {
  AssetLink,
  duration,
  Empty,
  ErrorNotice,
  Json,
  Loading,
  LossChart,
  Metric,
  PageHeader,
  percent,
  SectionHeader,
  ShortId,
  Status,
  time,
} from "./ui";
const terminal = ["SUCCESS", "FAILED", "CANCELLED"];
export function RunsPage() {
  const { data: runs, error, loading, refresh } = useData<Run[]>("/runs", 2500);
  const [search, setSearch] = useState(""),
    [filter, setFilter] = useState("ALL"),
    [page, setPage] = useState(1),
    [selected, setSelected] = useState<string[]>([]),
    [busy, setBusy] = useState(false),
    [initError, setInitError] = useState("");
  const searchInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const focusSearch = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (
        event.key === "/" &&
        !target.matches("input, textarea, select, [contenteditable]")
      ) {
        event.preventDefault();
        searchInput.current?.focus();
      }
    };
    window.addEventListener("keydown", focusSearch);
    return () => window.removeEventListener("keydown", focusSearch);
  }, []);
  const assets = useData<Asset[]>("/assets/dataset");
  const rows =
    runs?.filter(
      (r) =>
        (filter === "ALL" ||
          (filter === "ACTIVE"
            ? !terminal.includes(r.status)
            : r.status === filter)) &&
        (
          r.id +
          " " +
          r.training_spec.recipe.name +
          " " +
          r.training_spec.model.name
        )
          .toLowerCase()
          .includes(search.toLowerCase()),
    ) || [];
  const pageSize = 10;
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const visibleRows = rows.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize,
  );
  function resetFilters() {
    setSearch("");
    setFilter("ALL");
    setPage(1);
    searchInput.current?.focus();
  }
  const active = runs?.filter((r) => !terminal.includes(r.status)).length || 0;
  const completed = runs?.filter((r) => r.status === "SUCCESS") || [];
  const best = completed.length
    ? Math.max(...completed.map((r) => r.metrics?.test_accuracy || 0))
    : undefined;
  async function init() {
    setBusy(true);
    setInitError("");
    try {
      await api("/initialize", {});
      await assets.refresh();
      await refresh();
    } catch (e) {
      setInitError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeader
        eyebrow="实验 / Experiments"
        title="训练运行"
        description="把训练定义变成一次可追溯的实验。"
        actions={
          <Link className="button primary" to="/runs/new">
            <Plus size={17} />
            创建训练
          </Link>
        }
      />
      <ErrorNotice error={error} onRetry={refresh} />
      <ErrorNotice error={initError} />
      <div className="overview-strip">
        <Metric
          label="正在运行"
          value={
            <>
              {active}
              <span className="metric-unit">runs</span>
            </>
          }
          detail="真实 Docker 容器执行"
        />
        <Metric
          label="已完成训练"
          value={
            <>
              {completed.length}
              <span className="metric-unit">runs</span>
            </>
          }
          detail="保留权重、指标与完整日志"
        />
        <Metric
          label="最佳测试准确率"
          value={percent(best)}
          detail="已完成 Run · MNIST test split"
        />
        <Link to="/certification" className="cert-entry">
          <span className="cert-emblem">
            <Check size={22} />
          </span>
          <div>
            <strong>验证整条训练链路</strong>
            <span>
              MNIST Certification <ArrowUpRight size={13} />
            </span>
          </div>
        </Link>
      </div>
      {assets.data?.length === 0 && (
        <div className="setup-banner">
          <div>
            <strong>准备你的第一个实验</strong>
            <p>注册 MNIST、CNN 模型、两种 Recipe 和代码空间，开始真实训练。</p>
          </div>
          <button className="button" disabled={busy} onClick={init}>
            {busy ? (
              <LoaderCircle size={15} className="spin" />
            ) : (
              <Download size={15} />
            )}{" "}
            {busy ? "正在下载并校验数据…" : "初始化训练资产"}
          </button>
        </div>
      )}
      <div className="table-toolbar">
        <div className="tabs compact" aria-label="运行筛选">
          {[
            ["ALL", "全部运行"],
            ["ACTIVE", "进行中"],
            ["SUCCESS", "已完成"],
            ["FAILED", "失败"],
            ["CANCELLED", "已取消"],
          ].map(([value, label]) => (
            <button
              key={value}
              className={filter === value ? "selected" : ""}
              aria-pressed={filter === value}
              onClick={() => {
                setFilter(value);
                setPage(1);
              }}
            >
              {label}
              {value === "ALL" && (
                <span className="count">{runs?.length || 0}</span>
              )}
            </button>
          ))}
        </div>
        <div className="toolbar-right">
          <label className="search-field">
            <Search size={16} />
            <input
              ref={searchInput}
              aria-label="搜索训练运行"
              placeholder="搜索运行、模型或 Recipe"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
            />
            <kbd>/</kbd>
          </label>
        </div>
      </div>
      {selected.length > 0 && (
        <div className="selection-bar" aria-label="比较选择">
          <span role="status">
            已选择 {selected.length} / 2 个 Run，可跨页选择
          </span>
          <button className="text-button" onClick={() => setSelected([])}>
            清空选择
          </button>
          {selected.length === 2 && (
            <Link
              className="button small"
              to={"/runs/compare?ids=" + selected.join(",")}
            >
              <GitCompareArrows size={14} />
              比较 2 个 Run
            </Link>
          )}
        </div>
      )}
      {loading && !runs ? (
        <Loading />
      ) : rows.length ? (
        <div className="table-scroll">
          <table className="runs-table">
            <thead>
              <tr>
                <th className="check-col">
                  <span className="sr-only">选择比较</span>
                </th>
                <th>训练运行</th>
                <th>训练定义</th>
                <th>状态</th>
                <th>准确率</th>
                <th>用时</th>
                <th>创建时间</th>
                <th>
                  <span className="sr-only">查看</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((r) => (
                <tr
                  key={r.id}
                  className={
                    selected.includes(r.id) ? "row-selected" : undefined
                  }
                >
                  <td>
                    <input
                      type="checkbox"
                      aria-label={"选择 " + r.id + " 进行比较"}
                      checked={selected.includes(r.id)}
                      disabled={
                        selected.length >= 2 && !selected.includes(r.id)
                      }
                      onChange={(e) =>
                        setSelected(
                          e.target.checked
                            ? [...selected, r.id]
                            : selected.filter((id) => id !== r.id),
                        )
                      }
                    />
                  </td>
                  <td>
                    <Link className="run-title" to={"/runs/" + r.id}>
                      {r.training_spec.model.name}
                      <ArrowUpRight size={13} />
                    </Link>
                    <span className="row-subtitle mono">{r.id}</span>
                  </td>
                  <td>
                    <span>
                      {r.training_spec.recipe.name}
                      <span className="version">
                        {r.training_spec.recipe.version}
                      </span>
                    </span>
                    <span className="row-subtitle">
                      {r.training_spec.dataset.name}{" "}
                      <span className="dot-separator">·</span> CPU
                    </span>
                  </td>
                  <td>
                    <Status value={r.status} />
                  </td>
                  <td className="numeric">
                    {percent(r.metrics?.test_accuracy)}
                  </td>
                  <td className="numeric muted">
                    {duration(r.started_at, r.finished_at)}
                  </td>
                  <td className="muted nowrap">{time(r.created_at)}</td>
                  <td>
                    <Link
                      className="icon-button"
                      aria-label={"查看 " + r.id}
                      to={"/runs/" + r.id}
                    >
                      <ArrowRight size={16} />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty
          title={
            search || filter !== "ALL" ? "没有匹配的训练" : "从第一轮训练开始"
          }
          description={
            search || filter !== "ALL"
              ? "调整搜索或状态筛选后重试。"
              : "选择数据集、模型和 Recipe，让每一个结果都能被验证。"
          }
          action={
            search || filter !== "ALL" ? (
              <button className="button" onClick={resetFilters}>
                清空筛选
              </button>
            ) : (
              <Link to="/runs/new" className="text-link">
                创建训练 <ArrowRight size={15} />
              </Link>
            )
          }
        />
      )}
      <div className="list-footnote">
        <span role="status">
          {rows.length} 条运行记录
          {rows.length > 0 &&
            ` · 第 ${(currentPage - 1) * pageSize + 1}–${Math.min(currentPage * pageSize, rows.length)} 条`}
        </span>
        <nav className="pagination" aria-label="运行列表分页">
          <button
            className="icon-button"
            aria-label="上一页"
            disabled={currentPage === 1}
            onClick={() => setPage(currentPage - 1)}
          >
            <ArrowLeft size={16} />
          </button>
          <span>
            {currentPage} / {pageCount}
          </span>
          <button
            className="icon-button"
            aria-label="下一页"
            disabled={currentPage === pageCount}
            onClick={() => setPage(currentPage + 1)}
          >
            <ArrowRight size={16} />
          </button>
        </nav>
      </div>
      <div className="definition-note">
        <span className="note-number">01 —</span>
        <div>
          <strong>定义训练，独立于执行环境。</strong>
          <p>
            Dataset 决定用什么数据，Model 决定训练谁，Recipe
            决定如何训练。Runtime 与 Workspace 负责让它真实运行。
          </p>
        </div>
        <CircleHelp size={18} />
      </div>
    </>
  );
}
export function CreatePage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [all, setAll] = useState<Record<string, Asset[]>>({}),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true);
  const [selection, setSelection] = useState({
      dataset: "",
      model: "",
      recipe: "",
      runtime: "",
      workspace: "",
    }),
    [threads, setThreads] = useState(4),
    [memory, setMemory] = useState(4096);
  useEffect(() => {
    let current = true;
    Promise.all(
      ["dataset", "model", "recipe", "runtime", "workspace"].map(
        async (kind) => {
          const assets = await api<Asset[]>("/assets/" + kind);
          return [
            kind,
            kind === "runtime"
              ? assets.filter(
                  (a) => a.metadata.transformers && a.metadata.datasets,
                )
              : assets,
          ] as const;
        },
      ),
    )
      .then(async (pairs) => {
        if (!current) return;
        const assets = Object.fromEntries(pairs);
        setAll(assets);
        const preferred: Record<string, string> = {
          dataset: "mnist",
          model: "mnist-cnn",
          recipe: "mnist-adam",
          runtime: "mnist-pytorch-runtime",
          workspace: "mnist-hf",
        };
        const defaults = Object.fromEntries(
          pairs.map(([kind, list]) => [
            kind,
            list.find(
              (a) =>
                a.version ===
                  (kind === "runtime"
                    ? "v3"
                    : ["dataset", "model"].includes(kind)
                      ? "v2"
                      : "v1") && a.name === preferred[kind],
            )?.id ||
              list.find((a) => a.version === "v1")?.id ||
              "",
          ]),
        ) as typeof selection;
        const parent = params.get("from");
        if (parent) {
          const r = await api<Run>("/runs/" + parent);
          if (!current) return;
          for (const kind of ["dataset", "model", "recipe"] as const)
            defaults[kind] = r.assets[kind].id;
          if (assets.runtime.some((a) => a.id === r.assets.runtime.id))
            defaults.runtime = r.assets.runtime.id;
          defaults.workspace = r.assets.workspace.id;
          setThreads(r.execution_spec.resources.cpu_threads);
          setMemory(r.execution_spec.resources.memory_mb);
        }
        for (const kind of Object.keys(defaults) as (keyof typeof defaults)[]) {
          const requested = params.get(kind);
          if (requested && assets[kind].some((asset) => asset.id === requested))
            defaults[kind] = requested;
        }
        setSelection(defaults);
      })
      .catch((e) => {
        if (current) setError(e.message);
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [params]);
  const chosen = (kind: string) =>
    all[kind]?.find((a) => a.id === selection[kind as keyof typeof selection]);
  const recipe = chosen("recipe");
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const ref = (kind: string) => ({
        name: chosen(kind)!.name,
        version: chosen(kind)!.version,
      });
      const r = await api<Run>("/runs", {
        training_spec: {
          dataset: ref("dataset"),
          model: ref("model"),
          recipe: ref("recipe"),
        },
        execution_spec: {
          runtime: ref("runtime"),
          workspace: { name: chosen("workspace")!.name, snapshot: "current" },
          resources: {
            device: "cpu",
            gpu_count: 0,
            cpu_threads: threads,
            memory_mb: memory,
          },
        },
        parent_run_id: params.get("from"),
      });
      navigate("/runs/" + r.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function field(
    kind: keyof typeof selection,
    label: string,
    description: string,
  ) {
    return (
      <div className="asset-field" data-asset-kind={kind}>
        <label htmlFor={kind}>
          {label}
          <span>{kind[0].toUpperCase() + kind.slice(1)}</span>
        </label>
        <div className="select-wrap">
          <select
            id={kind}
            value={selection[kind]}
            onChange={(e) =>
              setSelection({ ...selection, [kind]: e.target.value })
            }
            required
          >
            <option value="" disabled>
              选择已注册资产
            </option>
            {all[kind]?.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name} / {a.version}
              </option>
            ))}
          </select>
          <ChevronDown size={15} />
        </div>
        <p>{description}</p>
      </div>
    );
  }
  return (
    <>
      <Link to="/runs" className="back-link">
        <ArrowLeft size={14} />
        训练运行
      </Link>
      <PageHeader
        eyebrow="新实验 / New experiment"
        title="创建训练"
        description="组合训练资产，交给一个独立的 Docker 容器执行。"
      />
      <ErrorNotice error={error} />
      {loading ? (
        <Loading />
      ) : (
        <form onSubmit={submit} className="create-layout">
          <div>
            <section className="form-section">
              <div className="numbered-heading">
                <span>01</span>
                <div>
                  <h2>训练定义</h2>
                  <p>这一次，用什么数据，训练谁，如何训练。</p>
                </div>
              </div>
              {field(
                "dataset",
                "数据集",
                "平台提供只读挂载；训练过程不会重新下载数据。",
              )}
              {field("model", "模型", "架构与初始化权重独立于训练策略。")}
              {field(
                "recipe",
                "训练配方",
                "替换 Recipe 即可改变优化器和训练策略。",
              )}
              {recipe && (
                <div className="recipe-summary">
                  <span>{recipe.loss}</span>
                  <span>{recipe.optimizer.name}</span>
                  <span>lr {recipe.optimizer.params.lr}</span>
                  <span>{recipe.epochs} epochs</span>
                  <span>batch {recipe.batch_size}</span>
                </div>
              )}
            </section>
            <section className="form-section">
              <div className="numbered-heading">
                <span>02</span>
                <div>
                  <h2>执行环境</h2>
                  <p>稳定的基础环境，加上本次训练的代码快照。</p>
                </div>
              </div>
              {field(
                "runtime",
                "运行环境",
                "固定镜像 ID，确保执行环境可追溯。",
              )}
              {field(
                "workspace",
                "代码空间",
                "提交时创建不可变快照，包含当前目录内的训练代码。",
              )}
              <div className="resource-fields">
                <div>
                  <label htmlFor="device">计算设备</label>
                  <input id="device" readOnly value="CPU" />
                </div>
                <div>
                  <label htmlFor="threads">CPU 线程</label>
                  <input
                    id="threads"
                    type="number"
                    min={1}
                    max={32}
                    value={threads}
                    onChange={(e) => setThreads(Number(e.target.value))}
                  />
                </div>
                <div>
                  <label htmlFor="memory">内存 / MiB</label>
                  <input
                    id="memory"
                    type="number"
                    min={512}
                    max={65536}
                    step={512}
                    value={memory}
                    onChange={(e) => setMemory(Number(e.target.value))}
                  />
                </div>
              </div>
            </section>
          </div>
          <aside className="submission-summary">
            <span className="eyebrow">本次训练</span>
            <h2>准备成为一个 Run</h2>
            <div className="composition">
              {(["dataset", "model", "recipe"] as const).map((kind, i) => (
                <div key={kind} data-asset-kind={kind}>
                  {i > 0 && <span className="composition-times">×</span>}
                  <span className="composition-label">{kind}</span>
                  <strong>{chosen(kind)?.name || "尚未选择"}</strong>
                  <span className="mono muted">
                    {chosen(kind)?.version || "—"}
                  </span>
                </div>
              ))}
            </div>
            <div className="summary-environment">
              <span>执行方式</span>
              <strong>Docker · CPU</strong>
              <span>资源上限</span>
              <strong>
                {threads} threads / {memory / 1024} GiB
              </strong>
              <span>Workspace</span>
              <strong>提交时创建快照</strong>
            </div>
            <button
              type="submit"
              className="button primary wide"
              disabled={busy || Object.values(selection).some((v) => !v)}
            >
              {busy ? (
                <LoaderCircle size={16} className="spin" />
              ) : (
                <Play size={16} />
              )}{" "}
              {busy ? "正在创建训练…" : "开始训练"}
              <ArrowRight size={16} />
            </button>
            <p className="submit-note">
              创建独立 Run，保存训练定义、环境信息和全部输出。
            </p>
            {Object.values(selection).some((v) => !v) && (
              <Link to="/runs" className="text-link">
                先返回初始化训练资产 <ArrowRight size={14} />
              </Link>
            )}
          </aside>
        </form>
      )}
    </>
  );
}
function LogViewer({ id }: { id: string }) {
  const [stream, setStream] = useState("stdout"),
    [content, setContent] = useState(""),
    [error, setError] = useState(""),
    [follow, setFollow] = useState(true),
    [search, setSearch] = useState("");
  const region = useRef<HTMLPreElement>(null);
  const offset = useRef(0);
  useEffect(() => {
    let active = true;
    let pending = false;
    offset.current = 0;
    setContent("");
    setError("");
    async function read() {
      if (pending) return;
      pending = true;
      try {
        const r = await api<{ content: string; offset: number }>(
          `/runs/${id}/logs?stream=${stream}&offset=${offset.current}`,
        );
        if (active) {
          offset.current = r.offset;
          setContent((v) => (v + r.content).slice(-1000000));
          setError("");
        }
      } catch (e) {
        if (active) setError((e as Error).message);
      } finally {
        pending = false;
      }
    }
    void read();
    const timer = setInterval(read, 1500);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [id, stream]);
  useEffect(() => {
    if (follow && region.current)
      region.current.scrollTop = region.current.scrollHeight;
  }, [content, follow]);
  const lines = content
    .split("\n")
    .filter(
      (line) => !search || line.toLowerCase().includes(search.toLowerCase()),
    );
  return (
    <section className="log-section">
      <div className="log-toolbar">
        <div className="log-title">
          <Terminal size={16} />
          <h2>执行日志</h2>
          <div className="segmented">
            {["stdout", "stderr"].map((s) => (
              <button
                key={s}
                className={s === stream ? "selected" : ""}
                onClick={() => setStream(s)}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
        <div className="log-tools">
          <label className="log-search">
            <Search size={14} />
            <input
              aria-label="搜索日志"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="查找日志"
            />
          </label>
          <button
            className="icon-button"
            aria-label={follow ? "暂停自动滚动" : "跟随最新日志"}
            aria-pressed={follow}
            onClick={() => setFollow(!follow)}
          >
            {follow ? <Pause size={15} /> : <ArrowDown size={15} />}
          </button>
          <a
            className="icon-button"
            aria-label="下载当前日志"
            href={`/api/runs/${id}/artifacts/${stream}.log`}
          >
            <ArrowDownToLine size={15} />
          </a>
        </div>
      </div>
      <ErrorNotice error={error} />
      <pre
        ref={region}
        className={"log-output " + (stream === "stderr" ? "stderr" : "")}
        tabIndex={0}
        aria-label={stream + " 日志"}
        onScroll={() => {
          const el = region.current;
          if (el && el.scrollHeight - el.scrollTop - el.clientHeight > 50)
            setFollow(false);
        }}
      >
        {content ? (
          lines.map((line, i) => (
            <div className="log-line" key={i}>
              <span className="line-number" aria-hidden="true">
                {i + 1}
              </span>
              <span>{line || " "}</span>
            </div>
          ))
        ) : (
          <span className="log-empty">
            {stream === "stderr" ? "暂无标准错误输出" : "等待容器输出日志…"}
          </span>
        )}
      </pre>
      <div className="log-bottom">
        <span>
          <span className="health-dot good" />{" "}
          {error ? "读取中断" : "每 1.5 秒更新"} · UTF-8
        </span>
        <button className="text-button" onClick={() => setFollow(true)}>
          跳到最新 <ArrowDown size={12} />
        </button>
      </div>
    </section>
  );
}
export function RunPage() {
  const { id } = useParams();
  const query = useData<Run>("/runs/" + id, 2000);
  const run = query.data;
  const metrics = useData<{ events: any[] }>("/runs/" + id + "/metrics", 2000);
  const [tab, setTab] = useState("training"),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [confirm, setConfirm] = useState(false),
    [version, setVersion] = useState(""),
    [promoted, setPromoted] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (confirm) dialog.current?.showModal();
    else dialog.current?.close();
  }, [confirm]);
  async function cancel() {
    setBusy(true);
    try {
      await api("/runs/" + id + "/cancel", {});
      setConfirm(false);
      await query.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function promote() {
    setBusy(true);
    setError("");
    try {
      const a = await api<Asset>("/runs/" + id + "/promote", { version });
      setPromoted(a.name + "/" + a.version);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (!run)
    return (
      <>
        <ErrorNotice error={query.error} onRetry={query.refresh} />
        {query.loading && <Loading />}
      </>
    );
  const events = metrics.data?.events || [];
  const current = events.at(-1);
  const progress = Math.min(
    100,
    (events.length / run.assets.recipe.epochs) * 100,
  );
  return (
    <>
      <Link to="/runs" className="back-link">
        <ArrowLeft size={14} />
        训练运行
      </Link>
      <PageHeader
        eyebrow={run.id}
        title={run.training_spec.model.name}
        description={`${run.training_spec.recipe.name} · ${time(run.created_at)} 创建`}
        actions={
          <>
            {!terminal.includes(run.status) ? (
              <button
                className="button"
                onClick={() => setConfirm(true)}
                disabled={run.cancel_requested}
              >
                <Square size={14} />
                {run.cancel_requested ? "正在取消…" : "取消训练"}
              </button>
            ) : (
              <Link className="button" to={"/runs/new?from=" + id}>
                <Copy size={15} />
                基于此 Run 新建
              </Link>
            )}
            <Link
              className="button icon-only"
              aria-label="比较运行"
              to={"/runs/compare?ids=" + id}
            >
              <GitCompareArrows size={17} />
            </Link>
          </>
        }
      />
      <ErrorNotice
        error={query.error ? "状态更新中断：" + query.error : ""}
        onRetry={query.refresh}
      />
      <ErrorNotice error={error} />
      <ErrorNotice
        error={
          run.monitor_error
            ? "Docker 监控暂不可用，运行状态待确认：" + run.monitor_error
            : ""
        }
      />
      {run.failure_reason && (
        <div className="failure-banner">
          <Status value={run.status} />
          <div>
            <strong>
              {run.status === "CANCELLED" ? "训练已停止" : "这次训练未完成"}
            </strong>
            <p>{run.failure_reason}</p>
          </div>
          <button className="text-button" onClick={() => setTab("diagnostics")}>
            查看诊断 <ArrowRight size={14} />
          </button>
        </div>
      )}
      <div className="run-context">
        <Status value={run.status} />
        <span className="context-divider" />
        <AssetLink kind="dataset" {...run.training_spec.dataset} />
        <span className="muted">×</span>
        <AssetLink kind="recipe" {...run.training_spec.recipe} />
        <span className="context-divider" />
        <span className="mono">
          CPU / {run.execution_spec.resources.cpu_threads} threads
        </span>
        <span className="context-duration">
          {duration(run.started_at, run.finished_at)}
        </span>
      </div>
      <div className="tabs detail-tabs">
        {[
          ["training", "训练"],
          ["artifacts", "产物"],
          ["diagnostics", "执行与诊断"],
        ].map(([value, label]) => (
          <button
            key={value}
            onClick={() => setTab(value)}
            className={tab === value ? "selected" : ""}
          >
            {label}
            {value === "artifacts" && (
              <span className="count">{run.artifacts.length}</span>
            )}
          </button>
        ))}
      </div>
      {tab === "training" && (
        <>
          <div className="training-metrics">
            <Metric
              label="测试准确率"
              value={percent(
                run.metrics?.test_accuracy ?? current?.test_accuracy,
              )}
              detail="完整测试集 · 10,000 样本"
            />
            <Metric
              label="训练损失"
              value={
                (run.metrics?.final_train_loss ?? current?.train_loss)?.toFixed(
                  4,
                ) || "—"
              }
              detail="Cross entropy / 每轮平均"
            />
            <Metric
              label="训练进度"
              value={
                <>
                  {events.length}
                  <span className="metric-denominator">
                    {" "}
                    / {run.assets.recipe.epochs}
                  </span>
                </>
              }
              detail={
                <span className="mini-progress">
                  <i style={{ width: progress + "%" }} />
                </span>
              }
            />
            <Metric
              label="权重验证"
              value={run.metadata.trained_model_hash ? "已更新" : "待验证"}
              detail={
                run.metadata.trained_model_hash
                  ? "初始与最终 state_dict hash 不同"
                  : "训练结束后计算 SHA-256"
              }
            />
          </div>
          <div className="curve-heading">
            <SectionHeader
              title="学习曲线"
              aside={
                <span className="muted text-small">
                  {run.assets.recipe.optimizer.name} · lr{" "}
                  {run.assets.recipe.optimizer.params.lr}
                </span>
              }
            />
          </div>
          <ErrorNotice error={metrics.error} />
          <LossChart events={events} />
          <LogViewer id={run.id} />
        </>
      )}
      {tab === "artifacts" && (
        <>
          <SectionHeader
            title="训练输出"
            aside={
              <span className="muted text-small">由容器生成，平台持久保存</span>
            }
          />
          {run.artifacts.length ? (
            <div className="artifact-list">
              {[
                ...run.artifacts,
                { name: "run.json", size: 0, sha256: "" },
              ].map((a) => (
                <div className="artifact-row" key={a.name}>
                  <FileCode2 size={19} />
                  <div>
                    <strong className="mono">{a.name}</strong>
                    <span>
                      {a.sha256 ? <ShortId value={a.sha256} /> : "完整运行记录"}
                    </span>
                  </div>
                  <span className="muted mono">
                    {a.size ? (a.size / 1024).toFixed(1) + " KB" : "JSON"}
                  </span>
                  <a
                    className="button small"
                    href={`/api/runs/${id}/artifacts/${a.name}`}
                  >
                    <Download size={14} />
                    下载
                  </a>
                </div>
              ))}
            </div>
          ) : (
            <Empty
              title="等待训练产物"
              description="训练完成后，checkpoint 与指标会出现在这里。日志在训练过程中持续保存。"
            />
          )}
          {run.status === "SUCCESS" && (
            <section className="promotion">
              <div>
                <h2>让结果成为下一次训练的起点</h2>
                <p>将 checkpoint 注册为 Model 新版本，保留完整来源。</p>
              </div>
              {promoted ? (
                <p role="status">
                  <Check size={16} />
                  已注册 {promoted}
                </p>
              ) : (
                <div className="inline-form">
                  <label htmlFor="model-version" className="sr-only">
                    新模型版本
                  </label>
                  <input
                    id="model-version"
                    placeholder="新版本，例如 trained-001"
                    value={version}
                    onChange={(e) => setVersion(e.target.value)}
                  />
                  <button
                    className="button"
                    disabled={!version || busy}
                    onClick={promote}
                  >
                    注册 Model <ArrowUpRight size={15} />
                  </button>
                </div>
              )}
            </section>
          )}
        </>
      )}
      {tab === "diagnostics" && (
        <div className="diagnostic-layout">
          <div>
            <SectionHeader title="训练定义" />
            <Json value={run.training_spec} />
            <SectionHeader title="执行环境" />
            <Json value={run.execution_spec} />
            <SectionHeader title="训练证据" />
            <Json value={run.metadata} />
            <SectionHeader title="Workspace 文件快照" />
            <Json value={run.assets.workspace.files} />
          </div>
          <aside>
            <SectionHeader title="执行实例" />
            <dl className="detail-list">
              <dt>Container ID</dt>
              <dd className="mono break">{run.container_id || "尚未创建"}</dd>
              <dt>Runtime image ID</dt>
              <dd className="mono break">{run.assets.runtime.image_id}</dd>
              <dt>退出码</dt>
              <dd>{run.exit_code ?? "—"}</dd>
              <dt>开始时间</dt>
              <dd>{time(run.started_at)}</dd>
              <dt>结束时间</dt>
              <dd>{time(run.finished_at)}</dd>
            </dl>
            <SectionHeader title="状态时间线" />
            <ol className="timeline">
              <li>
                <strong>CREATED</strong>
                <span>{time(run.created_at)}</span>
              </li>
              {run.events.map((e, i) => (
                <li key={i}>
                  <strong>{e.to}</strong>
                  <span>{time(e.at)}</span>
                </li>
              ))}
            </ol>
            <a
              className="button wide"
              href={"/api/runs/" + id + "/diagnostics"}
              target="_blank"
              rel="noreferrer"
            >
              <Download size={15} />
              查看完整诊断 JSON
            </a>
            <p className="submit-note">
              包含日志、容器状态与全部配置，可供 Harness 读取。
            </p>
          </aside>
        </div>
      )}
      <dialog
        ref={dialog}
        onCancel={() => setConfirm(false)}
        onClose={() => setConfirm(false)}
      >
        <div className="dialog-heading">
          <h2>取消这次训练？</h2>
          <button
            className="icon-button"
            aria-label="关闭"
            onClick={() => setConfirm(false)}
          >
            <X size={18} />
          </button>
        </div>
        <p>停止对应的 Docker 容器。已有日志会保留；再次训练需要创建新 Run。</p>
        <div className="dialog-actions">
          <button className="button" onClick={() => setConfirm(false)}>
            继续训练
          </button>
          <button className="button danger" disabled={busy} onClick={cancel}>
            {busy ? "正在停止…" : "确认取消"}
          </button>
        </div>
      </dialog>
    </>
  );
}
export function ComparePage() {
  const [params] = useSearchParams();
  const ids = (params.get("ids") || "").split(",").filter(Boolean);
  const data = useData<Run[]>("/runs", 3000);
  const [a, setA] = useState(ids[0] || ""),
    [b, setB] = useState(ids[1] || "");
  const left = data.data?.find((r) => r.id === a),
    right = data.data?.find((r) => r.id === b);
  return (
    <>
      <Link to="/runs" className="back-link">
        <ArrowLeft size={14} />
        训练运行
      </Link>
      <PageHeader
        eyebrow="实验比较 / Compare"
        title="让差异清晰可见"
        description="并排审视训练定义、执行条件和最终结果。"
      />
      <ErrorNotice error={data.error} />
      <div className="compare-selectors">
        {[
          [a, setA, "Run A"],
          [b, setB, "Run B"],
        ].map(([value, set, label]) => (
          <label key={label as string}>
            {label as string}
            <select
              value={value as string}
              onChange={(e) => (set as (s: string) => void)(e.target.value)}
            >
              <option value="">选择训练运行</option>
              {data.data?.map((r) => (
                <option value={r.id} key={r.id}>
                  {r.id} · {r.training_spec.recipe.name}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
      {left && right ? (
        <>
          <div className="table-scroll">
            <table className="comparison-table">
              <thead>
                <tr>
                  <th>比较项</th>
                  <th>Run A</th>
                  <th>Run B</th>
                </tr>
              </thead>
              <tbody>
                {(["dataset", "model", "recipe"] as const).map((kind) => (
                  <tr
                    className={
                      JSON.stringify(left.training_spec[kind]) !==
                      JSON.stringify(right.training_spec[kind])
                        ? "different"
                        : ""
                    }
                    key={kind}
                  >
                    <th>{kind}</th>
                    <td>
                      {left.training_spec[kind].name} /{" "}
                      {left.training_spec[kind].version}
                    </td>
                    <td>
                      {right.training_spec[kind].name} /{" "}
                      {right.training_spec[kind].version}
                    </td>
                  </tr>
                ))}
                <tr
                  className={
                    JSON.stringify(left.execution_spec) !==
                    JSON.stringify(right.execution_spec)
                      ? "different"
                      : ""
                  }
                >
                  <th>ExecutionSpec</th>
                  <td colSpan={2}>
                    {JSON.stringify(left.execution_spec) ===
                    JSON.stringify(right.execution_spec)
                      ? "完全相同 · Runtime / Workspace / 资源配置"
                      : "执行环境存在差异，请查看两次 Run 的执行与诊断信息"}
                  </td>
                </tr>
                <tr>
                  <th>状态</th>
                  <td>
                    <Status value={left.status} />
                  </td>
                  <td>
                    <Status value={right.status} />
                  </td>
                </tr>
                <tr>
                  <th>Test accuracy</th>
                  <td>{percent(left.metrics?.test_accuracy)}</td>
                  <td>{percent(right.metrics?.test_accuracy)}</td>
                </tr>
                <tr>
                  <th>Final train loss</th>
                  <td>{left.metrics?.final_train_loss.toFixed(5) || "—"}</td>
                  <td>{right.metrics?.final_train_loss.toFixed(5) || "—"}</td>
                </tr>
                <tr>
                  <th>执行耗时</th>
                  <td>{duration(left.started_at, left.finished_at)}</td>
                  <td>{duration(right.started_at, right.finished_at)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <SectionHeader title="训练损失对比" />
          <LossChart
            events={left.metrics?.history || []}
            comparison={right.metrics?.history || []}
          />
          <div className="compare-links">
            <Link className="text-link" to={"/runs/" + a}>
              查看 Run A <ArrowRight size={14} />
            </Link>
            <Link className="text-link" to={"/runs/" + b}>
              查看 Run B <ArrowRight size={14} />
            </Link>
          </div>
        </>
      ) : (
        <Empty
          title="选择两个训练 Run"
          description="使用相同数据集和模型，比较不同 Recipe 的学习过程。"
        />
      )}
    </>
  );
}
