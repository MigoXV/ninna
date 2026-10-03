import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ChevronRight,
  Download,
  Plus,
  Search,
  Globe2,
  Folder,
  Layers,
} from "lucide-react";
import { useData } from "./api";
import { formatBytes } from "./format";
import { Empty, ErrorNotice, Loading, PageHeader } from "./ui";

export type ImageScope = {
  registry?: string;
  namespace?: string;
  repository?: string;
};
export function imageScope(params: URLSearchParams): ImageScope {
  return Object.fromEntries(
    ["registry", "namespace", "repository"].flatMap((k) =>
      params.has(k) ? [[k, params.get(k)!]] : [],
    ),
  );
}
export function catalogHref(
  scope: ImageScope = {},
  extra: Record<string, string> = {},
) {
  const query = new URLSearchParams({ ...scope, ...extra });
  return "/assets/image" + (query.size ? "?" + query : "");
}
export function scopeLabel(value: string) {
  return value === "local"
    ? "本地镜像"
    : value === "_"
      ? "无命名空间"
      : value === "unclassified"
        ? "未分类"
        : value;
}
export function ImageCrumbs({
  scope = {},
  tail,
}: {
  scope?: ImageScope;
  tail?: string;
}) {
  const parts: { label: string; href: string }[] = [
    { label: "镜像资产", href: catalogHref() },
  ];
  const path: ImageScope = {};
  for (const key of ["registry", "namespace", "repository"] as const) {
    if (!scope[key]) break;
    path[key] = scope[key];
    parts.push({ label: scopeLabel(scope[key]!), href: catalogHref(path) });
  }
  return (
    <nav className="image-breadcrumb" aria-label="镜像目录路径">
      {parts.map((p, i) => (
        <span key={p.href}>
          {i > 0 && <ChevronRight size={12} aria-hidden="true" />}
          {i === parts.length - 1 && !tail ? (
            <span aria-current="page">{p.label}</span>
          ) : (
            <Link to={p.href}>{p.label}</Link>
          )}
        </span>
      ))}
      {tail && (
        <span>
          <ChevronRight size={12} aria-hidden="true" />
          <span aria-current="page">{tail}</span>
        </span>
      )}
    </nav>
  );
}
function VersionRows({ rows, search }: { rows: any[]; search: boolean }) {
  return (
    <div className="catalog-table-scroll">
      <table className="catalog-table">
        <thead>
          <tr>
            <th>{search ? "镜像路径 / 版本" : "版本 / Tag"}</th>
            <th>固定内容</th>
            <th>平台</th>
            <th>大小</th>
            <th>登记</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={[
                row.registry,
                row.namespace,
                row.repository,
                row.reference,
                row.image_id,
              ].join("/")}
            >
              <td>
                {search && (
                  <Link
                    className="catalog-full-path"
                    to={catalogHref(rowScope(row))}
                  >
                    {scopeLabel(row.registry)} / {scopeLabel(row.namespace)} /{" "}
                    {scopeLabel(row.repository)}
                  </Link>
                )}
                <span className="catalog-version mono">{row.reference}</span>
              </td>
              <td>
                <span className="mono" title={row.image_id}>
                  {row.image_id.slice(0, 24)}…
                </span>
              </td>
              <td>{row.platform || "—"}</td>
              <td className="mono">{formatBytes(row.size)}</td>
              <td>
                {row.assets.length === 1 ? (
                  <Link
                    className="text-link"
                    to={catalogHref(
                      {},
                      {
                        name: row.assets[0].name,
                        version: row.assets[0].version,
                      },
                    )}
                  >
                    查看详情
                    <ChevronRight size={13} />
                  </Link>
                ) : (
                  <details className="catalog-registrations">
                    <summary>{row.assets.length} 条登记</summary>
                    {row.assets.map((a: any) => (
                      <Link
                        key={a.id}
                        to={catalogHref(
                          {},
                          { name: a.name, version: a.version },
                        )}
                      >
                        {a.name} / {a.version}
                      </Link>
                    ))}
                  </details>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function rowScope(row: ImageScope): ImageScope {
  return {
    registry: row.registry,
    namespace: row.namespace,
    repository: row.repository,
  };
}
export function ImageCatalog() {
  const [params, setParams] = useSearchParams();
  const scope = imageScope(params),
    q = params.get("q") || "";
  const [draft, setDraft] = useState(q);
  useEffect(() => setDraft(q), [q]);
  const query = new URLSearchParams({ ...scope, ...(q ? { q } : {}) });
  const result = useData<any>("/images/catalog?" + query, 5000);
  const pulls = useData<any[]>("/image-pulls", 5000);
  const active =
    pulls.data?.filter((j) => ["CREATED", "RUNNING"].includes(j.status))
      .length || 0;
  const level = result.data?.level;
  const noun =
    level === "registries"
      ? "站点"
      : level === "namespaces"
        ? "命名空间"
        : level === "repositories"
          ? "镜像"
          : "版本";
  const title = scope.repository
    ? scopeLabel(scope.repository)
    : scope.namespace
      ? scopeLabel(scope.namespace)
      : scope.registry
        ? scopeLabel(scope.registry)
        : "镜像资产";
  const Icon =
    level === "registries" ? Globe2 : level === "namespaces" ? Folder : Layers;
  return (
    <>
      <ImageCrumbs scope={scope} />
      <PageHeader
        eyebrow="执行环境 / Image"
        title={title}
        description={
          scope.repository
            ? "按固定内容记录版本，选择登记查看资产详情。"
            : "按站点、命名空间和镜像浏览已登记的资产。"
        }
        actions={
          <>
            <Link
              className="button secondary"
              to={catalogHref(scope, { action: "pull" })}
            >
              <Download size={15} />
              拉取远端镜像
            </Link>
            <Link
              className="button primary"
              to={catalogHref(scope, { action: "local" })}
            >
              <Plus size={15} />
              注册本地镜像
            </Link>
          </>
        }
      />
      <div className="catalog-controls">
        <form
          className="catalog-search"
          onSubmit={(e) => {
            e.preventDefault();
            setParams({
              ...scope,
              ...(draft.trim() ? { q: draft.trim() } : {}),
            });
          }}
        >
          <Search size={15} />
          <input
            key={q}
            aria-label="搜索镜像"
            defaultValue={q}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="搜索镜像路径、标签或资产名称"
          />
          <button type="submit" className="button small">
            搜索
          </button>
          {q && (
            <Link
              className="text-link"
              to={catalogHref(scope)}
              onClick={() => setDraft("")}
            >
              清除
            </Link>
          )}
        </form>
        <Link
          className="text-link"
          to={catalogHref(scope, { action: "tasks" })}
        >
          拉取任务
          {active > 0 && <span className="version">{active} 进行中</span>}
          <ChevronRight size={14} />
        </Link>
      </div>
      <ErrorNotice error={result.error} onRetry={result.refresh} />
      <ErrorNotice
        error={pulls.error ? "拉取任务状态暂不可用" : ""}
        onRetry={pulls.refresh}
      />
      {result.loading ? (
        <Loading />
      ) : (
        result.data && (
          <>
            <div className="catalog-count muted text-small">
              {q ? `“${q}” · ` : ""}
              {level !== "versions" &&
                `${result.data.items.length} 个${noun} · `}
              {result.data.version_count} 个版本 · {result.data.asset_count}{" "}
              条登记
            </div>
            {result.data.items.length ? (
              level === "versions" ? (
                <VersionRows rows={result.data.items} search={!!q} />
              ) : (
                <div className="catalog-table-scroll">
                  <table className="catalog-table directory-table">
                    <thead>
                      <tr>
                        <th>{noun}</th>
                        <th>
                          {level === "registries"
                            ? "命名空间 / 镜像"
                            : level === "namespaces"
                              ? "镜像"
                              : "平台"}
                        </th>
                        <th>版本</th>
                        <th>最近登记</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.data.items.map((row: any) => (
                        <tr key={row.name}>
                          <td>
                            <Link
                              className="catalog-folder"
                              to={catalogHref(row.scope)}
                            >
                              <Icon size={17} strokeWidth={1.5} />
                              <span>{scopeLabel(row.name)}</span>
                              <ChevronRight size={14} />
                            </Link>
                          </td>
                          <td className="muted">
                            {level === "registries"
                              ? `${row.namespace_count} / ${row.repository_count}`
                              : level === "namespaces"
                                ? row.repository_count
                                : row.platforms.join(", ") || "—"}
                          </td>
                          <td className="mono">{row.version_count}</td>
                          <td className="mono muted">
                            {row.created_at?.slice(0, 10) || "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
            ) : (
              <Empty
                title={q ? "没有匹配的镜像" : "此目录暂无镜像"}
                description={
                  q
                    ? "调整关键词，或清除搜索后继续浏览。"
                    : "注册本地镜像或拉取远端版本后即可在目录中查看。"
                }
              />
            )}
          </>
        )
      )}
    </>
  );
}
