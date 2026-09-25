import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Box,
  Boxes,
  Check,
  ChevronRight,
  Database,
  Download,
  FileCode2,
  FolderCode,
  LoaderCircle,
  Play,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { api, useData } from "./api";
import type { Asset, Cert } from "./types";
import {
  Empty,
  ErrorNotice,
  Json,
  Loading,
  PageHeader,
  percent,
  SectionHeader,
  Status,
  time,
} from "./ui";
const definitions: Record<
  string,
  { title: string; en: string; description: string; icon: typeof Database }
> = {
  dataset: {
    title: "数据集",
    en: "Dataset",
    description: "已沉淀的数据资产。每一次训练，都从确定的数据版本开始。",
    icon: Database,
  },
  model: {
    title: "模型",
    en: "Model",
    description: "可训练的架构与初始化权重。训练的输入，也是新的起点。",
    icon: Boxes,
  },
  recipe: {
    title: "训练配方",
    en: "Recipe",
    description: "独立定义如何训练。同一个模型，可以有不同的学习方式。",
    icon: SlidersHorizontal,
  },
  runtime: {
    title: "运行环境",
    en: "Runtime",
    description: "版本化的 Docker 基础环境，让执行条件保持稳定。",
    icon: Box,
  },
  workspace: {
    title: "代码空间",
    en: "Workspace",
    description: "自由修改训练代码，为每次执行保留不可变快照。",
    icon: FolderCode,
  },
};
export function AssetsPage() {
  const { kind = "dataset" } = useParams();
  const info = definitions[kind];
  if (!info)
    return <Empty title="未知资产类型" description="请从左侧导航选择资产。" />;
  return <AssetContent key={kind} kind={kind} info={info} />;
}
function AssetContent({
  kind,
  info,
}: {
  kind: string;
  info: (typeof definitions)[string];
}) {
  const { data, error, loading, refresh } = useData<Asset[]>("/assets/" + kind);
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(""),
    [operationError, setOperationError] = useState(""),
    [snap, setSnap] = useState<Asset>(),
    [busy, setBusy] = useState(false);
  const selected = data?.find(
    (a) => a.name === params.get("name") && a.version === params.get("version"),
  );
  const Icon = info.icon;
  const rows =
    data?.filter((a) => (a.name + " " + a.version).includes(search)) || [];
  async function snapshot() {
    if (!selected) return;
    setBusy(true);
    try {
      setSnap(await api("/workspaces/" + selected.name + "/snapshots", {}));
    } catch (e) {
      setOperationError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      {selected && (
        <button className="back-link" onClick={() => setParams({})}>
          <ArrowLeft size={14} />
          {info.title}
        </button>
      )}
      <PageHeader
        eyebrow={
          (kind === "runtime" || kind === "workspace"
            ? "执行环境"
            : "训练定义") +
          " / " +
          info.en
        }
        title={selected ? selected.name : info.title}
        description={
          selected ? `${info.en} asset · ${selected.version}` : info.description
        }
        actions={
          selected ? (
            <Link
              className="button"
              to={"/runs/new?" + kind + "=" + encodeURIComponent(selected.id)}
            >
              <Play size={15} />
              用于训练
            </Link>
          ) : undefined
        }
      />
      <ErrorNotice error={error} onRetry={refresh} />
      <ErrorNotice error={operationError} />
      {loading ? (
        <Loading />
      ) : selected ? (
        <div className="asset-detail">
          <div className="asset-overview">
            <div className="asset-large-icon">
              <Icon size={30} strokeWidth={1.3} />
            </div>
            <div>
              <span className="eyebrow">{info.en}</span>
              <h2>
                {selected.name}
                <span className="version">{selected.version}</span>
              </h2>
              <p>
                {kind === "dataset"
                  ? "可直接参与训练的数据资产"
                  : kind === "model"
                    ? "架构、初始化与来源独立记录"
                    : kind === "recipe"
                      ? "训练策略由配置定义"
                      : kind === "runtime"
                        ? "通过固定 image ID 执行"
                        : "可编辑目录 → 不可变执行快照"}
              </p>
            </div>
          </div>
          {kind === "dataset" && (
            <>
              <div className="asset-facts">
                <div>
                  <span>训练样本</span>
                  <strong>{selected.train_split.count.toLocaleString()}</strong>
                </div>
                <div>
                  <span>测试样本</span>
                  <strong>{selected.test_split.count.toLocaleString()}</strong>
                </div>
                <div>
                  <span>图像尺寸</span>
                  <strong>
                    {selected.metadata.shape?.toString().replaceAll(",", " × ")}
                  </strong>
                </div>
                <div>
                  <span>类别</span>
                  <strong>{String(selected.metadata.classes)}</strong>
                </div>
              </div>
              <SectionHeader title="数据版本" />
              <dl className="detail-list horizontal">
                <dt>存储路径</dt>
                <dd className="mono break">{selected.path}</dd>
                <dt>SHA-256</dt>
                <dd className="mono break">{selected.checksum}</dd>
                <dt>读取方式</dt>
                <dd>只读挂载 · 离线读取</dd>
                <dt>资产格式</dt>
                <dd>
                  {selected.metadata.format === "huggingface.DatasetDict"
                    ? "Hugging Face · DatasetDict / Arrow"
                    : "MNIST / IDX"}
                </dd>
              </dl>
              <SectionHeader title="文件清单" />
              <Json value={selected.files} />
            </>
          )}
          {kind === "model" && (
            <>
              <SectionHeader title="网络结构" />
              <div className="architecture-flow">
                {selected.architecture.description
                  .split(" → ")
                  .map((s: string, i: number) => (
                    <div key={i}>
                      <span>{s}</span>
                      {i <
                        selected.architecture.description.split(" → ").length -
                          1 && <ArrowRight size={14} />}
                    </div>
                  ))}
              </div>
              <div className="asset-facts">
                <div>
                  <span>参数量</span>
                  <strong>{selected.parameter_count.toLocaleString()}</strong>
                </div>
                <div>
                  <span>初始化</span>
                  <strong>
                    {selected.initial_checkpoint
                      ? "Checkpoint"
                      : "Random seed " + selected.initialization.seed}
                  </strong>
                </div>
                <div>
                  <span>资产格式</span>
                  <strong>
                    {selected.metadata.format === "huggingface.PreTrainedModel"
                      ? "HF · Safetensors"
                      : "PyTorch"}
                  </strong>
                </div>
              </div>
              {selected.metadata.source_run_id && (
                <Link
                  className="text-link"
                  to={"/runs/" + selected.metadata.source_run_id}
                >
                  查看来源 Run <ArrowUpRight size={14} />
                </Link>
              )}
              <SectionHeader title="模型定义" />
              <Json value={selected} />
            </>
          )}
          {kind === "recipe" && (
            <>
              <div className="asset-facts">
                <div>
                  <span>优化器</span>
                  <strong>{selected.optimizer.name}</strong>
                </div>
                <div>
                  <span>Learning rate</span>
                  <strong>{selected.optimizer.params.lr}</strong>
                </div>
                <div>
                  <span>Epochs</span>
                  <strong>{selected.epochs}</strong>
                </div>
                <div>
                  <span>Batch size</span>
                  <strong>{selected.batch_size}</strong>
                </div>
              </div>
              <SectionHeader title="训练策略" />
              <Json
                value={{
                  training_loop: selected.training_loop,
                  loss: selected.loss,
                  optimizer: selected.optimizer,
                  scheduler: selected.scheduler,
                  epochs: selected.epochs,
                  batch_size: selected.batch_size,
                  gradient_accumulation: selected.gradient_accumulation,
                  freeze: selected.freeze,
                  seed: selected.seed,
                }}
              />
              <div className="definition-note">
                <SlidersHorizontal size={20} />
                <div>
                  <strong>改变策略，无须修改模型。</strong>
                  <p>
                    Loss、optimizer 和 training loop 均独立于 Model。使用不同
                    Recipe 创建新的 Run。
                  </p>
                </div>
              </div>
            </>
          )}
          {kind === "runtime" && (
            <>
              <SectionHeader title="运行环境" />
              <dl className="detail-list horizontal">
                <dt>Docker image</dt>
                <dd className="mono break">{selected.image}</dd>
                <dt>固定 image ID</dt>
                <dd className="mono break">{selected.image_id}</dd>
                <dt>Python</dt>
                <dd>{String(selected.metadata.python)}</dd>
                <dt>PyTorch</dt>
                <dd>{String(selected.metadata.torch)} · CPU</dd>
                <dt>torchvision</dt>
                <dd>{String(selected.metadata.torchvision)}</dd>
                {Boolean(selected.metadata.transformers) && (
                  <>
                    <dt>Transformers / Datasets</dt>
                    <dd>
                      {String(selected.metadata.transformers)} /{" "}
                      {String(selected.metadata.datasets)}
                    </dd>
                  </>
                )}
              </dl>
              <div className="definition-note">
                <Box size={20} />
                <div>
                  <strong>环境稳定，代码独立演进。</strong>
                  <p>
                    训练逻辑通过 Workspace 挂载。修改代码无需重新构建此镜像。
                  </p>
                </div>
              </div>
            </>
          )}
          {kind === "workspace" && (
            <>
              <dl className="detail-list horizontal">
                <dt>工作目录</dt>
                <dd className="mono break">{selected.path}</dd>
                <dt>执行入口</dt>
                <dd className="mono">{selected.entrypoint}</dd>
              </dl>
              <SectionHeader
                title="代码文件"
                aside={
                  <button
                    className="button small"
                    disabled={busy}
                    onClick={snapshot}
                  >
                    {busy ? (
                      <LoaderCircle size={14} />
                    ) : (
                      <FileCode2 size={14} />
                    )}
                    创建快照
                  </button>
                }
              />
              {snap && (
                <div className="success-notice" role="status">
                  <Check size={15} />
                  快照已保存{" "}
                  <span className="mono break">{String(snap.snapshot)}</span>
                </div>
              )}
              <WorkspaceFiles name={selected.name} />
            </>
          )}
        </div>
      ) : (
        <>
          <div className="table-toolbar">
            <span className="muted text-small">{rows.length} 个已注册版本</span>
            <label className="search-field">
              <Search size={16} />
              <input
                aria-label="搜索资产"
                placeholder="搜索名称或版本"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
          </div>
          {rows.length ? (
            <div className="asset-catalog">
              {rows.map((a) => (
                <button
                  className="asset-catalog-row"
                  key={a.id}
                  onClick={() =>
                    setParams({ name: a.name, version: a.version })
                  }
                >
                  <div className="asset-icon">
                    <Icon size={23} strokeWidth={1.5} />
                  </div>
                  <div className="asset-catalog-main">
                    <strong>
                      {a.name}
                      <span className="version">{a.version}</span>
                    </strong>
                    <p>
                      {kind === "dataset"
                        ? `${a.train_split.count.toLocaleString()} train / ${a.test_split.count.toLocaleString()} test · 28 × 28`
                        : kind === "model"
                          ? `${a.parameter_count.toLocaleString()} parameters · ${a.initial_checkpoint ? "checkpoint initialization" : "seed " + a.initialization.seed}`
                          : kind === "recipe"
                            ? `${a.optimizer.name} · lr ${a.optimizer.params.lr} · ${a.epochs} epochs`
                            : kind === "runtime"
                              ? `Python ${a.metadata.python} · PyTorch ${a.metadata.torch} · CPU`
                              : "train.py · 可编辑代码与不可变快照"}
                    </p>
                  </div>
                  <span className="catalog-type">
                    {String(a.metadata?.format || "").startsWith("huggingface.")
                      ? "Hugging Face"
                      : info.en}
                  </span>
                  <ArrowUpRight size={17} />
                </button>
              ))}
            </div>
          ) : (
            <Empty
              title="暂无资产"
              description="在训练运行页面初始化 MNIST 资产，或通过 API 注册新的资产版本。"
              action={
                <Link className="text-link" to="/runs">
                  前往工作台 <ArrowRight size={14} />
                </Link>
              }
            />
          )}
          <div className="asset-bottom-note">
            <span className="mono">{info.en.toUpperCase()}</span>
            <p>{info.description}</p>
          </div>
        </>
      )}
    </>
  );
}
function WorkspaceFiles({ name }: { name: string }) {
  const files = useData<string[]>("/workspaces/" + name + "/files");
  const [file, setFile] = useState(""),
    [content, setContent] = useState(""),
    [error, setError] = useState("");
  useEffect(() => {
    if (!file && files.data?.length) setFile(files.data[0]);
  }, [files.data, file]);
  useEffect(() => {
    if (!file) return;
    let active = true;
    setContent("");
    api<{ content: string }>(
      "/workspaces/" + name + "/files?path=" + encodeURIComponent(file),
    )
      .then((r) => {
        if (active) {
          setContent(r.content);
          setError("");
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [file, name]);
  return (
    <>
      <ErrorNotice error={files.error || error} />
      <div className="workspace-editor">
        <div className="file-tree">
          {files.data?.map((f) => (
            <button
              className={file === f ? "selected" : ""}
              key={f}
              onClick={() => setFile(f)}
            >
              <FileCode2 size={14} />
              {f}
            </button>
          ))}
        </div>
        <div className="code-pane">
          <header>
            <span className="mono">{file}</span>
            <span>只读预览</span>
          </header>
          <pre tabIndex={0}>{content}</pre>
        </div>
      </div>
    </>
  );
}
export function CertificationPage() {
  const {
    data: records,
    error,
    refresh,
  } = useData<Cert[]>("/certifications", 2000);
  const [selected, setSelected] = useState(""),
    [quick, setQuick] = useState(false),
    [busy, setBusy] = useState(false),
    [operationError, setOperationError] = useState("");
  const record = records?.find((r) => r.id === selected) || records?.[0];
  const running = records?.some((r) => r.status === "RUNNING");
  async function start() {
    setBusy(true);
    setOperationError("");
    try {
      const r = await api<Cert>("/certifications", { quick });
      setSelected(r.id);
      await refresh();
    } catch (e) {
      setOperationError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const passCount =
    record?.checks.filter((c) => c.status === "PASS").length || 0;
  return (
    <>
      <PageHeader
        eyebrow="系统验证 / Certification"
        title="让训练链路自己证明"
        description="从数据挂载到模型重载，用一次真实实验检查平台的每一个环节。"
        actions={
          <button
            className="button primary"
            onClick={start}
            disabled={busy || running}
          >
            {busy || running ? (
              <LoaderCircle size={16} className="spin" />
            ) : (
              <Play size={16} />
            )}{" "}
            {running ? "验收进行中" : "运行 MNIST 验收"}
          </button>
        }
      />
      <ErrorNotice error={error} onRetry={refresh} />
      <ErrorNotice error={operationError} />
      <div className="cert-intro">
        <div className="cert-intro-mark">
          <ShieldCheck size={38} strokeWidth={1.2} />
        </div>
        <div>
          <h2>MNIST Platform Certification</h2>
          <p>
            同一个 Dataset，同一个 Model，分别使用 Adam 与 SGD。
            <br />
            检查真实容器、模型更新、loss 下降，以及完整测试集上的准确率。
          </p>
        </div>
        <label className="cert-mode">
          <span>验收模式</span>
          <select
            aria-label="验收模式"
            disabled={running}
            value={quick ? "quick" : "full"}
            onChange={(e) => setQuick(e.target.value === "quick")}
          >
            <option value="full">完整验收 · &gt; 98%</option>
            <option value="quick">快速验收 · &gt; 95%</option>
          </select>
        </label>
      </div>
      <div className="cert-layout">
        <section>
          <SectionHeader
            title={record ? "验收记录" : "准备检查"}
            aside={
              record ? (
                <span className="mono muted text-small">{record.id}</span>
              ) : undefined
            }
          />
          {record ? (
            <>
              <div className="cert-result">
                <Status value={record.status} />
                <span>{passCount} 项已通过</span>
                <span className="muted">
                  {record.profile === "full" ? "完整验收" : "快速验收"} ·{" "}
                  {time(record.created_at)}
                </span>
              </div>
              {record.failure_reason && (
                <ErrorNotice error={record.failure_reason} />
              )}
              <div className="check-list">
                {record.checks.map((c, i) => (
                  <details key={i} className="check-item">
                    <summary>
                      <span className="check-number">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <span className={"check-icon " + c.status.toLowerCase()}>
                        {c.status === "PASS" ? (
                          <Check size={15} />
                        ) : (
                          <X size={15} />
                        )}
                      </span>
                      <span>{c.name}</span>
                      {c.name.includes("accuracy") &&
                        c.evidence?.accuracy !== undefined && (
                          <strong className="mono">
                            {percent(c.evidence.accuracy)}
                          </strong>
                        )}
                      <ChevronRight size={14} />
                    </summary>
                    <div className="check-evidence">
                      <Json value={c.evidence ?? "检查通过，无附加证据"} />
                    </div>
                  </details>
                ))}
              </div>
              {record.status === "RUNNING" && (
                <div className="cert-running" role="status">
                  <LoaderCircle className="spin" size={17} />
                  <div>
                    <strong>正在真实容器中训练与验证</strong>
                    <p>
                      完整验收需要几分钟。你可以离开此页，稍后回来查看结果。
                    </p>
                  </div>
                </div>
              )}
              {record.status !== "RUNNING" && (
                <div className={"overall " + record.status.toLowerCase()}>
                  <span>OVERALL</span>
                  <strong>{record.status}</strong>
                  <a
                    href={"/api/certifications/" + record.id}
                    target="_blank"
                    rel="noreferrer"
                    className="text-link"
                  >
                    <Download size={14} />
                    JSON 报告
                  </a>
                </div>
              )}
            </>
          ) : (
            <div className="cert-preview">
              {[
                "资产注册与 Runtime 可用性",
                "Docker 容器与真实挂载",
                "训练进程与日志采集",
                "Checkpoint 保存与独立重载",
                "模型 Hash 变化与 Loss 下降",
                "测试准确率与 Recipe 解耦",
              ].map((label, i) => (
                <div key={label}>
                  <span className="check-number">0{i + 1}</span>
                  <span>{label}</span>
                  <span className="muted text-small">待运行</span>
                </div>
              ))}
            </div>
          )}
        </section>
        <aside className="cert-aside">
          <h3>验收门槛</h3>
          <div className="threshold">
            <strong>
              {record ? record.threshold * 100 : quick ? 95 : 98}
              <span>%</span>
            </strong>
            <span>测试准确率须高于此值</span>
          </div>
          <p>
            使用完整的 10,000 张 MNIST
            测试图像。权重必须发生变化，固定样本集上的 loss 必须下降。
          </p>
          <div className="aside-rule" />
          <h3>关联训练</h3>
          {record?.run_ids.length ? (
            record.run_ids.map((id, i) => (
              <Link className="linked-run" to={"/runs/" + id} key={id}>
                <div>
                  <strong>
                    {i === 0 ? "Recipe A · Adam" : "Recipe B · SGD"}
                  </strong>
                  <span className="mono">{id}</span>
                </div>
                <ArrowUpRight size={15} />
              </Link>
            ))
          ) : (
            <p>启动验收后，将创建两次独立 Training Run。</p>
          )}
          {record?.run_ids.length === 2 && (
            <Link
              className="text-link"
              to={"/runs/compare?ids=" + record.run_ids.join(",")}
            >
              比较两次训练 <ArrowRight size={14} />
            </Link>
          )}
          <div className="aside-rule" />
          <h3>历史验收</h3>
          {records?.length ? (
            records.map((r) => (
              <button
                className={
                  "cert-history " + (record?.id === r.id ? "selected" : "")
                }
                key={r.id}
                onClick={() => setSelected(r.id)}
              >
                <span>{time(r.created_at)}</span>
                <Status value={r.status} />
              </button>
            ))
          ) : (
            <p>尚无验收记录。</p>
          )}
        </aside>
      </div>
    </>
  );
}
