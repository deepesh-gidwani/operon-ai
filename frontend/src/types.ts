export type TaskName = 'data' | 'insight' | 'action';
export type TaskState = 'queued' | 'running' | 'succeeded' | 'failed' | 'skipped';

export interface StateTransition {
  task: TaskName;
  from_state: TaskState;
  to_state: TaskState;
  at: string;
  detail: string;
}

export interface AgentState {
  task: TaskName;
  state: TaskState;
  started_at: string | null;
  finished_at: string | null;
  detail: string;
}

export interface ColumnInfo {
  name: string;
  dtype: string;
  missing: number;
  missing_pct: number;
  unique: number;
}

export interface UploadResponse {
  dataset_id: string;
  filename: string;
  rows: number;
  columns: ColumnInfo[];
  preview: Record<string, unknown>[];
}

export interface KPI {
  label: string;
  value: string;
  detail: string;
}

export interface ChartSpec {
  kind: 'line' | 'bar';
  title: string;
  x_key: string;
  y_keys: string[];
  data: Record<string, string | number>[];
}

export interface MetricValue {
  id: string;
  label: string;
  function: string;
  column: string | null;
  value: unknown;
  detail: string;
}

export interface PlannedAnalysis {
  function: string;
  column: string | null;
  secondary_column: string | null;
  label: string;
  reason: string;
}

export interface ExecutionPlan {
  objective: string;
  rationale: string;
  selected_analyses: PlannedAnalysis[];
  insight_focus: string[];
  max_insights: number;
  max_actions: number;
}

export interface DataProfile {
  rows: number;
  columns: ColumnInfo[];
  data_brief: string;
}

export interface Insight {
  title: string;
  body: string;
  evidence: string[];
  metric_refs: string[];
}

export interface ActionItem {
  rank: number;
  title: string;
  body: string;
  expected_impact: string;
  effort: 'low' | 'medium' | 'high';
  evidence_refs: string[];
  uncertainty: string;
}

export interface Report {
  run_id: string;
  dataset_id: string;
  objective: string;
  status: 'complete' | 'partial';
  model: string;
  kpis: KPI[];
  chart: ChartSpec;
  profile: DataProfile;
  insights: Insight[];
  actions: ActionItem[];
  warnings: string[];
  plan: ExecutionPlan | null;
  metrics: MetricValue[];
  agent_states: AgentState[];
}

export interface AnalyzeResponse {
  run_id: string;
  status: 'complete' | 'partial';
  transitions: StateTransition[];
  report: Report;
}

export interface Health {
  status: string;
  model: string;
  llm_configured: boolean;
  datasets: number;
  runs: number;
}
