export type Project = {
  id: string;
  name: string;
  description: string;
  created_at: string;
  run_count: number;
  active_count: number;
  last_run_at: string | null;
};
export type Ref = { name: string; version: string };
export type Asset = {
  id: string;
  name: string;
  version: string;
  metadata: Record<string, unknown>;
  [key: string]: any;
};
export type Run = {
  project_id: string;
  id: string;
  status: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  container_id: string | null;
  exit_code: number | null;
  failure_reason: string | null;
  monitor_error: string | null;
  cancel_requested: boolean;
  training_spec: { dataset: Ref; model: Ref; recipe: Ref };
  execution_spec: {
    runtime: Ref;
    workspace: { name: string; snapshot: string };
    resources: {
      device: string;
      gpu_count: number;
      cpu_threads: number;
      memory_mb: number;
    };
  };
  assets: Record<string, Asset>;
  metrics: any;
  metadata: Record<string, unknown>;
  artifacts: { name: string; size: number; sha256: string }[];
  events: { from: string; to: string; at: string }[];
};
