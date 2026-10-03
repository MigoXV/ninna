import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowUpRight, Download } from "lucide-react";
import { api, useData } from "./api";
import { formatBytes } from "./format";
import {
  ImageCatalog,
  ImageCrumbs,
  catalogHref,
  imageScope,
  scopeLabel,
} from "./image-catalog";
import type { Asset } from "./types";
import {
  Empty,
  ErrorNotice,
  Json,
  Loading,
  PageHeader,
  SectionHeader,
} from "./ui";

const assetLink = (a: { name: string; version: string }, kind = "image") =>
  `/assets/${kind}?name=${encodeURIComponent(a.name)}&version=${encodeURIComponent(a.version)}`;

const states: Record<string, string> = {
  CREATED: "等待拉取",
  RUNNING: "正在拉取",
  SUCCESS: "已注册",
  FAILED: "拉取失败",
  AVAILABLE: "本地可用",
  MISSING: "本地缺失",
  UNAVAILABLE: "无法连接 Docker",
};

export function ImagesPage() {
  const [params] = useSearchParams();
  const name = params.get("name"),
    version = params.get("version"),
    mode = params.get("action");
  if (name && version)
    return (
      <ImageDetail key={`${name}/${version}`} name={name} version={version} />
    );
  if (mode === "local" || mode === "pull")
    return <ImageForm key={mode} mode={mode} />;
  if (mode === "tasks") return <ImagePulls />;
  return <ImageCatalog />;
}
function ImagePulls() {
  const [params] = useSearchParams();
  const scope = imageScope(params);
  const pulls = useData<any[]>("/image-pulls", 2000);
  return (
    <>
      <ImageCrumbs scope={scope} tail="拉取任务" />
      <PageHeader
        eyebrow="执行环境 / Image"
        title="拉取任务"
        description="查看所有拉取的进度、固定 digest 与结果。离开页面后任务继续。"
        actions={
          <Link
            className="button primary"
            to={catalogHref(scope, { action: "pull" })}
          >
            <Download size={15} />
            拉取远端镜像
          </Link>
        }
      />
      <ErrorNotice error={pulls.error} onRetry={pulls.refresh} />
      {pulls.loading ? (
        <Loading />
      ) : pulls.data?.length ? (
        <div className="image-pulls">
          {pulls.data.map((job) => (
            <PullJob key={job.id} job={job} />
          ))}
        </div>
      ) : (
        !pulls.error && (
          <Empty
            title="暂无拉取任务"
            description="从镜像仓库拉取后，任务记录会保存在这里。"
          />
        )
      )}
    </>
  );
}
function PullJob({ job }: { job: any }) {
  return (
    <details className="image-pull">
      <summary>
        <span>
          <strong>{job.request.name}</strong>
          <span className="version">{job.request.version}</span>
        </span>
        <span className="muted image-source">{job.request.source}</span>
        <span>{states[job.status]}</span>
      </summary>
      <div className="image-pull-body">
        <p className="mono break">
          {job.id} · {job.resolved_reference || "尚未解析 digest"}
        </p>
        {job.error && <ErrorNotice error={job.error} />}
        <div>
          {Object.entries(job.layers).map(([id, layer]: [string, any]) => (
            <p key={id} className="text-small">
              <span className="mono">{id}</span> · {layer.status}
              {layer.total
                ? ` · ${formatBytes(layer.current || 0)} / ${formatBytes(layer.total)}`
                : ""}
            </p>
          ))}
        </div>
        {job.logs.length > 0 && <pre tabIndex={0}>{job.logs.join("\n")}</pre>}
        {job.status === "SUCCESS" && (
          <Link className="text-link" to={assetLink(job.request)}>
            查看镜像资产 <ArrowUpRight size={14} />
          </Link>
        )}
        {job.status === "FAILED" && (
          <Link className="text-link" to="/assets/image?action=pull">
            重新发起拉取
          </Link>
        )}
      </div>
    </details>
  );
}
function ImageForm({ mode }: { mode: "local" | "pull" }) {
  const local = useData<any[]>("/images/local");
  const [params, setParams] = useSearchParams();
  const scope = imageScope(params);
  const back = catalogHref(scope);
  const [name, setName] = useState(""),
    [version, setVersion] = useState("v1"),
    [source, setSource] = useState(
      params.get("source") ||
        (mode === "pull" && scope.registry && scope.registry !== "local"
          ? [
              scope.registry,
              scope.namespace === "_" ? "" : scope.namespace,
              scope.repository,
            ]
              .filter(Boolean)
              .join("/") + (scope.repository ? ":" : "/")
          : ""),
    ),
    [description, setDescription] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api(mode === "local" ? "/assets/image" : "/image-pulls", {
        name,
        version,
        source,
        description,
      });
      setParams(
        mode === "local" ? { name, version } : { ...scope, action: "tasks" },
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <ImageCrumbs
        scope={scope}
        tail={mode === "local" ? "注册本地镜像" : "拉取远端镜像"}
      />
      <PageHeader
        eyebrow="执行环境 / Image"
        title={mode === "local" ? "注册本地镜像" : "拉取远端镜像"}
        description={
          mode === "local"
            ? "读取 Docker 的实际元数据，保存不可变资产版本。"
            : "先解析仓库 digest，再按固定内容拉取；离开页面后任务继续。"
        }
      />
      <form className="image-form" onSubmit={submit}>
        <ErrorNotice error={error} />
        {mode === "local" ? (
          <>
            <ErrorNotice error={local.error} onRetry={local.refresh} />
            <label>
              本地镜像
              <select
                required
                value={source}
                onChange={(e) => setSource(e.target.value)}
                disabled={local.loading}
              >
                <option value="">
                  {local.loading ? "正在读取 Docker…" : "选择镜像"}
                </option>
                {local.data?.flatMap((a) =>
                  [...a.tags, a.image_id].map((ref: string) => (
                    <option key={a.image_id + ref} value={ref}>
                      {ref} · {a.architecture} · {formatBytes(a.size)}
                    </option>
                  )),
                )}
              </select>
            </label>
          </>
        ) : (
          <label>
            仓库地址
            <input
              required
              value={source}
              onChange={(e) => setSource(e.target.value)}
              placeholder="registry.example.com/team/image:version"
              autoComplete="off"
            />
            <span className="muted text-small">
              私有仓库使用平台部署侧 Docker 凭据；地址中不要填写密码。
            </span>
          </label>
        )}
        <ReferencePreview source={source} />
        <div className="image-identity-fields">
          <label>
            资产名称
            <input
              required
              pattern="[A-Za-z0-9_.-]+"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="pytorch-cpu"
            />
          </label>
          <label>
            版本
            <input
              required
              pattern="[A-Za-z0-9_.-]+"
              value={version}
              onChange={(e) => setVersion(e.target.value)}
            />
          </label>
        </div>
        <label>
          说明
          <input
            maxLength={1000}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="镜像的用途与来源"
          />
        </label>
        <div className="image-form-actions">
          <button className="button primary" disabled={busy}>
            {busy
              ? "正在提交…"
              : mode === "local"
                ? "注册镜像资产"
                : "开始拉取"}
          </button>
          <Link className="button secondary" to={back}>
            返回列表
          </Link>
        </div>
      </form>
    </>
  );
}
function ReferencePreview({ source }: { source: string }) {
  const [value, setValue] = useState<any>();
  useEffect(() => {
    setValue(undefined);
    let active = true;
    if (!source || source.startsWith("sha256:")) return;
    const timer = setTimeout(() => {
      void api("/images/reference?source=" + encodeURIComponent(source))
        .then((v) => {
          if (active) setValue(v);
        })
        .catch(() => {});
    }, 300);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [source]);
  return (
    <p className="muted text-small break" role="status">
      {source.startsWith("sha256:")
        ? "按 image ID 登记到本地镜像；目录依据注册时唯一的仓库路径归类，多仓库或无标签时归入未分类。"
        : value
          ? `登记位置：${scopeLabel(value.registry)} / ${scopeLabel(value.namespace)} / ${value.repository} · ${value.reference}`
          : "选择或填写完整镜像引用后显示登记位置。"}
    </p>
  );
}
function ImageDetail({ name, version }: { name: string; version: string }) {
  const detail = useData<any>(
    `/assets/image/${encodeURIComponent(name)}/${encodeURIComponent(version)}`,
    5000,
  );
  const [creating, setCreating] = useState(false);
  const d = detail.data,
    a = d?.asset;
  return (
    <>
      <ImageCrumbs scope={d?.location} tail={version} />
      <PageHeader
        eyebrow="执行环境 / Image"
        title={name}
        description={`不可变镜像资产 · ${version}`}
        actions={
          <button
            className="button primary"
            disabled={d?.availability.status !== "AVAILABLE"}
            onClick={() => setCreating(!creating)}
          >
            创建运行环境
          </button>
        }
      />
      <ErrorNotice error={detail.error} onRetry={detail.refresh} />
      {detail.loading ? (
        <Loading />
      ) : (
        a && (
          <>
            <div className="image-availability" role="status">
              {states[d.availability.status]}
              {d.availability.error && ` · ${d.availability.error}`}
            </div>
            {creating && (
              <RuntimeForm
                image={a}
                onCreated={() => {
                  setCreating(false);
                  void detail.refresh();
                }}
              />
            )}
            <SectionHeader title="镜像身份" />
            <dl className="detail-list horizontal">
              <dt>Image ID</dt>
              <dd className="mono break">{a.image_id}</dd>
              <dt>来源</dt>
              <dd className="mono break">{a.source_reference}</dd>
              <dt>仓库 digest</dt>
              <dd className="mono break">
                {a.repo_digests.join("\n") || "本地构建，无仓库 digest"}
              </dd>
              <dt>注册时标签</dt>
              <dd className="mono break">{a.tags.join(", ") || "无标签"}</dd>
              <dt>平台 / 大小</dt>
              <dd>
                {a.os}/{a.architecture}
                {a.variant && `/${a.variant}`} · {formatBytes(a.size)}
              </dd>
              <dt>说明</dt>
              <dd>{a.description || "未填写"}</dd>
              <dt>注册时间</dt>
              <dd>{a.created_at}</dd>
            </dl>
            <SectionHeader title="引用的运行环境" />
            {d.runtimes.length ? (
              d.runtimes.map((r: Asset) => (
                <p key={r.id}>
                  <Link className="text-link" to={assetLink(r, "runtime")}>
                    {r.name} / {r.version}
                    <ArrowUpRight size={14} />
                  </Link>
                </p>
              ))
            ) : (
              <p className="muted">
                尚无 Runtime 引用。创建时会在容器中验证训练依赖。
              </p>
            )}
            <SectionHeader title="使用此镜像的训练" />
            {d.runs.length ? (
              d.runs.map((r: any) => (
                <p key={r.id}>
                  <Link className="text-link mono" to={`/runs/${r.id}`}>
                    {r.id}
                  </Link>{" "}
                  · {r.status}
                </p>
              ))
            ) : (
              <p className="muted">暂无训练记录。</p>
            )}
            <details className="image-pull">
              <summary>构建来源与完整元数据</summary>
              <Json value={a} />
            </details>
          </>
        )
      )}
    </>
  );
}
export function RuntimeForm({
  image,
  onCreated,
}: {
  image: Asset;
  onCreated: () => void;
}) {
  const [name, setName] = useState(""),
    [version, setVersion] = useState("v1"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  return (
    <form
      className="image-form runtime-form"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError("");
        try {
          await api("/assets/runtime", {
            name,
            version,
            image_ref: { name: image.name, version: image.version },
          });
          onCreated();
        } catch (e) {
          setError((e as Error).message);
        } finally {
          setBusy(false);
        }
      }}
    >
      <SectionHeader title="创建运行环境" />
      <p className="muted text-small">
        固定引用此镜像版本，验证 Python、PyTorch 和 HF 训练依赖。
      </p>
      <ErrorNotice error={error} />
      <div className="image-identity-fields">
        <label>
          Runtime 名称
          <input
            required
            pattern="[A-Za-z0-9_.-]+"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label>
          版本
          <input
            required
            pattern="[A-Za-z0-9_.-]+"
            value={version}
            onChange={(e) => setVersion(e.target.value)}
          />
        </label>
      </div>
      <button className="button primary" disabled={busy}>
        {busy ? "正在容器中验证…" : "验证并创建"}
      </button>
    </form>
  );
}
