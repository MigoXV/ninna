import { useEffect, useLayoutEffect, useRef, useState } from "react";

// Session-local view state: never writes training assets or Run history.
export function useViewState<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const saved = sessionStorage.getItem("ninna.view." + key);
      return saved === null ? initial : (JSON.parse(saved) as T);
    } catch {
      return initial;
    }
  });
  useEffect(() => {
    try {
      sessionStorage.setItem("ninna.view." + key, JSON.stringify(value));
    } catch {
      /* Private browsing can disable storage. */
    }
  }, [key, value]);
  return [value, setValue] as const;
}

const positions = new Map<string, number>();
export function useRegionScroll(key: string, ready = true) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const node = ref.current;
    if (!node || !ready) return;
    node.scrollTop = positions.get(key) || 0;
    const save = () => positions.set(key, node.scrollTop);
    node.addEventListener("scroll", save, { passive: true });
    return () => {
      save();
      node.removeEventListener("scroll", save);
    };
  }, [key, ready]);
  return ref;
}
