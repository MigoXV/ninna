import { useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { api, useData } from "./api";
import { ArrowRight, LoaderCircle } from "lucide-react";
import { ObjectEditor, ObjectRow, ObjectSelect } from "./object-row";
import { Empty, ErrorNotice, Json, Loading, PageHeader } from "./ui";
import "./work.css";

type RecordValue = Record<string, any>;
const requestId = () => {
  // LAN installations may use HTTP, where randomUUID is unavailable.
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join(
    "",
  );
};
const reference = (value: string) => {
  const [name, version] = value.split("/");
  return { name, version };
};
const key = (value: RecordValue) => `${value.name}/${value.version}`;
const states: Record<string, string> = {
  QUEUED: "等待执行",
  RUNNING: "执行中",
  SUCCESS: "完成",
  FAILED: "失败",
  CANCELLED: "已取消",
  DOWNLOADED: "已下载",
  MISSING: "本地文件缺失",
  CORRUPT: "校验失败",
  DRAFT: "环境草稿",
  ACTIVE: "进行中",
  WAITING: "等待处理",
  COMPLETED: "已完成",
  ARCHIVED: "已归档",
  READY: "可执行",
  CHECKING: "检查中",
  BLOCKED: "需要处理",
  PUBLISHED: "已发布",
};
function State({ value }: { value: string }) {
  return <span className="work-state">{states[value] || value}</span>;
}
function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="work-field">
      <span>{label}</span>
      {children}
    </label>
  );
}
function useAction() {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return { error, busy, act };
}
function Jobs({ owner }: { owner?: string }) {
  const jobs = useData<RecordValue[]>("/v2/jobs", 3000);
  const [selected, setSelected] = useState("");
  const logs = useData<RecordValue>(
    selected ? `/v2/jobs/${selected}/logs` : "/v2/capabilities",
    selected ? 3000 : 0,
  );
  const action = useAction();
  const values =
    jobs.data?.filter(
      (j) =>
        !owner ||
        j.payload.owner_id === owner ||
        j.payload.work_item_id === owner,
    ) || [];
  return (
    <section className="work-section">
      <h2>后台操作</h2>
      <ErrorNotice error={jobs.error || action.error} />
      <div
        className="work-list work-jobs"
        tabIndex={0}
        role="region"
        aria-label="后台操作记录"
      >
        {values.slice(0, 30).map((job) => (
          <div className="work-row" key={job.id}>
            <div>
              <strong>
                {{
                  acquire: "获取资产",
                  publish_asset: "发布资产",
                  initialize: "准备工作区",
                  command: "执行命令",
                  publish_environment: "发布环境",
                  check_plan: "检查训练方案",
                  run: "提交运行",
                }[job.operation as string] || job.operation}
              </strong>
              <span className="muted">
                {job.error ||
                  job.result?.run_id ||
                  job.result?.name ||
                  job.payload.name ||
                  job.id}
              </span>
            </div>
            <State value={job.status} />
            {job.operation === "command" && (
              <button className="button" onClick={() => setSelected(job.id)}>
                日志
              </button>
            )}
            {job.status === "QUEUED" ||
            (job.operation === "command" && job.status === "RUNNING") ? (
              <button
                className="button"
                disabled={action.busy}
                onClick={() =>
                  void action.act(async () => {
                    await api(`/v2/jobs/${job.id}/cancel`, {
                      request_id: requestId(),
                    });
                    await jobs.refresh();
                  })
                }
              >
                取消
              </button>
            ) : null}
          </div>
        ))}
      </div>
      {!values.length && <p className="muted">暂无后台操作。</p>}
      {selected && (
        <pre
          className="log-content"
          tabIndex={0}
          role="region"
          aria-label="后台操作日志"
        >
          {logs.data?.content || "暂无输出"}
        </pre>
      )}
    </section>
  );
}

export function SourcesPage() {
  const sources = useData<RecordValue[]>("/v2/sources");
  const action = useAction();
  const [name, setName] = useState("");
  const [endpoint, setEndpoint] = useState("");
  const [tokenEnv, setTokenEnv] = useState("");
  const [checks, setChecks] = useState<Record<string, string>>({});
  return (
    <div className="work-page-v2">
      <PageHeader
        title="托管平台"
        eyebrow="设置"
        description="同时连接内网平台与 Hugging Face。已下载资产可以离线使用。"
      />
      <ErrorNotice error={sources.error || action.error} />
      <div
        className="work-list"
        tabIndex={0}
        role="region"
        aria-label="托管平台列表"
      >
        {sources.data?.map((source) => (
          <div className="work-row" key={source.id}>
            <div>
              <strong>{source.name}</strong>
              <span className="muted">{source.endpoint}</span>
            </div>
            <span>
              {checks[source.id] || (source.enabled ? "已配置" : "已停用")}
            </span>
            <button
              className="button"
              disabled={action.busy}
              onClick={() =>
                void action.act(async () => {
                  const result = await api(`/v2/sources/${source.id}/status`);
                  setChecks({
                    ...checks,
                    [source.id]:
                      result.status === "CONNECTED"
                        ? "连接正常"
                        : result.status === "DISABLED"
                          ? "已停用"
                          : "连接失败",
                  });
                })
              }
            >
              检查连接
            </button>
            <button
              className="button"
              disabled={action.busy}
              onClick={() =>
                void action.act(async () => {
                  await api(`/v2/sources/${source.id}`, {
                    request_id: requestId(),
                    name: source.name,
                    endpoint: source.endpoint,
                    protocol: source.protocol,
                    token_env: source.token_env,
                    enabled: !source.enabled,
                    expected_version: source.version,
                  });
                  await sources.refresh();
                })
              }
            >
              {source.enabled ? "停用" : "启用"}
            </button>
          </div>
        ))}
      </div>
      <form
        className="work-section work-form"
        onSubmit={(e) => {
          e.preventDefault();
          void action.act(async () => {
            await api("/v2/sources", {
              name,
              endpoint,
              token_env: tokenEnv || null,
              request_id: requestId(),
            });
            setName("");
            setEndpoint("");
            await sources.refresh();
          });
        }}
      >
        <h2>添加托管平台</h2>
        <Field label="名称">
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="公司内网 / Hugging Face"
          />
        </Field>
        <Field label="平台地址">
          <input
            required
            type="url"
            value={endpoint}
            onChange={(e) => setEndpoint(e.target.value)}
            placeholder="https://huggingface.co"
          />
        </Field>
        <Field label="凭据变量名称（可选）">
          <input
            value={tokenEnv}
            onChange={(e) => setTokenEnv(e.target.value)}
            placeholder="NINNA_HF_TOKEN"
          />
        </Field>
        <p className="muted">
          填写平台部署环境中的变量名称，令牌值不进入对话或训练环境。
        </p>
        <button className="button primary" disabled={action.busy}>
          添加平台
        </button>
      </form>
    </div>
  );
}

export function AssetLibrary() {
  const assets = useData<RecordValue[]>("/v2/assets", 4000);
  const sources = useData<RecordValue[]>("/v2/sources");
  const action = useAction();
  const [kind, setKind] = useState("model");
  const [source, setSource] = useState("");
  const [query, setQuery] = useState("");
  const [remote, setRemote] = useState<RecordValue[]>([]);
  const [offset, setOffset] = useState<number | null>(0);
  const [name, setName] = useState("");
  const [location, setLocation] = useState("");
  const [revision, setRevision] = useState("main");
  const [method, setMethod] = useState("platform");
  async function acquire(repo?: string) {
    await api("/v2/assets/acquire", {
      request_id: requestId(),
      kind,
      name: repo?.split("/").pop() || name,
      ...(method === "platform" || repo
        ? { source_id: source, repo_id: repo || location, revision }
        : method === "url"
          ? { url: location }
          : { local_path: location }),
    });
    await assets.refresh();
  }
  return (
    <div className="work-page-v2">
      <PageHeader
        title="模型与数据"
        eyebrow="资产"
        description="查看来源和本地副本。先准备资产，再开始训练。"
      />
      <ErrorNotice error={assets.error || sources.error || action.error} />
      <div className="work-toolbar">
        <Field label="类型">
          <select
            value={kind}
            onChange={(e) => {
              setKind(e.target.value);
              setRemote([]);
              setOffset(0);
            }}
          >
            <option value="model">模型</option>
            <option value="dataset">数据集</option>
          </select>
        </Field>
        <Field label="搜索本地资产">
          <input value={query} onChange={(e) => setQuery(e.target.value)} />
        </Field>
        <Link to="/settings/sources">管理托管平台</Link>
      </div>
      <div
        className="work-list"
        tabIndex={0}
        role="region"
        aria-label="本地资产列表"
      >
        {assets.data
          ?.filter((a) => a.kind === kind && a.name.includes(query))
          .map((asset) => (
            <div className="work-row" key={asset.id}>
              <div>
                <Link to={`/library/${asset.id}`}>
                  <strong>{asset.name}</strong>
                </Link>
                <span className="muted">
                  {sources.data?.find((s) => s.id === asset.source_id)?.name ||
                    "本地导入"}{" "}
                  · {asset.revision?.slice(0, 12)}
                </span>
              </div>
              <State value={asset.local_status} />
              <span className="muted">训练兼容性按方案检查</span>
            </div>
          ))}
      </div>
      {assets.loading ? (
        <Loading />
      ) : !assets.data?.some((a) => a.kind === kind) ? (
        <Empty
          title="还没有本地资产"
          description="从下方托管平台下载，或导入已有文件。"
        />
      ) : null}
      <section className="work-section">
        <h2>查找远端资产</h2>
        <div className="work-toolbar">
          <Field label="托管平台">
            <select
              value={source}
              onChange={(e) => {
                setSource(e.target.value);
                setRemote([]);
                setOffset(0);
              }}
            >
              <option value="">选择平台</option>
              {sources.data
                ?.filter((s) => s.enabled)
                .map((s) => (
                  <option value={s.id} key={s.id}>
                    {s.name}
                  </option>
                ))}
            </select>
          </Field>
          <button
            className="button"
            disabled={!source || action.busy}
            onClick={() =>
              void action.act(async () => {
                const result = await api(
                  `/v2/sources/${source}/assets?kind=${kind}&q=${encodeURIComponent(query)}`,
                );
                setRemote(result.items);
                setOffset(result.next_offset);
              })
            }
          >
            搜索远端
          </button>
        </div>
        <div
          className="work-list"
          tabIndex={0}
          role="region"
          aria-label="远端搜索结果"
        >
          {remote.map((repo) => (
            <div className="work-row" key={repo.repo_id}>
              <div>
                <strong>{repo.repo_id}</strong>
                <span className="muted">
                  {repo.local_revisions.length ? "已有本地版本" : "尚未下载"}
                </span>
              </div>
              <button
                className="button"
                disabled={action.busy}
                onClick={() => void action.act(() => acquire(repo.repo_id))}
              >
                下载
              </button>
            </div>
          ))}
        </div>
        {remote.length > 0 && offset !== null && (
          <button
            className="button"
            disabled={action.busy}
            onClick={() =>
              void action.act(async () => {
                const result = await api(
                  `/v2/sources/${source}/assets?kind=${kind}&q=${encodeURIComponent(query)}&offset=${offset}`,
                );
                setRemote([...remote, ...result.items]);
                setOffset(result.next_offset);
              })
            }
          >
            加载更多
          </button>
        )}
      </section>
      <form
        className="work-section work-form"
        onSubmit={(e) => {
          e.preventDefault();
          void action.act(() => acquire());
        }}
      >
        <h2>获取指定资产</h2>
        <Field label="获取方式">
          <select value={method} onChange={(e) => setMethod(e.target.value)}>
            <option value="platform">托管平台仓库</option>
            <option value="url">HTTP(S) 文件</option>
            <option value="local">Ninna 主机目录或文件</option>
          </select>
        </Field>
        <Field label="名称">
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        <Field
          label={
            method === "platform"
              ? "仓库标识"
              : method === "url"
                ? "下载地址"
                : "Ninna 主机路径"
          }
        >
          <input
            required
            value={location}
            onChange={(e) => setLocation(e.target.value)}
          />
        </Field>
        {method === "platform" && (
          <Field label="版本或分支">
            <input
              required
              value={revision}
              onChange={(e) => setRevision(e.target.value)}
            />
          </Field>
        )}
        <button
          className="button primary"
          disabled={action.busy || (method === "platform" && !source)}
        >
          获取到本地
        </button>
        <p className="muted">
          Codex 机器上的文件可用 ninna upload 流式上传，无需共享目录。
        </p>
      </form>
      <Jobs />
    </div>
  );
}

export function AssetRevisionPage() {
  const { assetId } = useParams();
  const asset = useData<RecordValue>(`/v2/assets/${assetId}`);
  const sources = useData<RecordValue[]>("/v2/sources");
  const action = useAction();
  const [metadata, setMetadata] = useState("{}");
  const [source, setSource] = useState("");
  const [repo, setRepo] = useState("");
  return (
    <div className="work-page-v2">
      <Link to="/library">返回资产</Link>
      <PageHeader
        title={asset.data?.name || "资产详情"}
        eyebrow="固定版本"
        description="文件已下载与适合当前训练是两项独立检查。"
      />
      <ErrorNotice error={asset.error || action.error} />
      {asset.data && (
        <>
          <State value={asset.data.local_status} />
          <details>
            <summary>来源与文件清单</summary>
            <Json value={asset.data} />
          </details>
          <button
            className="button"
            disabled={action.busy}
            onClick={() =>
              void action.act(async () => {
                const result = await api(`/v2/assets/${assetId}?verify=true`);
                if (result.local_status !== "DOWNLOADED")
                  throw new Error(states[result.local_status]);
                await asset.refresh();
              })
            }
          >
            校验本地文件
          </button>
          <form
            className="work-section work-form"
            onSubmit={(e) => {
              e.preventDefault();
              void action.act(async () => {
                await api(`/v2/assets/${assetId}/binding`, {
                  request_id: requestId(),
                  metadata: JSON.parse(metadata),
                });
              });
            }}
          >
            <h2>训练加载信息</h2>
            <p className="muted">
              数据集填写 train_split、test_split；模型填写
              architecture、initialization、parameter_count。Codex
              可以根据文件补充这些信息。
            </p>
            <Field label="元数据 JSON">
              <textarea
                rows={6}
                value={metadata}
                onChange={(e) => setMetadata(e.target.value)}
              />
            </Field>
            <button className="button" disabled={action.busy}>
              保存加载信息
            </button>
          </form>
          <form
            className="work-section work-form"
            onSubmit={(e) => {
              e.preventDefault();
              void action.act(async () => {
                await api(`/v2/assets/${assetId}/publish`, {
                  request_id: requestId(),
                  source_id: source,
                  repo_id: repo,
                  private: true,
                });
              });
            }}
          >
            <h2>发布到托管平台</h2>
            <Field label="目标平台">
              <select
                required
                value={source}
                onChange={(e) => setSource(e.target.value)}
              >
                <option value="">选择平台</option>
                {sources.data
                  ?.filter((s) => s.enabled)
                  .map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
              </select>
            </Field>
            <Field label="目标仓库">
              <input
                required
                value={repo}
                onChange={(e) => setRepo(e.target.value)}
                placeholder="namespace/repository"
              />
            </Field>
            <button className="button" disabled={action.busy}>
              发布为私有仓库
            </button>
          </form>
        </>
      )}
      <Jobs />
    </div>
  );
}

export function EnvironmentsPage() {
  const environments = useData<RecordValue[]>("/v2/environments", 4000);
  const images = useData<RecordValue[]>("/assets/image");
  const spaces = useData<RecordValue[]>("/assets/workspace");
  const action = useAction();
  const [name, setName] = useState("");
  const [image, setImage] = useState("");
  const [workspace, setWorkspace] = useState("");
  return (
    <div className="work-page-v2">
      <PageHeader
        title="训练环境"
        eyebrow="准备一次，重复使用"
        description="发布准备好的环境基线；每个工作任务拥有独立文件和状态。"
      />
      <ErrorNotice
        error={
          environments.error || images.error || spaces.error || action.error
        }
      />
      <div
        className="work-list"
        tabIndex={0}
        role="region"
        aria-label="训练环境列表"
      >
        {environments.data?.map((env) => (
          <div className="work-row" key={env.id}>
            <div>
              <Link to={`/environments/${env.id}`}>
                <strong>{env.name}</strong>
              </Link>
              <span className="muted">
                {env.revisions.length} 个已发布版本 ·{" "}
                {env.ready ? "工作区已准备" : "等待准备"}
              </span>
            </div>
            <State value={env.status} />
          </div>
        ))}
      </div>
      <form
        className="work-section work-form"
        onSubmit={(e) => {
          e.preventDefault();
          void action.act(async () => {
            const ws = spaces.data?.find((s) => s.name === workspace);
            await api("/v2/environments", {
              request_id: requestId(),
              name,
              image_ref: reference(image),
              workspace_name: workspace || null,
              framework: ws?.metadata.framework || null,
            });
            setName("");
            await environments.refresh();
          });
        }}
      >
        <h2>准备新环境</h2>
        <Field label="环境名称">
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="语音识别训练"
          />
        </Field>
        <Field label="基础镜像">
          <select
            required
            value={image}
            onChange={(e) => setImage(e.target.value)}
          >
            <option value="">选择已登记镜像</option>
            {images.data?.map((i) => (
              <option key={i.id} value={key(i)}>
                {key(i)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="初始代码">
          <select
            value={workspace}
            onChange={(e) => setWorkspace(e.target.value)}
          >
            <option value="">空工作区，由 Codex 准备</option>
            {spaces.data
              ?.filter((w) => !w.name.startsWith("prepared-"))
              .map((w) => (
                <option key={w.id} value={w.name}>
                  {w.name}
                </option>
              ))}
          </select>
        </Field>
        <button className="button primary" disabled={action.busy}>
          创建环境草稿
        </button>
      </form>
      <details className="work-section">
        <summary>高级环境资源</summary>
        <div className="work-toolbar">
          <Link to="/assets/image">镜像管理</Link>
          <Link to="/assets/framework">框架能力</Link>
          <Link to="/assets/recipe">训练方案模板</Link>
        </div>
      </details>
      <Jobs />
    </div>
  );
}

function WorkspaceTools({ owner }: { owner: string }) {
  const files = useData<RecordValue>(`/v2/workspaces/${owner}/files`);
  const action = useAction();
  const [path, setPath] = useState("");
  const [content, setContent] = useState("");
  const [sha, setSha] = useState<string | null>(null);
  const [command, setCommand] = useState("");
  return (
    <details className="work-section">
      <summary>工作区文件与准备命令</summary>
      <ErrorNotice error={files.error || action.error} />
      <div className="work-form">
        <Field label="选择文件">
          <select
            value={path}
            onChange={(e) => {
              setPath(e.target.value);
              setContent("");
              setSha(null);
              if (e.target.value)
                void action.act(async () => {
                  const value = await api(
                    `/v2/workspaces/${owner}/files?path=${encodeURIComponent(e.target.value)}`,
                  );
                  setContent(value.content);
                  setSha(value.sha256);
                });
            }}
          >
            <option value="">新建文件</option>
            {files.data?.files.map((file: string) => (
              <option key={file}>{file}</option>
            ))}
          </select>
        </Field>
        <Field label="相对路径">
          <input
            value={path}
            onChange={(e) => {
              setPath(e.target.value);
              setSha(null);
            }}
          />
        </Field>
        <Field label="文件内容">
          <textarea
            rows={12}
            value={content}
            onChange={(e) => setContent(e.target.value)}
          />
        </Field>
        <button
          className="button"
          disabled={!path || action.busy}
          onClick={() =>
            void action.act(async () => {
              const value = await api(`/v2/workspaces/${owner}/files`, {
                request_id: requestId(),
                path,
                content,
                expected_sha256: sha,
              });
              setSha(value.sha256);
              await files.refresh();
            })
          }
        >
          保存文件
        </button>
        <Field label="准备命令（在任务容器内执行）">
          <textarea
            rows={3}
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            placeholder="python --version"
          />
        </Field>
        <button
          className="button"
          disabled={!command || action.busy}
          onClick={() =>
            void action.act(async () => {
              await api(`/v2/workspaces/${owner}/commands`, {
                request_id: requestId(),
                argv: ["bash", "-lc", command],
              });
            })
          }
        >
          执行命令
        </button>
        <div className="work-toolbar">
          {["start", "stop"].map((state) => (
            <button
              className="button"
              key={state}
              disabled={action.busy}
              onClick={() =>
                void action.act(async () => {
                  await api(`/v2/workspaces/${owner}/${state}`, {
                    request_id: requestId(),
                  });
                })
              }
            >
              {state === "start" ? "启动工作区" : "停止工作区"}
            </button>
          ))}
        </div>
      </div>
    </details>
  );
}

export function EnvironmentPage() {
  const { environmentId = "" } = useParams();
  const envs = useData<RecordValue[]>("/v2/environments", 3000);
  const action = useAction();
  const env = envs.data?.find((e) => e.id === environmentId);
  return (
    <div className="work-page-v2">
      <Link to="/environments">返回环境</Link>
      <PageHeader
        title={env?.name || "环境详情"}
        eyebrow="可复用基线"
        description="准备依赖和代码，验证后发布。已有工作任务不会被新版本覆盖。"
      />
      <ErrorNotice error={envs.error || action.error} />
      <div className="work-toolbar">
        <button
          className="button"
          disabled={action.busy || env?.ready}
          onClick={() =>
            void action.act(async () => {
              await api(`/v2/environments/${environmentId}/prepare`, {
                request_id: requestId(),
              });
            })
          }
        >
          准备环境
        </button>
        <button
          className="button primary"
          disabled={action.busy || !env?.ready}
          onClick={() =>
            void action.act(async () => {
              await api(`/v2/environments/${environmentId}/publish`, {
                request_id: requestId(),
              });
            })
          }
        >
          验证并发布新版本
        </button>
      </div>
      <div
        className="work-list"
        tabIndex={0}
        role="region"
        aria-label="环境版本记录"
      >
        {env?.revisions.map((revision: RecordValue) => (
          <div className="work-row" key={revision.id}>
            <div>
              <strong>{revision.id}</strong>
              <span className="muted">{revision.created_at}</span>
            </div>
            <Link
              className="button"
              to={`/work/new?environment=${revision.id}`}
            >
              使用此版本
            </Link>
          </div>
        ))}
      </div>
      {env?.ready && <WorkspaceTools owner={environmentId} />}
      <Jobs owner={environmentId} />
    </div>
  );
}

export function WorkItemsPage() {
  const { projectId = "" } = useParams();
  const items = useData<RecordValue[]>(
    `/v2/work-items?project_id=${projectId}`,
    4000,
  );
  return (
    <div className="work-page-v2">
      <Link to="/projects">返回项目</Link>
      <PageHeader
        title={projectId}
        eyebrow="工作任务"
        description="围绕目标持续工作，每次训练保留独立记录。"
      />
      <div className="work-toolbar">
        <Link className="button primary" to={`/work/new?project=${projectId}`}>
          新建工作任务
        </Link>
        <Link to={`/projects/${projectId}/runs`}>查看全部运行与历史记录</Link>
      </div>
      <ErrorNotice error={items.error} />
      {items.loading ? (
        <Loading />
      ) : !items.data?.length ? (
        <Empty
          title="还没有工作任务"
          description="可以在 Codex 中创建，也可以从这里选择环境开始。"
        />
      ) : (
        <div
          className="work-list"
          tabIndex={0}
          role="region"
          aria-label="工作任务列表"
        >
          {items.data.map((item) => (
            <div className="work-row" key={item.id}>
              <div>
                <Link to={`/work/${item.id}`}>
                  <strong>{item.title}</strong>
                </Link>
                <span className="muted">{item.next_step || item.goal}</span>
              </div>
              <State value={item.status} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function NewWorkPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const projects = useData<RecordValue[]>("/projects");
  const envs = useData<RecordValue[]>("/v2/environments");
  const action = useAction();
  const [project, setProject] = useState(
    params.get("project") || params.get("project_id") || "",
  );
  const [revision, setRevision] = useState(params.get("environment") || "");
  const [title, setTitle] = useState("");
  const [goal, setGoal] = useState("");
  const [constraints, setConstraints] = useState("");
  return (
    <div className="work-page-v2">
      <PageHeader
        title="新建工作任务"
        eyebrow="目标与环境"
        description="描述想训练的模型和预期结果，选择一个准备好的环境。"
      />
      <ErrorNotice error={action.error || projects.error || envs.error} />
      <form
        className="work-form"
        onSubmit={(e) => {
          e.preventDefault();
          void action.act(async () => {
            const value = await api("/v2/work-items", {
              request_id: requestId(),
              project_id: project,
              title,
              goal,
              constraints,
              environment_revision_id: revision,
            });
            navigate(
              `/work/${value.id}${params.get("parent") ? `?parent=${encodeURIComponent(params.get("parent")!)}` : ""}`,
            );
          });
        }}
      >
        <Field label="项目">
          <select
            required
            value={project}
            onChange={(e) => setProject(e.target.value)}
          >
            <option value="">选择项目</option>
            {projects.data?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="任务名称">
          <input
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </Field>
        <Field label="想完成什么">
          <textarea
            required
            rows={4}
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder="用客服录音微调语音识别模型，先做小规模验证"
          />
        </Field>
        <Field label="约束与偏好">
          <textarea
            rows={2}
            value={constraints}
            onChange={(e) => setConstraints(e.target.value)}
            placeholder="可用时间、资源限制、质量目标"
          />
        </Field>
        <Field label="训练环境">
          <select
            required
            value={revision}
            onChange={(e) => setRevision(e.target.value)}
          >
            <option value="">选择已发布的环境</option>
            {envs.data?.flatMap((env) =>
              env.revisions.map((r: RecordValue) => (
                <option value={r.id} key={r.id}>
                  {env.name} · {r.created_at}
                </option>
              )),
            )}
          </select>
        </Field>
        <Link to="/environments">准备或管理环境</Link>
        <button className="button primary" disabled={action.busy}>
          创建工作任务
        </button>
      </form>
    </div>
  );
}

function RunComposer({
  work,
  retryPlan,
}: {
  work: RecordValue;
  retryPlan?: RecordValue;
}) {
  const [params] = useSearchParams();
  const parent = params.get("parent");
  const definitions = useData<RecordValue[]>("/assets/framework");
  const recipes = useData<RecordValue[]>("/assets/recipe");
  const assets = useData<RecordValue[]>("/v2/assets");
  const gpus = useData<RecordValue[]>("/resources/gpus");
  const environments = useData<RecordValue[]>("/v2/environments");
  const action = useAction();
  const [task, setTask] = useState(retryPlan?.task || "");
  const [operation, setOperation] = useState(retryPlan?.operation || "train");
  const [recipe, setRecipe] = useState(retryPlan ? key(retryPlan.recipe) : "");
  const [inputs, setInputs] = useState<Record<string, string>>(
    retryPlan?.inputs || {},
  );
  const [gpu, setGpu] = useState(retryPlan?.resources.gpu_ids?.[0] || "");
  const [threads, setThreads] = useState(retryPlan?.resources.cpu_threads || 4);
  const [memory, setMemory] = useState(retryPlan?.resources.memory_mb || 4096);
  const [resourceDraft, setResourceDraft] = useState<{
    gpu: string;
    threads: number;
    memory: number;
  }>();
  const [sourceRun, setSourceRun] = useState("");
  const [sourcePath, setSourcePath] = useState("");
  const framework = definitions.data?.find(
    (f) => work.framework && key(f) === key(work.framework),
  );
  const contract = framework?.tasks[task]?.operations[operation];
  const requirements =
    contract?.required_inputs ||
    (!work.framework ? { dataset: "dataset", model: "model" } : {});
  const options =
    recipes.data?.filter((r) =>
      work.framework
        ? r.framework &&
          key(r.framework) === key(work.framework) &&
          r.task === task &&
          (r.operation || "train") === operation
        : !r.framework,
    ) || [];
  const chosenRecipe = options.find((r) => key(r) === recipe);
  const environment = environments.data?.find((env) =>
    env.revisions.some(
      (revision: RecordValue) => revision.id === work.environment_revision_id,
    ),
  );
  const environmentName = environment?.name || work.environment_revision_id;
  const environmentVersion = environment?.revisions.find(
    (r: RecordValue) => r.id === work.environment_revision_id,
  );
  const assetVersion = (asset: RecordValue) =>
    asset.legacy_ref?.version || asset.revision?.slice(0, 12);
  const inputOptions = (kind: unknown) =>
    (assets.data || [])
      .filter((a) => a.kind === kind && a.local_status === "DOWNLOADED")
      .map((a) => ({ id: a.id, name: a.name, version: assetVersion(a) }));
  const operationLabels: Record<string, string> = {
    prepare: "准备数据",
    train: "训练",
    evaluate: "评估",
    export: "导出",
    infer: "推理",
  };
  const errors =
    action.error || definitions.error || recipes.error || assets.error;
  const missing = Object.entries(requirements).some(
    ([name, kind]) => !inputOptions(kind).some((a) => a.id === inputs[name]),
  );
  const canCheck =
    work.ready &&
    !definitions.error &&
    !recipes.error &&
    !assets.error &&
    !definitions.loading &&
    !recipes.loading &&
    !assets.loading &&
    !!chosenRecipe &&
    !missing &&
    (!work.framework || !!contract);
  const recipeDetail = chosenRecipe?.optimizer
    ? [
        chosenRecipe.optimizer.name,
        chosenRecipe.optimizer.params?.lr != null
          ? `lr ${chosenRecipe.optimizer.params.lr}`
          : null,
        chosenRecipe.epochs != null ? `${chosenRecipe.epochs} epochs` : null,
        chosenRecipe.batch_size != null
          ? `batch ${chosenRecipe.batch_size}`
          : null,
      ]
        .filter(Boolean)
        .join(" · ")
    : chosenRecipe?.description || "固定本次运行使用的训练策略";
  const resourceName = `${gpu ? "GPU" : "CPU"} · ${threads} 线程 · ${memory / 1024} GiB`;
  return (
    <section className="run-composer" aria-label="创建运行方案">
      {parent && (
        <p className="composer-parent">
          基于运行 <Link to={`/runs/${parent}`}>{parent}</Link>{" "}
          创建新运行；原记录保持不变。
        </p>
      )}
      <ErrorNotice error={errors} />
      <form
        className="object-composer-layout"
        onSubmit={(e) => {
          e.preventDefault();
          if (!canCheck || action.busy) return;
          void action.act(async () => {
            await api("/v2/run-plans", {
              request_id: requestId(),
              work_item_id: work.id,
              task: task || "mnist",
              operation,
              inputs,
              recipe: reference(recipe),
              resources: {
                device: gpu ? "cuda" : "cpu",
                gpu_count: gpu ? 1 : 0,
                gpu_ids: gpu ? [gpu] : [],
                cpu_threads: threads,
                memory_mb: memory,
              },
              source_run_id: sourceRun || null,
              source_path: sourcePath || null,
              parent_run_id: parent,
            });
          });
        }}
      >
        <div className="composer-main">
          <ObjectRow label="所属项目" name={work.project_id} />
          <section
            className="composer-section"
            aria-labelledby="training-definition"
          >
            <header className="composer-section-heading">
              <h2 id="training-definition">
                <span>01</span>训练定义
              </h2>
              <p>选择数据、模型与训练策略，组成这一次运行。</p>
            </header>
            {work.framework && (
              <ObjectSelect
                label="任务类型"
                value={task}
                loading={definitions.loading}
                error={definitions.error}
                options={Object.entries(framework?.tasks || {}).map(
                  ([name, def]) => ({
                    id: name,
                    name: (def as RecordValue).description || name,
                  }),
                )}
                description="当前训练框架支持的任务"
                onChange={(value) => {
                  setTask(value);
                  setRecipe("");
                  setInputs({});
                  setSourceRun("");
                  setSourcePath("");
                  const operations = framework?.tasks[value]?.operations || {};
                  setOperation(
                    "train" in operations
                      ? "train"
                      : Object.keys(operations)[0] || "train",
                  );
                }}
              />
            )}
            {work.framework && (
              <ObjectSelect
                label="操作"
                value={operation}
                options={Object.keys(
                  framework?.tasks[task]?.operations || {},
                ).map((o) => ({
                  id: o,
                  name: operationLabels[o] || o,
                }))}
                description="本次运行要执行的任务"
                onChange={(value) => {
                  setOperation(value);
                  setRecipe("");
                  setInputs({});
                  setSourceRun("");
                  setSourcePath("");
                }}
              />
            )}
            {Object.entries(requirements).map(([name, kind]) => (
              <ObjectSelect
                key={name}
                label={kind === "dataset" ? "数据集" : "模型"}
                value={inputs[name] || ""}
                options={inputOptions(kind)}
                loading={assets.loading}
                error={assets.error}
                description={
                  kind === "dataset"
                    ? "只读挂载 · 训练时不重复下载"
                    : "模型架构与初始化权重"
                }
                emptyAction={<Link to="/library">前往模型与数据</Link>}
                onChange={(value) => setInputs({ ...inputs, [name]: value })}
              />
            ))}
            <ObjectSelect
              label="训练配方"
              value={recipe}
              options={options.map((r) => ({
                id: key(r),
                name: r.name,
                version: r.version,
              }))}
              loading={recipes.loading}
              error={recipes.error}
              onChange={setRecipe}
              description={
                <>
                  {recipeDetail}
                  {chosenRecipe?.loss && (
                    <>
                      <br />
                      损失函数　{chosenRecipe.loss}
                    </>
                  )}
                </>
              }
            />
            {contract?.needs_source && (
              <div className="composer-source work-form">
                <Field label="来源运行">
                  <input
                    required
                    value={sourceRun}
                    onChange={(e) => setSourceRun(e.target.value)}
                  />
                </Field>
                <Field label="来源产物路径">
                  <input
                    required
                    value={sourcePath}
                    onChange={(e) => setSourcePath(e.target.value)}
                  />
                </Field>
              </div>
            )}
          </section>
          <section
            className="composer-section"
            aria-labelledby="execution-environment"
          >
            <header className="composer-section-heading">
              <h2 id="execution-environment">
                <span>02</span>执行环境
              </h2>
              <p>沿用任务环境，检查方案时固定代码与依赖快照。</p>
            </header>
            <ObjectRow
              label="运行环境"
              name={environmentName}
              version={environmentVersion?.id
                .replace(/^environment_revision-/, "")
                .slice(0, 8)}
              description="Docker · 使用当前任务的依赖环境"
              action={
                environment && (
                  <Link
                    className="object-change"
                    to={`/environments/${environment.id}`}
                  >
                    查看 ›
                  </Link>
                )
              }
            />
            <ObjectRow
              label="代码空间"
              name={work.title}
              description="检查方案时创建不可变快照"
              action={
                work.ready && (
                  <a className="object-change" href="#work-workspace">
                    查看 ›
                  </a>
                )
              }
            />
            <ObjectRow
              label="计算资源"
              name={resourceName}
              description="本次运行的资源上限"
              action={
                <button
                  type="button"
                  className="object-change"
                  aria-haspopup="dialog"
                  onClick={() => setResourceDraft({ gpu, threads, memory })}
                >
                  更改配置
                </button>
              }
            />
          </section>
        </div>
        <aside className="composer-summary" aria-label="本次运行摘要">
          <header>
            <p className="composer-kicker">
              本次{operationLabels[operation] || "运行"}
            </p>
            <h2>准备创建 Run</h2>
            <p className="composer-caption">保存到 {work.project_id}</p>
          </header>
          <div className="composer-summary-assets">
            {Object.entries(requirements).map(([name, kind]) => {
              const asset = assets.data?.find((a) => a.id === inputs[name]);
              return (
                <div key={name}>
                  <strong>
                    {asset?.name ||
                      `尚未选择${kind === "dataset" ? "数据集" : "模型"}`}
                  </strong>
                  <span>{asset && assetVersion(asset)}</span>
                </div>
              );
            })}
            <div>
              <strong>{chosenRecipe?.name || "尚未选择训练配方"}</strong>
              <span>{chosenRecipe?.version}</span>
            </div>
          </div>
          <div className="composer-summary-environment">
            <strong>Docker · {gpu ? "GPU" : "CPU"}</strong>
            <p>
              {threads} 线程 · {memory / 1024} GiB 内存
            </p>
            <small>{environmentName}</small>
            {gpu && (
              <small>
                {gpus.data?.find((g) => g.uuid === gpu)?.name || gpu}
              </small>
            )}
          </div>
          <div className="composer-summary-workspace">
            <strong>{work.title}</strong>
            <small>检查方案时创建代码快照</small>
          </div>
          <div className="composer-summary-action">
            <button
              className="button primary wide"
              disabled={action.busy || !canCheck}
            >
              {action.busy && <LoaderCircle size={16} className="spin" />}
              {action.busy ? "正在提交检查…" : "检查并固定运行方案"}
              <ArrowRight size={16} />
            </button>
            <p className="composer-caption">
              检查完成后，在下方运行方案中开始运行。每次运行保留独立记录。
            </p>
            {!work.ready && (
              <p className="composer-caption">等待工作区准备完成。</p>
            )}
          </div>
        </aside>
      </form>
      {resourceDraft && (
        <ObjectEditor
          title="计算资源"
          onClose={() => setResourceDraft(undefined)}
        >
          <form
            className="work-form"
            onSubmit={(e) => {
              e.preventDefault();
              setGpu(resourceDraft.gpu);
              setThreads(resourceDraft.threads);
              setMemory(resourceDraft.memory);
              setResourceDraft(undefined);
            }}
          >
            <Field label="计算设备">
              <select
                value={resourceDraft.gpu}
                onChange={(e) =>
                  setResourceDraft({ ...resourceDraft, gpu: e.target.value })
                }
              >
                <option value="">CPU</option>
                {gpus.data?.map((g) => (
                  <option key={g.uuid} value={g.uuid}>
                    {g.name} · {g.uuid}
                  </option>
                ))}
                {resourceDraft.gpu &&
                  !gpus.data?.some((g) => g.uuid === resourceDraft.gpu) && (
                    <option value={resourceDraft.gpu}>
                      {resourceDraft.gpu}（待确认可用性）
                    </option>
                  )}
              </select>
            </Field>
            <ErrorNotice error={gpus.error} onRetry={gpus.refresh} />
            <Field label="CPU 线程">
              <input
                type="number"
                required
                min={1}
                max={32}
                step={1}
                value={resourceDraft.threads || ""}
                onChange={(e) =>
                  setResourceDraft({
                    ...resourceDraft,
                    threads: Number(e.target.value),
                  })
                }
              />
            </Field>
            <Field label="内存 / MiB">
              <input
                type="number"
                required
                min={512}
                max={262144}
                step={1}
                value={resourceDraft.memory || ""}
                onChange={(e) =>
                  setResourceDraft({
                    ...resourceDraft,
                    memory: Number(e.target.value),
                  })
                }
              />
            </Field>
            <div className="dialog-actions">
              <button
                type="button"
                className="button"
                onClick={() => setResourceDraft(undefined)}
              >
                取消
              </button>
              <button className="button primary">确认配置</button>
            </div>
          </form>
        </ObjectEditor>
      )}
    </section>
  );
}

export function WorkPage() {
  const { workId = "" } = useParams();
  const [params] = useSearchParams();
  const context = useData<RecordValue>(`/v2/work-items/${workId}`, 3000);
  const action = useAction();
  const work = context.data?.work_item;
  const parent = params.get("parent");
  const retryPlan = context.data?.plans.find((plan: RecordValue) =>
    context.data?.runs.some(
      (run: RecordValue) => run.id === parent && run.plan_id === plan.id,
    ),
  );
  return (
    <div className="work-page-v2">
      <Link to={work ? `/projects/${work.project_id}` : "/projects"}>
        返回项目
      </Link>
      <PageHeader
        title={work?.title || "工作任务"}
        eyebrow="Codex 工作上下文"
        description={work?.goal || "正在读取任务"}
      />
      <ErrorNotice error={context.error || action.error} />
      {work && (
        <>
          <div className="work-toolbar">
            <State value={work.status} />
            <span>{work.ready ? "工作区已准备" : "正在准备工作区"}</span>
            <button
              className="button"
              disabled={action.busy}
              onClick={() =>
                void action.act(async () => {
                  await api(`/v2/work-items/${workId}`, {
                    request_id: requestId(),
                    expected_version: work.version,
                    summary: work.summary,
                    next_step: work.next_step,
                    status:
                      work.status === "COMPLETED" ? "ACTIVE" : "COMPLETED",
                  });
                  await context.refresh();
                })
              }
            >
              {work.status === "COMPLETED" ? "继续工作" : "标记工作完成"}
            </button>
          </div>
          {work.constraints && <p>约束：{work.constraints}</p>}
          {work.summary && (
            <section className="work-section">
              <h2>Codex 进度摘要</h2>
              <p>{work.summary}</p>
              <p>下一步：{work.next_step}</p>
            </section>
          )}
          {work.status === "ACTIVE" && (
            <RunComposer
              key={parent || "new"}
              work={work}
              retryPlan={retryPlan}
            />
          )}
          <section className="work-section">
            <h2>运行方案</h2>
            <div
              className="work-list"
              tabIndex={0}
              role="region"
              aria-label="运行方案记录"
            >
              {context.data?.plans.map((plan: RecordValue) => (
                <div className="work-row" key={plan.id}>
                  <div>
                    <strong>
                      {plan.operation} · {plan.task}
                    </strong>
                    <span className="muted">{plan.error || plan.id}</span>
                  </div>
                  <State value={plan.status} />
                  {plan.status === "READY" && (
                    <button
                      className="button primary"
                      disabled={
                        action.busy ||
                        context.data?.jobs.some(
                          (j: RecordValue) =>
                            j.operation === "run" &&
                            j.payload.plan_id === plan.id,
                        )
                      }
                      onClick={() =>
                        void action.act(async () => {
                          await api("/v2/runs", {
                            request_id: `submit:${plan.id}`,
                            plan_id: plan.id,
                          });
                          await context.refresh();
                        })
                      }
                    >
                      开始运行
                    </button>
                  )}
                </div>
              ))}
            </div>
          </section>
          <section className="work-section">
            <h2>运行记录与成果</h2>
            <div
              className="work-list"
              tabIndex={0}
              role="region"
              aria-label="运行成果记录"
            >
              {context.data?.runs.map((run: RecordValue) => (
                <div className="work-row" key={run.id}>
                  <Link to={`/runs/${run.id}`}>{run.id}</Link>
                  <State value={run.status} />
                  <span className="muted">
                    {run.failure_reason ||
                      `${run.artifacts?.length || 0} 个产物`}
                  </span>
                </div>
              ))}
            </div>
          </section>
          {work.ready && (
            <div id="work-workspace">
              <WorkspaceTools owner={workId} />
            </div>
          )}
          <Jobs owner={workId} />
        </>
      )}
    </div>
  );
}

export function AgentSettingsPage() {
  const capabilities = useData<RecordValue>("/v2/capabilities");
  const action = useAction();
  const [migration, setMigration] = useState<RecordValue>();
  return (
    <div className="work-page-v2">
      <PageHeader
        title="Codex 接入"
        eyebrow="设置"
        description="在 Codex 中完成资产准备、环境配置、训练和迭代。Ninna 持续执行已提交的工作。"
      />
      <ErrorNotice error={capabilities.error || action.error} />
      <section className="work-section">
        <h2>连接 MCP</h2>
        <pre className="log-content">{`codex mcp add ninna --url ${window.location.origin}/mcp/`}</pre>
        <p>
          安装仓库中的 Ninna Skill。首次连接读取 ninna://guide 和
          get_capabilities；新的会话通过工作任务 ID 接续。
        </p>
        <p>
          资产文件在 Codex 所在机器上时，使用 ninna upload；不需要共享文件系统。
        </p>
      </section>
      <section className="work-section">
        <h2>历史数据迁移</h2>
        <p>为历史资产和环境创建新索引，保留原始运行和产物。先检查再执行。</p>
        <div className="work-toolbar">
          <button
            className="button"
            disabled={action.busy}
            onClick={() =>
              void action.act(async () =>
                setMigration(await api("/v2/migration")),
              )
            }
          >
            检查迁移
          </button>
          {migration && (
            <button
              className="button"
              disabled={action.busy}
              onClick={() =>
                void action.act(async () =>
                  setMigration(
                    await api("/v2/migration", { request_id: requestId() }),
                  ),
                )
              }
            >
              创建新索引
            </button>
          )}
        </div>
        {migration && (
          <p>
            {migration.assets} 个历史资产，{migration.runs_preserved}{" "}
            条运行记录；{migration.applied ? "已完成迁移" : "尚未执行"}。
          </p>
        )}
      </section>
      <details>
        <summary>平台能力</summary>
        <Json value={capabilities.data} />
      </details>
    </div>
  );
}
