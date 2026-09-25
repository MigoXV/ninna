import { useCallback, useEffect, useRef, useState } from "react";
export async function api<T = any>(path: string, body?: unknown): Promise<T> {
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
    const error = await response
      .json()
      .catch(() => ({ detail: response.statusText }));
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : JSON.stringify(error.detail),
    );
  }
  return response.json();
}
export function useData<T>(path: string, interval = 0) {
  const [data, setData] = useState<T>(),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  const active = useRef(0);
  const requestId = useRef(0);
  const refresh = useCallback(async () => {
    const generation = active.current;
    const ticket = ++requestId.current;
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
      if (generation === active.current && ticket === requestId.current)
        setLoading(false);
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
  return { data, error, loading, refresh };
}
