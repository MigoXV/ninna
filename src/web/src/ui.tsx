import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  ArrowUpRight,
  Check,
  Circle,
  LoaderCircle,
  OctagonAlert,
  X,
  Inbox,
  RotateCcw,
} from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
export const statusLabel: Record<string, string> = {
  CREATED: "等待执行",
  PREPARING: "准备中",
  RUNNING: "训练中",
  SUCCESS: "已完成",
  FAILED: "失败",
  CANCELLED: "已取消",
  PASS: "通过",
  FAIL: "未通过",
};
export function Status({ value }: { value: string }) {
  const Icon = ["SUCCESS", "PASS"].includes(value)
    ? Check
    : ["FAILED", "FAIL"].includes(value)
      ? OctagonAlert
      : value === "CANCELLED"
        ? X
        : ["RUNNING", "PREPARING"].includes(value)
          ? LoaderCircle
          : Circle;
  return (
    <span className={"status status-" + value.toLowerCase()}>
      <Icon size={13} />
      {statusLabel[value] || value}
    </span>
  );
}
export function ErrorNotice({
  error,
  onRetry,
}: {
  error: string;
  onRetry?: () => void;
}) {
  return error ? (
    <div className="error-notice" role="alert">
      <OctagonAlert size={17} />
      <span>{error}</span>
      {onRetry && (
        <button className="text-button" onClick={onRetry}>
          <RotateCcw size={14} />
          重试
        </button>
      )}
    </div>
  ) : null;
}
export function Empty({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <Inbox size={30} strokeWidth={1} />
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        {description && <p className="page-description">{description}</p>}
      </div>
      <div className="page-actions">{actions}</div>
    </header>
  );
}
export function SectionHeader({
  title,
  aside,
}: {
  title: string;
  aside?: ReactNode;
}) {
  return (
    <div className="section-heading">
      <h2>{title}</h2>
      {aside}
    </div>
  );
}
export function AssetLink({
  kind,
  name,
  version,
}: {
  kind: string;
  name: string;
  version: string;
}) {
  return (
    <Link
      className="asset-link"
      to={
        "/assets/" +
        kind +
        "?name=" +
        encodeURIComponent(name) +
        "&version=" +
        encodeURIComponent(version)
      }
    >
      {name}
      <span className="version">{version}</span>
    </Link>
  );
}
export function Json({ value }: { value: unknown }) {
  return (
    <pre className="json-view" tabIndex={0} aria-label="JSON 数据">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}
export function ShortId({ value }: { value: string }) {
  return (
    <span className="mono" title={value}>
      {value.slice(0, 16)}
    </span>
  );
}
export function Loading() {
  return (
    <div className="loading" role="status">
      <LoaderCircle size={18} className="spin" />
      正在读取工作空间…
    </div>
  );
}
export function time(value: string | null) {
  return value
    ? new Intl.DateTimeFormat("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(value))
    : "—";
}
export function duration(start: string | null, end: string | null) {
  if (!start) return "—";
  const seconds = Math.max(
    0,
    Math.floor(
      ((end ? new Date(end).getTime() : Date.now()) -
        new Date(start).getTime()) /
        1000,
    ),
  );
  return seconds < 60
    ? `${seconds}s`
    : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}
export function percent(value: number | undefined) {
  return value === undefined ? "—" : (value * 100).toFixed(2) + "%";
}
export function Metric({
  label,
  value,
  detail,
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
}) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
    </div>
  );
}
export function LossChart({
  events,
  comparison,
}: {
  events: any[];
  comparison?: any[];
}) {
  const rows = events.map((event, i) => ({
    ...event,
    comparison: comparison?.[i]?.train_loss,
  }));
  if (comparison && comparison.length > rows.length)
    comparison
      .slice(rows.length)
      .forEach((event) =>
        rows.push({ epoch: event.epoch, comparison: event.train_loss }),
      );
  return (
    <div
      className="chart-region"
      role="img"
      aria-label="每轮训练与测试损失曲线"
    >
      {rows.length ? (
        <>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart
              data={rows}
              margin={{ top: 15, right: 15, bottom: 5, left: -24 }}
            >
              <CartesianGrid
                stroke="var(--line)"
                vertical={false}
                strokeDasharray="3 5"
              />
              <XAxis
                dataKey="epoch"
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 12, fill: "var(--muted)" }}
                label={{
                  value: "Epoch",
                  position: "insideBottomRight",
                  offset: -2,
                  fontSize: 11,
                }}
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 12, fill: "var(--muted)" }}
              />
              <Tooltip
                contentStyle={{
                  background: "var(--elevated)",
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  fontSize: 12,
                }}
              />
              <Line
                name={comparison ? "Run A · train loss" : "Train loss"}
                type="linear"
                dataKey="train_loss"
                stroke="#8a651f"
                strokeWidth={2}
                dot={{ r: 3 }}
                isAnimationActive={false}
              />
              <Line
                name={comparison ? "Run B · train loss" : "Test loss"}
                type="linear"
                dataKey={comparison ? "comparison" : "test_loss"}
                stroke="#557d83"
                strokeWidth={2}
                dot={{ r: 3 }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
          <div className="chart-legend">
            <span>
              <i /> {comparison ? "Run A" : "Train loss"}
            </span>
            <span>
              <i /> {comparison ? "Run B" : "Test loss"}
            </span>
          </div>
        </>
      ) : (
        <div className="chart-placeholder">
          <div className="empty-chart-lines" />
          <span>等待首个训练指标</span>
          <small>每个 epoch 完成后更新曲线</small>
        </div>
      )}
    </div>
  );
}
export function ExternalLink({
  to,
  children,
}: {
  to: string;
  children: ReactNode;
}) {
  return (
    <Link className="text-link" to={to}>
      {children}
      <ArrowUpRight size={14} />
    </Link>
  );
}
