import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, ChartNoAxesCombined, Search } from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, useData } from "./api";
import {
  Empty,
  ErrorNotice,
  Loading,
  PageHeader,
  SectionHeader,
  Status,
  percent,
  time,
} from "./ui";
import type { Run } from "./types";

type Experiment = Run & {
  aim_hash: string;
  summary: Record<string, number>;
  recipe?: {
    optimizer?: { name: string; params: { lr: number } };
    batch_size?: number;
    epochs?: number;
  };
};
type Curves = {
  run_id: string;
  aim_hash: string;
  source: string;
  synced_at: string;
  series: { name: string; points: { step: number; value: number }[] }[];
};
const metrics = {
  train_loss: "训练损失",
  test_loss: "测试损失",
  test_accuracy: "测试准确率",
  lr: "学习率",
  elapsed_time: "累计用时 / s",
};
const colors = ["#63734c", "#a57c31", "#587c91", "#945b6d"];

export function ExperimentsPage() {
  const data = useData<{
    tracking: { enabled: boolean; error: string | null; tracked_runs: number };
    runs: Experiment[];
  }>("/experiments", 3000);
  const [selected, setSelected] = useState<string[]>([]),
    [search, setSearch] = useState(""),
    [status, setStatus] = useState("");
  const [metric, setMetric] = useState<keyof typeof metrics>("train_loss"),
    [curves, setCurves] = useState<Curves[]>([]),
    [error, setError] = useState("");
  const [initialized, setInitialized] = useState(false),
    [curvesLoading, setCurvesLoading] = useState(false);
  useEffect(() => {
    if (!initialized && data.data?.runs.length) {
      setSelected(
        data.data.runs
          .filter((r) => r.status === "SUCCESS")
          .slice(0, 2)
          .map((r) => r.id),
      );
      setInitialized(true);
    }
  }, [data.data, initialized]);
  const selectionKey = selected.join(",");
  useEffect(() => {
    let current = true,
      ticket = 0;
    setCurves([]);
    setCurvesLoading(!!selectionKey);
    setError("");
    async function read() {
      const request = ++ticket;
      try {
        const values = await Promise.all(
          selectionKey
            .split(",")
            .filter(Boolean)
            .map((id) => api<Curves>("/experiments/" + id + "/metrics")),
        );
        if (current && request === ticket) {
          setCurves(values);
          setError("");
        }
      } catch (e) {
        if (current) setError((e as Error).message);
      } finally {
        if (current) setCurvesLoading(false);
      }
    }
    void read();
    const timer = window.setInterval(read, 3000);
    return () => {
      current = false;
      window.clearInterval(timer);
    };
  }, [selectionKey]);
  const runs = data.data?.runs || [];
  const shown = runs.filter(
    (r) =>
      (!status || r.status === status) &&
      [r.id, r.training_spec.recipe.name, r.training_spec.model.name]
        .join(" ")
        .includes(search),
  );
  const rows = new Map<number, Record<string, number>>();
  curves.forEach((curve, i) =>
    curve.series
      .find((s) => s.name === metric)
      ?.points.forEach((point) => {
        const row = rows.get(point.step) || { step: point.step };
        row["run" + i] = point.value;
        rows.set(point.step, row);
      }),
  );
  const points = [...rows.values()].sort((a, b) => a.step - b.step);
  function toggle(id: string) {
    setSelected((ids) =>
      ids.includes(id)
        ? ids.filter((value) => value !== id)
        : ids.length < 4
          ? [...ids, id]
          : ids,
    );
  }
  return (
    <>
      <PageHeader
        eyebrow="实验观察 / Experiments"
        title="读懂每一次学习"
        description="从 Aim 读取训练曲线与实验参数，在同一个工作空间里比较结果。"
        actions={
          <Link className="button" to="/hub">
            记录设置
            <ArrowUpRight size={14} />
          </Link>
        }
      />
      <ErrorNotice
        error={data.error || data.data?.tracking.error || error}
        onRetry={data.refresh}
      />
      {data.data && !data.data.tracking.enabled && (
        <div className="integration-notice">
          Aim 记录已暂停。已有实验仍可查看，新训练的指标会在重新启用后补录。
        </div>
      )}
      <div className="experiment-topline">
        <span>
          <ChartNoAxesCombined size={17} />
          Aim SDK <span className="version">3.29.1</span>
        </span>
        <p>
          {runs.length} 个实验 · {selected.length} / 4 已选
        </p>
      </div>
      {data.loading ? (
        <Loading />
      ) : !runs.length ? (
        <Empty
          title="等待第一个实验"
          description="平台会把真实 Run 的参数、状态和指标同步到 Aim。创建一次训练后即可查看。"
          action={
            <Link className="button primary" to="/runs/new">
              创建训练
            </Link>
          }
        />
      ) : (
        <div className="experiment-workspace">
          <section className="experiment-library" aria-label="选择实验">
            <div className="experiment-filters">
              <label className="sr-only" htmlFor="experiment-search">
                搜索实验
              </label>
              <div className="experiment-search">
                <Search size={15} />
                <input
                  id="experiment-search"
                  placeholder="搜索 Run 或 Recipe"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
              <label className="sr-only" htmlFor="experiment-state">
                实验状态
              </label>
              <select
                id="experiment-state"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
              >
                <option value="">全部状态</option>
                <option value="SUCCESS">已完成</option>
                <option value="RUNNING">训练中</option>
                <option value="FAILED">失败</option>
                <option value="CANCELLED">已取消</option>
              </select>
            </div>
            <div className="experiment-list">
              {shown.map((run) => (
                <label
                  className={
                    "experiment-pick " +
                    (selected.includes(run.id) ? "selected" : "")
                  }
                  key={run.id}
                >
                  <input
                    type="checkbox"
                    checked={selected.includes(run.id)}
                    disabled={
                      !selected.includes(run.id) && selected.length >= 4
                    }
                    onChange={() => toggle(run.id)}
                  />
                  <div>
                    <strong>{run.training_spec.recipe.name}</strong>
                    <span className="mono">{run.id}</span>
                    <small>
                      {time(run.created_at)} · {run.training_spec.model.name}
                    </small>
                  </div>
                  <Status value={run.status} />
                </label>
              ))}
              {!shown.length && (
                <Empty
                  title="没有匹配的实验"
                  description="修改搜索条件或状态筛选。"
                />
              )}
            </div>
          </section>
          <section className="experiment-canvas">
            <div className="experiment-chart-toolbar">
              <h2>训练轨迹</h2>
              <label>
                <span className="sr-only">显示指标</span>
                <select
                  aria-label="显示指标"
                  value={metric}
                  onChange={(e) =>
                    setMetric(e.target.value as keyof typeof metrics)
                  }
                >
                  {Object.entries(metrics).map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {!selected.length ? (
              <Empty
                title="选择实验，开始比较"
                description="最多选择 4 个实验，按真实 epoch 对齐曲线。"
              />
            ) : curvesLoading ? (
              <Loading />
            ) : !points.length ? (
              <Empty
                title="尚无该指标"
                description="训练产生 epoch 指标后会自动显示。失败或提前取消的 Run 可能没有曲线。"
              />
            ) : (
              <div
                className="aim-chart"
                role="img"
                aria-label={metrics[metric] + "随 epoch 变化，下方提供数值表格"}
              >
                <ResponsiveContainer width="100%" height={310}>
                  <LineChart
                    data={points}
                    margin={{ top: 12, right: 20, bottom: 20, left: 0 }}
                    accessibilityLayer
                  >
                    <CartesianGrid stroke="#e9e1d2" vertical={false} />
                    <XAxis
                      dataKey="step"
                      allowDecimals={false}
                      tick={{ fontSize: 12, fill: "#6c6557" }}
                      label={{
                        value: "epoch",
                        position: "insideBottom",
                        offset: -12,
                      }}
                    />
                    <YAxis
                      tick={{ fontSize: 12, fill: "#6c6557" }}
                      domain={
                        metric === "test_accuracy" ? [0, 1] : ["auto", "auto"]
                      }
                      width={55}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "#fffdf8",
                        border: "1px solid #ded4bf",
                        borderRadius: 6,
                        fontSize: 12,
                      }}
                    />
                    {curves.map((curve, i) => (
                      <Line
                        key={curve.run_id}
                        name={curve.run_id}
                        dataKey={"run" + i}
                        stroke={colors[i]}
                        strokeWidth={2}
                        dot={{ r: 3 }}
                        connectNulls={false}
                        isAnimationActive={false}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
            <div className="aim-legend">
              {curves.map((curve, i) => (
                <Link key={curve.run_id} to={"/runs/" + curve.run_id}>
                  <i style={{ background: colors[i] }} />
                  {curve.run_id}
                  <ArrowUpRight size={12} />
                </Link>
              ))}
            </div>
            <SectionHeader title="结果与来源" aside="数据来源：Aim" />
            <div className="experiment-summaries">
              {selected.map((id) => {
                const run = runs.find((r) => r.id === id);
                if (!run) return null;
                return (
                  <div className="experiment-summary" key={id}>
                    <Link to={"/runs/" + id}>
                      {id}
                      <ArrowUpRight size={13} />
                    </Link>
                    <dl>
                      <dt>Recipe</dt>
                      <dd>
                        {run.training_spec.recipe.name} /{" "}
                        {run.training_spec.recipe.version}
                      </dd>
                      <dt>优化器 / lr</dt>
                      <dd>
                        {run.recipe?.optimizer
                          ? `${run.recipe.optimizer.name} / ${run.recipe.optimizer.params.lr}`
                          : "—"}
                      </dd>
                      <dt>Batch / epochs</dt>
                      <dd>
                        {run.recipe?.batch_size ?? "—"} /{" "}
                        {run.recipe?.epochs ?? "—"}
                      </dd>
                      <dt>测试准确率</dt>
                      <dd>{percent(run.summary.test_accuracy)}</dd>
                      <dt>最终训练损失</dt>
                      <dd>{run.summary.final_train_loss?.toFixed(5) || "—"}</dd>
                      <dt>Aim hash</dt>
                      <dd className="mono break">{run.aim_hash}</dd>
                    </dl>
                  </div>
                );
              })}
            </div>
            {!!points.length && (
              <details className="aim-values">
                <summary>查看原始数值 · {metrics[metric]}</summary>
                <div className="table-scroll" tabIndex={0}>
                  <table className="comparison-table">
                    <thead>
                      <tr>
                        <th>Epoch</th>
                        {curves.map((c) => (
                          <th key={c.run_id}>{c.run_id}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {points.map((row) => (
                        <tr key={row.step}>
                          <th>{row.step}</th>
                          {curves.map((c, i) => (
                            <td key={c.run_id}>
                              {row["run" + i] === undefined
                                ? "—"
                                : row["run" + i].toPrecision(6)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            )}
          </section>
        </div>
      )}
    </>
  );
}
