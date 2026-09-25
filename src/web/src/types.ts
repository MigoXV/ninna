export type Ref = { name: string; version: string };
export type Asset = {
  id: string;
  name: string;
  version: string;
  metadata: Record<string, unknown>;
  [key: string]: any;
};
export type Run = {
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
export type Cert = {
  id: string;
  status: string;
  profile: string;
  created_at: string;
  finished_at: string | null;
  threshold: number;
  checks: { name: string; status: string; evidence: any }[];
  run_ids: string[];
  failure_reason: string | null;
};
