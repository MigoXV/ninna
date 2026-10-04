import { useCallback, useEffect, useRef, useState } from "react";
// Keep the mutation identity when a response is lost and the user retries unchanged input.
const pendingMutations = new Map<string, string>();
export async function api<T = any>(path: string, body?: unknown): Promise<T> {
  let retryKey: string | undefined;
  if (body && typeof body === "object" && "request_id" in body) {
    const { request_id, ...payload } = body as Record<string, unknown>;
    retryKey = path + JSON.stringify(payload);
    const identity = pendingMutations.get(retryKey) || String(request_id);
    pendingMutations.set(retryKey, identity);
    body = { ...payload, request_id: identity };
  }
  const response = await fetch(
    "/api" + path,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  if (!response.ok) {
    if (retryKey && response.status < 500) pendingMutations.delete(retryKey);
    const error = await response
      .json()
      .catch(() => ({ detail: response.statusText }));
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : error.detail?.message || JSON.stringify(error.detail),
    );
  }
  const result = await response.json();
  if (retryKey) pendingMutations.delete(retryKey);
  return result;
}
export function useData<T>(path: string, interval = 0) {
  const [data, setData] = useState<T>(),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  const active = useRef(0);
  const requestId = useRef(0);
  const [refreshing, setRefreshing] = useState(false);
  const refresh = useCallback(async () => {
    const generation = active.current;
    const ticket = ++requestId.current;
    setRefreshing(true);
    try {
      const result = await api<T>(path);
      if (generation === active.current && ticket === requestId.current) {
        setData(result);
        setError("");
      }
    } catch (e) {
      if (generation === active.current && ticket === requestId.current)
        setError((e as Error).message);
    } finally {
      if (generation === active.current && ticket === requestId.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [path]);
  useEffect(() => {
    active.current++;
    setLoading(true);
    setData(undefined);
    setError("");
    void refresh();
    const timer = interval ? window.setInterval(refresh, interval) : undefined;
    return () => {
      active.current++;
      window.clearInterval(timer);
    };
  }, [refresh, interval]);
  return { data, error, loading, refreshing, refresh };
}
