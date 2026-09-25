import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowDownToLine,
  ArrowUpFromLine,
  ArrowUpRight,
  Check,
  Cloud,
  RefreshCw,
  Settings2,
} from "lucide-react";
import { api, useData } from "./api";
import type { Asset } from "./types";
import {
  Empty,
  ErrorNotice,
  Loading,
  PageHeader,
  SectionHeader,
  time,
} from "./ui";

type HubConfig = {
  enabled: boolean;
  endpoint: string;
  namespace: string;
  token_configured: boolean;
};
type Settings = {
  hub: HubConfig;
  aim: { enabled: boolean };
  tracking: { error: string | null; tracked_runs: number };
};
type Repository = {
  id: string;
  sha: string | null;
  private: boolean;
  kind: string;
};
type Transfer = {
  id: string;
  direction: string;
  status: string;
  created_at: string;
  error: string | null;
  result: any;
  request: any;
};
const transferLabels: Record<string, string> = {
  CREATED: "等待传输",
  RUNNING: "传输中",
  SUCCESS: "已完成",
  FAILED: "失败",
};

export function HubPage() {
  const settings = useData<Settings>("/integrations");
  const status = useData<
    HubConfig & { status: string; account?: string; error?: string }
  >("/hub/status", 15000);
  const transfers = useData<Transfer[]>("/hub/transfers", 2000);
  const [kind, setKind] = useState("model"),
    [repositories, setRepositories] = useState<Repository[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]),
    [search, setSearch] = useState("");
  const [configOpen, setConfigOpen] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [enabled, setEnabled] = useState(false),
    [aim, setAim] = useState(true),
    [endpoint, setEndpoint] = useState("");
  const [namespace, setNamespace] = useState(""),
    [token, setToken] = useState("");
  const [busy, setBusy] = useState(""),
    [reposLoading, setReposLoading] = useState(false),
    [reload, setReload] = useState(0);
  const [assetId, setAssetId] = useState(""),
    [publishRepo, setPublishRepo] = useState(""),
    [isPrivate, setIsPrivate] = useState(true);
  const [importRepo, setImportRepo] = useState(""),
    [revision, setRevision] = useState("main");
  const [name, setName] = useState(""),
    [version, setVersion] = useState("hub-" + Date.now().toString(36));
  useEffect(() => {
    if (!settings.data) return;
    setEnabled(settings.data.hub.enabled);
    setEndpoint(settings.data.hub.endpoint);
    setNamespace(settings.data.hub.namespace);
    setAim(settings.data.aim.enabled);
  }, [settings.data]);
  useEffect(() => {
    let current = true;
    setAssetId("");
    setRepositories([]);
    setError("");
    api<Asset[]>("/assets/" + kind)
      .then((data) => {
        if (current)
          setAssets(
            data.filter((a) =>
              String(a.metadata.format || "").startsWith("huggingface."),
            ),
          );
      })
      .catch((e) => {
        if (current) setError(e.message);
      });
    if (settings.data?.hub.enabled) {
      setReposLoading(true);
      api<Repository[]>("/hub/repositories?kind=" + kind)
        .then((data) => {
          if (current) setRepositories(data);
        })
        .catch((e) => {
          if (current) setError(e.message);
        })
        .finally(() => {
          if (current) setReposLoading(false);
        });
    }
    return () => {
      current = false;
    };
  }, [kind, settings.data?.hub.enabled, reload]);
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy("settings");
    setError("");
    setNotice("");
    try {
      await api("/integrations", {
        hub: { enabled, endpoint, namespace, token: token || null },
        aim: { enabled: aim },
      });
      setToken("");
      await settings.refresh();
      await status.refresh();
      setReload((r) => r + 1);
      setNotice("集成设置已保存。");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function transfer(direction: string, payload: any) {
    setBusy(direction);
    setError("");
    setNotice("");
    try {
      const result = await api<Transfer>("/hub/" + direction, payload);
      setNotice("传输已排队 · " + result.id);
      await transfers.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  const online = status.data?.status === "CONNECTED";
  return (
    <>
      <PageHeader
        eyebrow="资产中心 / Central storage"
        title="让资产拥有共同的归处"
        description="模型与数据集集中保存；每次训练仍使用一个确定、可验证的版本。"
        actions={
          <button
            className="button"
            onClick={() => setConfigOpen(!configOpen)}
            aria-expanded={configOpen}
          >
            <Settings2 size={16} />
            连接设置
          </button>
        }
      />
      <ErrorNotice error={error || settings.error || status.error} />
      {notice && (
        <div className="integration-notice" role="status">
          <Check size={16} />
          {notice}
        </div>
      )}
      <div className="integration-connection">
        <div className="asset-icon">
          <Cloud size={24} />
        </div>
        <div>
          <strong>KohakuHub</strong>
          <p>{settings.data?.hub.endpoint || "正在读取连接设置"}</p>
        </div>
        <span className={"connection-state " + (online ? "connected" : "")}>
          {online
            ? "已连接 · " + (status.data?.account || "匿名只读")
            : status.data?.status === "DISABLED"
              ? "未启用 · 本地存储"
              : "暂不可用"}
        </span>
      </div>
      {configOpen && (
        <form className="integration-settings" onSubmit={save}>
          <SectionHeader title="连接与实验记录" />
          <div className="integration-fields">
            <label>
              Hub 地址
              <input
                type="url"
                required
                value={endpoint}
                onChange={(e) => setEndpoint(e.target.value)}
              />
            </label>
            <label>
              默认命名空间
              <input
                required
                value={namespace}
                pattern="[A-Za-z0-9_-]+"
                onChange={(e) => setNamespace(e.target.value)}
              />
            </label>
            <label>
              访问令牌
              <input
                type="password"
                autoComplete="new-password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder={
                  settings.data?.hub.token_configured
                    ? "已配置 · 留空保留现有令牌"
                    : "输入 Hub 访问令牌"
                }
              />
            </label>
          </div>
          <div className="integration-settings-actions">
            <label className="check-control">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
              />
              启用中心存储
            </label>
            <label className="check-control">
              <input
                type="checkbox"
                checked={aim}
                onChange={(e) => setAim(e.target.checked)}
              />
              使用 Aim 记录实验
            </label>
            <button className="button primary" disabled={!!busy}>
              {busy === "settings" ? "保存中…" : "保存并检查连接"}
            </button>
          </div>
          <p className="muted">
            令牌仅保存在后端。关闭中心存储后，本地资产和训练记录仍可使用。
          </p>
        </form>
      )}
      {!settings.data?.hub.enabled ? (
        <Empty
          title="按需连接中心存储"
          description="启用后，可以发布 HF 资产，或将 Hub 中的固定版本导入工作空间。"
          action={
            <button className="button" onClick={() => setConfigOpen(true)}>
              配置连接
            </button>
          }
        />
      ) : (
        <>
          {!online && (
            <ErrorNotice
              error={
                status.data?.error || "正在检查连接；传输前请确认服务可用。"
              }
              onRetry={status.refresh}
            />
          )}
          <div className="integration-toolbar">
            <div className="segmented" aria-label="资产类型">
              {[
                ["model", "模型"],
                ["dataset", "数据集"],
              ].map(([value, label]) => (
                <button
                  key={value}
                  className={kind === value ? "selected" : ""}
                  aria-pressed={kind === value}
                  onClick={() => setKind(value)}
                >
                  {label}
                </button>
              ))}
            </div>
            <label className="sr-only" htmlFor="hub-search">
              搜索仓库
            </label>
            <input
              id="hub-search"
              placeholder="搜索远端仓库"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <button
              className="button"
              onClick={() => {
                setReload((r) => r + 1);
                void status.refresh();
              }}
            >
              <RefreshCw size={14} />
              刷新
            </button>
          </div>
          <div className="hub-repositories">
            {reposLoading ? (
              <Loading />
            ) : repositories.filter((r) => r.id.includes(search)).length ? (
              repositories
                .filter((r) => r.id.includes(search))
                .map((repo) => (
                  <button
                    className="hub-repository"
                    key={repo.id}
                    onClick={() => {
                      setImportRepo(repo.id);
                      setRevision(repo.sha || "main");
                      setName(repo.id.split("/").pop() || "");
                      document
                        .getElementById("hub-import-title")
                        ?.scrollIntoView({
                          block: "center",
                          behavior: "smooth",
                        });
                    }}
                  >
                    <div>
                      <strong>{repo.id}</strong>
                      <span className="mono">
                        {repo.sha?.slice(0, 12) || "尚无提交"}
                      </span>
                    </div>
                    <span>{repo.private ? "私有" : "公开"}</span>
                    <ArrowDownToLine size={16} />
                  </button>
                ))
            ) : (
              <Empty
                title="没有匹配的仓库"
                description="可以从下方发布本地 HF 资产，或修改搜索条件。"
              />
            )}
          </div>
          <div className="hub-operations">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const asset = assets.find((a) => a.id === assetId);
                if (asset)
                  void transfer("publish", {
                    kind,
                    name: asset.name,
                    version: asset.version,
                    repo_id: publishRepo,
                    private: isPrivate,
                  });
              }}
            >
              <SectionHeader title="发布资产" />
              <p className="muted">
                将完整的 HF 文件和训练资产清单保存到中心。
              </p>
              <label>
                本地资产
                <select
                  required
                  value={assetId}
                  onChange={(e) => {
                    setAssetId(e.target.value);
                    const a = assets.find((a) => a.id === e.target.value);
                    if (a) setPublishRepo(namespace + "/" + a.name);
                  }}
                >
                  <option value="">选择已注册资产</option>
                  {assets.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name} / {a.version}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                目标仓库
                <input
                  required
                  placeholder="namespace/repository"
                  pattern="[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+"
                  value={publishRepo}
                  onChange={(e) => setPublishRepo(e.target.value)}
                />
              </label>
              <label className="check-control">
                <input
                  type="checkbox"
                  checked={isPrivate}
                  onChange={(e) => setIsPrivate(e.target.checked)}
                />
                新建为私有仓库
              </label>
              <button className="button primary" disabled={!!busy || !online}>
                <ArrowUpFromLine size={15} />
                发布到 Hub
              </button>
            </form>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void transfer("import", {
                  kind,
                  repo_id: importRepo,
                  revision,
                  name,
                  version,
                });
              }}
            >
              <h2 id="hub-import-title">导入固定版本</h2>
              <p className="muted">
                读取 ninna-asset.json，校验文件后注册为新的本地资产。
              </p>
              <label>
                远端仓库
                <input
                  required
                  value={importRepo}
                  placeholder="namespace/repository"
                  pattern="[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+"
                  onChange={(e) => setImportRepo(e.target.value)}
                />
              </label>
              <label>
                Commit / branch
                <input
                  required
                  value={revision}
                  onChange={(e) => setRevision(e.target.value)}
                />
              </label>
              <div className="integration-fields compact">
                <label>
                  本地名称
                  <input
                    required
                    value={name}
                    pattern="[A-Za-z0-9_.-]+"
                    onChange={(e) => setName(e.target.value)}
                  />
                </label>
                <label>
                  新版本
                  <input
                    required
                    value={version}
                    pattern="[A-Za-z0-9_.-]+"
                    onChange={(e) => setVersion(e.target.value)}
                  />
                </label>
              </div>
              <button className="button" disabled={!!busy || !online}>
                <ArrowDownToLine size={15} />
                下载并注册
              </button>
            </form>
          </div>
        </>
      )}
      <SectionHeader title="传输记录" aside="独立传输记录" />
      <div className="transfer-list">
        {transfers.data?.length ? (
          transfers.data.map((job) => (
            <div
              className="transfer-row"
              key={job.id}
              data-transfer-id={job.id}
            >
              <span className="transfer-direction">
                {job.direction === "publish" ? (
                  <ArrowUpFromLine size={17} />
                ) : (
                  <ArrowDownToLine size={17} />
                )}
              </span>
              <div>
                <strong>{job.request.repo_id}</strong>
                <p>
                  {job.direction === "publish" ? "发布" : "导入"} ·{" "}
                  {job.request.name} / {job.request.version} ·{" "}
                  {time(job.created_at)}
                </p>
                {job.result && (
                  <p className="mono">commit {job.result.revision}</p>
                )}
                {job.error && <p className="transfer-error">{job.error}</p>}
              </div>
              <span className={"status status-" + job.status.toLowerCase()}>
                {transferLabels[job.status] || job.status}
              </span>
              {job.result?.asset_id && (
                <Link
                  className="text-link"
                  to={
                    "/assets/" +
                    job.request.kind +
                    "?name=" +
                    encodeURIComponent(job.request.name) +
                    "&version=" +
                    encodeURIComponent(job.request.version)
                  }
                >
                  查看资产
                  <ArrowUpRight size={13} />
                </Link>
              )}
              {job.status === "FAILED" && settings.data?.hub.enabled && (
                <button
                  className="text-button"
                  disabled={!!busy}
                  onClick={() =>
                    void transfer(
                      job.direction === "publish" ? "publish" : "import",
                      job.request,
                    )
                  }
                >
                  重试
                </button>
              )}
            </div>
          ))
        ) : (
          <Empty
            title="还没有传输记录"
            description="发起一次发布或导入后，可以在这里查看结果和固定 commit。"
          />
        )}
      </div>
    </>
  );
}
