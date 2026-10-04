import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { chartSeries } from "./chart-theme";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, useData } from "./api";
import type { Asset, Project, Ref, Run } from "./types";
import {
  Empty,
  ErrorNotice,
  Json,
  Loading,
  PageHeader,
  SectionHeader,
} from "./ui";

type Operation = {
  required_inputs: Record<string, "model" | "dataset">;
  needs_source: boolean;
};
type Framework = Asset & {
  tasks: Record<
    string,
    { description: string; operations: Record<string, Operation> }
  >;
};
type GPU = {
  uuid: string;
  name: string;
  memory_used_mb: number;
  utilization: number;
};
const key = (a: Ref) => `${a.name}/${a.version}`;
const ref = (a: Ref) => ({ name: a.name, version: a.version });
const operations: Record<string, string> = {
  prepare: "准备数据",
  train: "训练",
  evaluate: "评估",
  export: "导出",
  infer: "推理",
};

export function FrameworksPage() {
  const frameworks = useData<Framework[]>("/assets/framework");
  return (
    <div className="framework-page">
      <PageHeader
        eyebrow="Framework"
        title="训练框架"
        description="查看框架支持的任务、操作与 Agent 使用说明。"
      />
      <ErrorNotice error={frameworks.error} onRetry={frameworks.refresh} />
      {frameworks.loading ? (
        <Loading />
      ) : !frameworks.data?.length ? (
        <Empty
          title="尚未导入框架"
          description="先在镜像资产注册适配镜像，再通过 API 或 Agent 导入镜像内的框架说明与代码空间。"
        />
      ) : (
        frameworks.data.map((f) => (
          <section className="form-section" key={key(f)}>
            <SectionHeader
              title={`${f.name} / ${f.version}`}
              aside={
                <Link
                  className="button"
                  to={`/tasks/new?framework=${encodeURIComponent(key(f))}`}
                >
                  创建任务
                </Link>
              }
            />
            {Object.entries(f.tasks).map(([name, task]) => (
              <p key={name}>
                <strong>{name}</strong> · {task.description} ·{" "}
                {Object.keys(task.operations)
                  .map((o) => operations[o])
                  .join(" / ")}
              </p>
            ))}
            <details>
              <summary>Agent 使用说明</summary>
              <pre className="log-content">
                {f.documentation?.skill || "暂无说明"}
              </pre>
            </details>
          </section>
        ))
      )}
    </div>
  );
}

export function CreateTaskPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const projects = useData<Project[]>("/projects");
  const frameworks = useData<Framework[]>("/assets/framework");
  const recipes = useData<Asset[]>("/assets/recipe");
  const runtimes = useData<Asset[]>("/assets/runtime");
  const workspaces = useData<Asset[]>("/assets/workspace");
  const datasets = useData<Asset[]>("/assets/dataset");
  const models = useData<Asset[]>("/assets/model");
  const gpus = useData<GPU[]>("/resources/gpus", 10000);
  const [project, setProject] = useState(
    params.get("project_id") || params.get("project") || "",
  );
  const [framework, setFramework] = useState(params.get("framework") || "");
  const [task, setTask] = useState(params.get("task") || "");
  const [operation, setOperation] = useState("train");
  const [recipe, setRecipe] = useState("");
  const [runtime, setRuntime] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [gpu, setGPU] = useState("");
  const [memory, setMemory] = useState(8192);
  const [cpu, setCPU] = useState(4);
  const [sourceRun, setSourceRun] = useState("");
  const [sourcePath, setSourcePath] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const f = frameworks.data?.find((f) => key(f) === framework);
  const taskDef = f?.tasks[task];
  const contract = taskDef?.operations[operation];
  const recipeOptions =
    recipes.data?.filter(
      (a) =>
        a.framework &&
        key(a.framework) === framework &&
        a.task === task &&
        (a.operation || "train") === operation,
    ) || [];
  const runtimeOptions =
    runtimes.data?.filter(
      (a) => a.framework && key(a.framework) === framework,
    ) || [];
  const workspaceOptions =
    workspaces.data?.filter(
      (a) =>
        a.metadata.framework && key(a.metadata.framework as Ref) === framework,
    ) || [];
  const clear = () => {
    setRecipe("");
    setInputs({});
    setSourceRun("");
    setSourcePath("");
    setError("");
  };
  const select = (
    label: string,
    value: string,
    change: (value: string) => void,
    options: { value: string; label: string }[],
  ) => (
    <label className="form-field">
      {label}
      <select
        aria-label={label}
        required
        value={value}
        onChange={(e) => change(e.target.value)}
      >
        <option value="">请选择</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
  const assetOptions = (values: Asset[]) =>
    values.map((a) => ({ value: key(a), label: key(a) }));
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = recipeOptions.find((a) => key(a) === recipe),
        rt = runtimeOptions.find((a) => key(a) === runtime),
        ws = workspaceOptions.find((a) => key(a) === workspace);
      if (!f || !contract || !r || !rt || !ws)
        throw new Error("请选择匹配的框架、配方、运行环境和代码空间。");
      const resolvedInputs = Object.fromEntries(
        Object.entries(contract.required_inputs).map(([name, kind]) => {
          const asset = (kind === "model" ? models.data : datasets.data)?.find(
            (a) => key(a) === inputs[name],
          );
          if (!asset) throw new Error(`请选择输入 ${name}`);
          return [name, { kind, ref: ref(asset) }];
        }),
      );
      const body = {
        protocol_version: 1,
        parent_run_id: params.get("parent_run_id"),
        project_id: project,
        framework: ref(f),
        task,
        operation,
        recipe: ref(r),
        inputs: resolvedInputs,
        execution_spec: {
          runtime: ref(rt),
          workspace: { name: ws.name },
          resources: {
            device: gpu ? "cuda" : "cpu",
            gpu_count: gpu ? 1 : 0,
            gpu_ids: gpu ? [gpu] : [],
            memory_mb: memory,
            cpu_threads: cpu,
          },
        },
        source: sourceRun ? { run_id: sourceRun, path: sourcePath } : null,
      };
      await api("/tasks/preflight", body);
      const run = await api<Run>("/tasks", body);
      navigate(`/runs/${run.id}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const loadError = [
    projects,
    frameworks,
    recipes,
    runtimes,
    workspaces,
    datasets,
    models,
  ]
    .map((v) => v.error)
    .filter(Boolean)
    .join("; ");
  return (
    <div className="framework-page">
      <PageHeader
        eyebrow="Framework task"
        title="创建框架任务"
        description="选择已注册的配方与输入，校验后在独立容器中执行。"
      />
      <ErrorNotice error={loadError || error} />
      <form className="create-layout" onSubmit={submit}>
        <div>
          <section className="form-section">
            {select(
              "所属项目",
              project,
              setProject,
              projects.data?.map((p) => ({ value: p.id, label: p.name })) || [],
            )}
            {select(
              "训练框架",
              framework,
              (v) => {
                setFramework(v);
                setTask("");
                setRuntime("");
                setWorkspace("");
                clear();
              },
              assetOptions(frameworks.data || []),
            )}
            {select(
              "任务",
              task,
              (v) => {
                setTask(v);
                setOperation("train");
                clear();
              },
              Object.entries(f?.tasks || {}).map(([value, t]) => ({
                value,
                label: `${value} · ${t.description}`,
              })),
            )}
            {select(
              "操作",
              operation,
              (v) => {
                setOperation(v);
                clear();
              },
              Object.keys(taskDef?.operations || {}).map((value) => ({
                value,
                label: operations[value],
              })),
            )}
            {select("配方", recipe, setRecipe, assetOptions(recipeOptions))}
            {contract && !recipeOptions.length && (
              <p className="muted">
                该操作尚无配方，请先注册对应的原生 Lightning 配置。
              </p>
            )}
          </section>
          <section className="form-section">
            <SectionHeader title="输入资产" />
            {Object.entries(contract?.required_inputs || {}).map(
              ([name, kind]) => (
                <div key={name}>
                  {select(
                    `${name} · ${kind === "model" ? "模型" : "数据集"}`,
                    inputs[name] || "",
                    (v) => setInputs({ ...inputs, [name]: v }),
                    assetOptions(
                      (kind === "model" ? models.data : datasets.data) || [],
                    ),
                  )}
                </div>
              ),
            )}
            <label className="form-field">
              来源运行 ID
              {contract?.needs_source ? "（必填）" : "（恢复训练时填写）"}
              <input
                required={contract?.needs_source}
                value={sourceRun}
                onChange={(e) => setSourceRun(e.target.value)}
              />
            </label>
            {sourceRun && (
              <label className="form-field">
                来源产物路径
                <input
                  required
                  value={sourcePath}
                  onChange={(e) => setSourcePath(e.target.value)}
                  placeholder="checkpoints/last.ckpt"
                />
              </label>
            )}
          </section>
          <section className="form-section">
            <SectionHeader title="执行环境" />
            {select(
              "运行环境",
              runtime,
              setRuntime,
              assetOptions(runtimeOptions),
            )}
            {select(
              "代码空间",
              workspace,
              setWorkspace,
              assetOptions(workspaceOptions),
            )}
            <label className="form-field">
              计算设备
              <select value={gpu} onChange={(e) => setGPU(e.target.value)}>
                <option value="">CPU</option>
                {gpus.data?.map((g) => (
                  <option
                    key={g.uuid}
                    value={g.uuid}
                    disabled={g.memory_used_mb > 128 || g.utilization > 0}
                  >
                    {g.name} · {g.uuid} · 已用 {g.memory_used_mb} MB
                  </option>
                ))}
              </select>
            </label>
            <ErrorNotice error={gpus.error} onRetry={gpus.refresh} />
            <label className="form-field">
              CPU 线程
              <input
                type="number"
                min={1}
                max={32}
                value={cpu}
                onChange={(e) => setCPU(Number(e.target.value))}
              />
            </label>
            <label className="form-field">
              内存（MB）
              <input
                type="number"
                min={512}
                max={262144}
                value={memory}
                onChange={(e) => setMemory(Number(e.target.value))}
              />
            </label>
          </section>
          <button
            className="button primary"
            disabled={busy || !contract || !!loadError}
          >
            {busy ? "校验并创建中…" : "创建任务"}
          </button>
        </div>
        <aside>
          <SectionHeader title="配方内容" />
          <Json
            value={recipeOptions.find((a) => key(a) === recipe)?.config || {}}
          />
          <p className="muted">
            每次执行固定资产版本和代码快照。来源产物必须属于当前项目且已封存。
          </p>
        </aside>
      </form>
    </div>
  );
}

export function TaskMetrics({ run, events }: { run: Run; events: any[] }) {
  const values = {
    ...events.reduce((acc, event) => ({ ...acc, ...event.metrics }), {}),
    ...run.metrics,
  };
  const names = Object.keys(values).filter(
    (name) => typeof values[name] === "number",
  );
  const [selected, setSelected] = useState("");
  const metric = names.includes(selected) ? selected : names[0] || "";
  const rows = events
    .filter((event) => typeof event.metrics?.[metric] === "number")
    .map((event) => ({ step: event.step, value: event.metrics[metric] }));
  const result = run.metadata.result as
    | { evidence?: Record<string, unknown>; quality?: { status: string } }
    | undefined;
  const quality = result?.quality?.status;
  return (
    <>
      <SectionHeader
        title={`${run.task_spec?.task} · ${operations[run.task_spec?.operation || ""] || "任务"}`}
      />
      <dl className="task-metrics">
        {names.map((name) => (
          <div key={name}>
            <dt>{name}</dt>
            <dd className="mono">{values[name].toPrecision(6)}</dd>
          </div>
        ))}
      </dl>
      {!names.length && <p className="muted">等待任务上报指标。</p>}
      {!!names.length && (
        <label className="form-field">
          指标曲线
          <select
            value={metric}
            onChange={(event) => setSelected(event.target.value)}
          >
            {names.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </label>
      )}
      {!!rows.length && (
        <div
          role="img"
          aria-label={`${metric} 随优化步变化`}
          style={{ height: 260 }}
        >
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rows}>
              <XAxis dataKey="step" stroke="var(--muted)" />
              <YAxis width={70} stroke="var(--muted)" />
              <Tooltip />
              <Line
                type="linear"
                dataKey="value"
                name={metric}
                stroke={chartSeries[0].color}
                dot
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      <SectionHeader title="训练与质量证据" />
      <p>
        质量判定：
        {quality === "passed"
          ? "通过"
          : quality === "failed"
            ? "未达标"
            : "尚未评估"}
      </p>
      <Json value={result?.evidence || { status: "等待任务证据" }} />
    </>
  );
}
