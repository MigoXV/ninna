import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

export type ObjectOption = { id: string; name: string; version?: string };

export function ObjectRow({
  label,
  name,
  version,
  description,
  action,
}: {
  label: string;
  name: string;
  version?: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="object-row">
      <span className="object-type">{label}</span>
      <div className="object-identity">
        <div className="object-name-line">
          <strong>{name}</strong>
          {version && <span className="object-version">{version}</span>}
        </div>
        {description && <div className="object-description">{description}</div>}
      </div>
      {action}
    </div>
  );
}

export function ObjectEditor({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const heading = useId();
  useEffect(() => {
    const dialog = ref.current!;
    const trigger = document.activeElement as HTMLElement | null;
    dialog.showModal();
    return () => {
      dialog.close();
      trigger?.focus();
    };
  }, []);
  return createPortal(
    <dialog
      ref={ref}
      className="object-editor"
      aria-labelledby={heading}
      onCancel={onClose}
      onClose={onClose}
    >
      <div className="dialog-heading">
        <h2 id={heading}>{title}</h2>
        <button
          type="button"
          className="icon-button"
          aria-label="关闭"
          onClick={onClose}
        >
          <X size={18} />
        </button>
      </div>
      {children}
    </dialog>,
    document.body,
  );
}

export function ObjectSelect({
  label,
  value,
  options,
  description,
  onChange,
  loading = false,
  error = "",
  emptyAction,
}: {
  label: string;
  value: string;
  options: ObjectOption[];
  description?: ReactNode;
  onChange: (value: string) => void;
  loading?: boolean;
  error?: string;
  emptyAction?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(value);
  const selected = options.find((o) => o.id === value);
  return (
    <>
      <ObjectRow
        label={label}
        name={
          selected?.name ||
          (loading ? "正在读取…" : value ? "所选资产不可用" : "尚未选择")
        }
        version={selected?.version}
        description={
          error ||
          (!loading && !options.length ? (
            <span>暂无可用选项。{emptyAction}</span>
          ) : (
            description
          ))
        }
        action={
          <button
            type="button"
            className="object-change"
            aria-label={`更改${label}`}
            aria-haspopup="dialog"
            disabled={loading || !!error}
            onClick={() => {
              setDraft(selected?.id || "");
              setOpen(true);
            }}
          >
            更改 ›
          </button>
        }
      />
      {open && (
        <ObjectEditor title={`更改${label}`} onClose={() => setOpen(false)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              e.stopPropagation();
              if (!options.some((o) => o.id === draft)) return;
              onChange(draft);
              setOpen(false);
            }}
          >
            <label className="work-field">
              <span>{label}</span>
              <select
                autoFocus
                required
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
              >
                <option value="" disabled>
                  选择{label}
                </option>
                {options.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name}
                    {o.version ? ` / ${o.version}` : ""}
                  </option>
                ))}
              </select>
            </label>
            {!options.length && (
              <p className="muted">暂无可用选项。{emptyAction}</p>
            )}
            <div className="dialog-actions">
              <button
                type="button"
                className="button"
                onClick={() => setOpen(false)}
              >
                取消
              </button>
              <button
                className="button primary"
                disabled={!options.some((o) => o.id === draft)}
              >
                确认更改
              </button>
            </div>
          </form>
        </ObjectEditor>
      )}
    </>
  );
}
