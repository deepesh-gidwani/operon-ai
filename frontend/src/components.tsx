import { useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type {
  ActionItem,
  AgentState,
  ChartSpec,
  ColumnInfo,
  Insight,
  KPI,
  MetricValue,
  Report,
  StateTransition,
  TaskName,
  TaskState,
} from './types';

/* ---------- shared helpers ---------- */

function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const s = ms / 1000;
  if (s < 60) return s < 10 ? `${s.toFixed(1)}s` : `${Math.round(s)}s`;
  return `${Math.floor(s / 60)}m ${String(Math.round(s % 60)).padStart(2, '0')}s`;
}

function spanMs(start: string | null, end: string | null): number | null {
  if (!start || !end) return null;
  const ms = Date.parse(end) - Date.parse(start);
  return Number.isFinite(ms) && ms >= 0 ? ms : null;
}

/* ---------- state presentation ---------- */

const STATE_PILL: Record<TaskState, string> = {
  queued: 'bg-white/5 text-slate-400 border-edge',
  running: 'bg-accent/15 text-accent-soft border-accent/40',
  succeeded: 'bg-success/15 text-success border-success/40',
  failed: 'bg-danger/15 text-danger border-danger/40',
  skipped: 'bg-white/5 text-slate-500 border-edge',
};

const DOT: Record<TaskState, string> = {
  queued: 'bg-slate-600',
  running: 'bg-accent motion-safe:animate-pulse',
  succeeded: 'bg-success',
  failed: 'bg-danger',
  skipped: 'bg-slate-700',
};

function stateOf(transitions: StateTransition[], task: TaskName): TaskState {
  const last = [...transitions].reverse().find((t) => t.task === task);
  return last ? last.to_state : 'queued';
}

/* ---------- agent timeline ---------- */

function DataIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <ellipse cx="8" cy="3.5" rx="5.5" ry="2" />
      <path d="M2.5 3.5v9c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2v-9" />
      <path d="M2.5 8c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2" />
    </svg>
  );
}

function InsightIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M2 13.5h12" strokeLinecap="round" />
      <path d="M3.5 11V8.5M8 11V4.5M12.5 11V7" strokeLinecap="round" />
    </svg>
  );
}

function ActionIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M2.5 8h10M8.5 4.5 12.5 8l-4 3.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

const AGENTS: { id: TaskName; title: string; blurb: string; icon: () => JSX.Element }[] = [
  { id: 'data', title: 'Data Agent', blurb: 'Pandas profiling and metric evidence', icon: DataIcon },
  { id: 'insight', title: 'Insight Agent', blurb: 'Trend and anomaly claims from evidence', icon: InsightIcon },
  { id: 'action', title: 'Action Agent', blurb: 'Prioritized, evidence-linked recommendations', icon: ActionIcon },
];

export function AgentTimeline({
  transitions,
  agentStates,
  executing,
}: {
  transitions: StateTransition[];
  agentStates: AgentState[];
  executing: boolean;
}) {
  const totalMs = useMemo(() => {
    const starts = agentStates.map((s) => s.started_at).filter((v): v is string => !!v);
    const ends = agentStates.map((s) => s.finished_at).filter((v): v is string => !!v);
    if (!starts.length || !ends.length) return null;
    return spanMs(starts.sort()[0], ends.sort().reverse()[0]);
  }, [agentStates]);

  return (
    <div>
      {executing && (
        <p className="mb-3 rounded-lg border border-accent/40 bg-accent/10 px-3 py-2 text-xs leading-relaxed text-accent-soft">
          Pipeline executing on the server — agent states arrive with the completed report. Nothing here is
          simulated.
        </p>
      )}
      <ol className="space-y-2">
        {AGENTS.map((agent) => {
          const state = executing ? ('queued' as TaskState) : stateOf(transitions, agent.id);
          const info = agentStates.find((s) => s.task === agent.id);
          const ms = !executing && info ? spanMs(info.started_at, info.finished_at) : null;
          const Icon = agent.icon;
          return (
            <li
              key={agent.id}
              className="flex items-center gap-3 rounded-lg border border-edge bg-ink/50 px-3 py-2.5"
            >
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-raised text-slate-300">
                <Icon />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-display text-sm font-bold text-slate-100">{agent.title}</span>
                  <span className={`flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-semibold ${STATE_PILL[state]}`}>
                    <span className={`h-1.5 w-1.5 rounded-full ${DOT[state]}`} />
                    {state}
                  </span>
                  {ms !== null && <span className="font-mono text-xs text-slate-500">{formatDuration(ms)}</span>}
                </div>
                <p className="mt-0.5 truncate text-xs text-slate-500" title={agent.blurb}>
                  {agent.blurb}
                </p>
              </div>
            </li>
          );
        })}
      </ol>
      <div className="mt-2 flex items-center justify-between text-xs text-slate-500">
        <span>
          {transitions.length} trace event{transitions.length === 1 ? '' : 's'}
        </span>
        {totalMs !== null && <span className="font-mono">total {formatDuration(totalMs)}</span>}
      </div>
      {transitions.length > 0 && (
        <details className="mt-2 rounded-lg border border-edge bg-ink/50 px-3 py-2">
          <summary className="cursor-pointer text-xs font-medium text-slate-300">Execution trace</summary>
          <ul className="mt-2 space-y-1 font-mono text-xs text-slate-400">
            {transitions.map((t, i) => (
              <li key={i}>
                <span className="text-slate-600">{t.at.length >= 19 ? t.at.slice(11, 19) : t.at}</span>{' '}
                {t.task}: {t.from_state} → {t.to_state}
                {t.detail && <span className="text-slate-500"> — {t.detail}</span>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

/* ---------- KPIs ---------- */

export function KpiGrid({ kpis }: { kpis: KPI[] }) {
  return (
    <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
      {kpis.map((kpi) => (
        <div key={kpi.label} className="rounded-lg border border-edge bg-ink/50 px-4 py-3">
          <p className="text-xs font-medium text-slate-400">{kpi.label}</p>
          <p className="mt-1 truncate font-display text-xl font-bold text-slate-50" title={kpi.value}>
            {kpi.value}
          </p>
          {kpi.detail && (
            <p className="mt-0.5 truncate text-xs text-slate-500" title={kpi.detail}>
              {kpi.detail}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

/* ---------- interactive chart ---------- */

const CHART_COLORS = ['#4d84ff', '#3ecf8e', '#d9a13b', '#f26d6d'];

export function ReportChart({ chart }: { chart: ChartSpec }) {
  const Chart = chart.kind === 'line' ? LineChart : BarChart;
  const [visible, setVisible] = useState<string[]>(chart.y_keys);
  const [limit, setLimit] = useState<number | null>(null);

  const rangeOptions = useMemo(() => {
    const n = chart.data.length;
    if (n > 60) return [30, 60];
    if (n > 30) return [30];
    return [];
  }, [chart.data.length]);

  const effectiveLimit = limit ?? (chart.data.length > 60 ? 60 : chart.data.length);
  const data = chart.data.slice(-effectiveLimit);

  function toggleKey(key: string) {
    setVisible((prev) => {
      if (prev.includes(key)) {
        // Deselecting the last visible series resets to all — every control stays functional.
        return prev.length === 1 ? [...chart.y_keys] : prev.filter((k) => k !== key);
      }
      return [...prev, key];
    });
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="section-head">{chart.title}</h3>
        <span className="text-xs text-slate-500">
          pandas aggregation · {data.length} of {chart.data.length} points
        </span>
      </div>
      {(chart.y_keys.length > 1 || rangeOptions.length > 0) && (
        <div className="mb-3 flex flex-wrap items-center gap-1.5">
          {chart.y_keys.length > 1 &&
            chart.y_keys.map((k) => (
              <button
                key={k}
                className={`btn-small ${visible.includes(k) ? 'border-accent/50 text-accent-soft' : 'opacity-60'}`}
                onClick={() => toggleKey(k)}
                title={visible.includes(k) && visible.length === 1 ? 'Show all series' : `Toggle ${k}`}
              >
                {k}
              </button>
            ))}
          {rangeOptions.length > 0 && (
            <span className="ml-1 flex items-center gap-1.5">
              <span className="text-xs text-slate-600">show</span>
              {rangeOptions.map((n) => (
                <button
                  key={n}
                  className={`btn-small ${effectiveLimit === n ? 'border-accent/50 text-accent-soft' : ''}`}
                  onClick={() => setLimit(n)}
                >
                  {n}
                </button>
              ))}
              <button
                className={`btn-small ${effectiveLimit === chart.data.length ? 'border-accent/50 text-accent-soft' : ''}`}
                onClick={() => setLimit(chart.data.length)}
              >
                all
              </button>
            </span>
          )}
        </div>
      )}
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <Chart data={data} margin={{ top: 5, right: 10, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="#1e2635" strokeDasharray="3 3" />
            <XAxis dataKey={chart.x_key} tick={{ fill: '#64748b', fontSize: 11 }} tickLine={false} minTickGap={28} />
            <YAxis tick={{ fill: '#64748b', fontSize: 11 }} tickLine={false} width={64} />
            <Tooltip
              contentStyle={{ background: '#0f141e', border: '1px solid #1e2635', borderRadius: 8, fontSize: 12 }}
              labelStyle={{ color: '#e2e8f0' }}
            />
            {chart.kind === 'line'
              ? visible.map((k) => (
                  <Line
                    key={k}
                    type="monotone"
                    dataKey={k}
                    stroke={CHART_COLORS[chart.y_keys.indexOf(k) % CHART_COLORS.length]}
                    strokeWidth={2}
                    dot={false}
                  />
                ))
              : visible.map((k) => (
                  <Bar
                    key={k}
                    dataKey={k}
                    fill={CHART_COLORS[chart.y_keys.indexOf(k) % CHART_COLORS.length]}
                    radius={[4, 4, 0, 0]}
                  />
                ))}
          </Chart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/* ---------- metric references (resolved to real numbers) ---------- */

export function MetricRefs({ refs, metrics }: { refs: string[]; metrics: MetricValue[] }) {
  const byId = useMemo(() => new Map(metrics.map((m) => [m.id, m])), [metrics]);
  if (!refs.length) return null;
  return (
    <dl className="mt-2 space-y-1 rounded-md bg-raised/60 px-2.5 py-2">
      {refs.map((ref) => {
        const m = byId.get(ref);
        return (
          <div key={ref} className="flex flex-wrap items-baseline gap-x-2 text-xs">
            <dt className="font-mono text-accent-soft">{ref}</dt>
            <dd className="text-slate-400">{m ? m.detail : 'metric not in this run'}</dd>
          </div>
        );
      })}
    </dl>
  );
}

/* ---------- insights & actions ---------- */

export function InsightList({ insights, metrics }: { insights: Insight[]; metrics: MetricValue[] }) {
  if (!insights.length) return <p className="subtle">No insights generated for this run.</p>;
  return (
    <ol className="space-y-3">
      {insights.map((ins, i) => (
        <li key={i} className="rounded-lg border border-edge bg-ink/50 p-4">
          <p className="font-display text-sm font-bold text-slate-100">
            <span className="mr-2 font-mono text-accent-soft">{String(i + 1).padStart(2, '0')}</span>
            {ins.title}
          </p>
          <p className="mt-1.5 text-sm leading-relaxed text-slate-300">{ins.body}</p>
          {ins.evidence.length > 0 && (
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {ins.evidence.map((ev, j) => (
                <span key={j} className="rounded-md bg-success/10 px-2 py-1 font-mono text-xs text-success">
                  {ev}
                </span>
              ))}
            </div>
          )}
          <MetricRefs refs={ins.metric_refs} metrics={metrics} />
        </li>
      ))}
    </ol>
  );
}

const EFFORT_STYLE: Record<ActionItem['effort'], string> = {
  low: 'bg-success/15 text-success',
  medium: 'bg-white/10 text-slate-300',
  high: 'bg-warn/15 text-warn',
};

export function ActionList({ actions, metrics }: { actions: ActionItem[]; metrics: MetricValue[] }) {
  if (!actions.length) return <p className="subtle">No actions generated for this run.</p>;
  return (
    <ol className="space-y-3">
      {actions.map((a) => (
        <li key={a.rank} className="flex gap-3 rounded-lg border border-edge bg-ink/50 p-4">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-accent font-display text-sm font-bold text-white">
            {a.rank}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <p className="font-display text-sm font-bold text-slate-100">{a.title}</p>
              <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${EFFORT_STYLE[a.effort]}`}>
                {a.effort} effort
              </span>
            </div>
            <p className="mt-1 text-sm leading-relaxed text-slate-300">{a.body}</p>
            {a.expected_impact && (
              <p className="mt-1.5 text-sm text-slate-400">
                <span className="font-medium text-slate-300">Expected impact:</span> {a.expected_impact}
              </p>
            )}
            {a.uncertainty && (
              <p className="mt-1 text-sm text-slate-500">
                <span className="font-medium text-slate-400">Uncertainty:</span> {a.uncertainty}
              </p>
            )}
            <MetricRefs refs={a.evidence_refs} metrics={metrics} />
          </div>
        </li>
      ))}
    </ol>
  );
}

/* ---------- source data preview ---------- */

export function PreviewTable({
  columns,
  preview,
}: {
  columns: ColumnInfo[];
  preview: Record<string, unknown>[];
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-edge">
      <table className="w-full text-left text-xs">
        <thead>
          <tr className="bg-ink/70 text-slate-400">
            {columns.map((c) => (
              <th
                key={c.name}
                className="whitespace-nowrap px-3 py-2 font-medium"
                title={`${c.dtype} · ${c.unique} unique · ${c.missing} missing`}
              >
                {c.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {preview.map((row, i) => (
            <tr key={i} className="border-t border-edge text-slate-300">
              {columns.map((c) => (
                <td key={c.name} className="max-w-[160px] truncate px-3 py-1.5 font-mono">
                  {row[c.name] === null || row[c.name] === undefined ? (
                    <span className="text-slate-600">—</span>
                  ) : (
                    String(row[c.name])
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ---------- provenance ---------- */

export function Provenance({
  report,
  filename,
  traceEvents,
}: {
  report: Report;
  filename: string | null;
  traceEvents: number;
}) {
  const rows: [string, string][] = [
    ['Source file', filename ?? 'Unknown file'],
    ['Dataset', `${report.profile.rows.toLocaleString()} rows · ${report.profile.columns.length} columns`],
    ['Run', report.run_id],
    ['Model', report.model],
    [
      'Execution plan',
      report.plan
        ? `${report.plan.selected_analyses.length} analyses · focus: ${report.plan.insight_focus.join(', ') || 'general'}`
        : 'Not recorded',
    ],
    ['Evidence', `${report.metrics.length} deterministic metrics · ${traceEvents} trace events`],
  ];
  return (
    <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
      {rows.map(([k, v]) => (
        <div key={k} className="flex flex-col gap-0.5 border-b border-edge/60 pb-2">
          <dt className="text-xs font-medium text-slate-500">{k}</dt>
          <dd className="truncate font-mono text-xs text-slate-300" title={v}>
            {v}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/* ---------- empty / loading / error states ---------- */

export function EmptyState() {
  return (
    <div className="card py-10">
      <h2 className="text-center font-display text-lg font-bold text-slate-100">Three agents, one report</h2>
      <p className="subtle mx-auto mt-1 max-w-md text-center">
        Upload a CSV, describe the outcome you want, and run the pipeline. Every number below comes from your
        data or the model run — nothing is prefabricated.
      </p>
      <ol className="mx-auto mt-5 max-w-2xl space-y-2">
        {[
          ['01 · Data Agent', 'Validates and profiles your CSV — real pandas statistics.'],
          ['02 · Insight Agent', 'muse-spark-1.3 finds patterns tied to your objective.'],
          ['03 · Action Agent', 'Ranks concrete next steps by impact and effort.'],
        ].map(([t, d]) => (
          <li key={t} className="flex items-baseline gap-3 rounded-lg border border-edge bg-ink/50 px-4 py-2.5">
            <span className="shrink-0 font-mono text-xs text-accent-soft">{t}</span>
            <span className="text-sm text-slate-400">{d}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

export function LoadingState({ label }: { label: string }) {
  return (
    <div className="card flex items-center gap-3 py-6" role="status" aria-live="polite">
      <span
        className="h-5 w-5 shrink-0 animate-spin rounded-full border-2 border-edge border-t-accent motion-reduce:animate-none"
        aria-hidden="true"
      />
      <p className="text-sm text-slate-300">{label}</p>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-xl border border-danger/40 bg-danger/10 px-4 py-3" role="alert">
      <p className="text-sm font-medium text-danger">Something went wrong</p>
      <p className="mt-0.5 text-sm text-slate-300">{message}</p>
      {onRetry && (
        <button className="btn-small mt-2" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}
