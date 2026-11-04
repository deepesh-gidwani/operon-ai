import { useCallback, useEffect, useRef, useState } from 'react';
import { analyze, downloadReport, fetchSampleFile, getHealth, uploadCsv } from './api';
import {
  ActionList,
  AgentTimeline,
  EmptyState,
  ErrorState,
  InsightList,
  KpiGrid,
  LoadingState,
  PreviewTable,
  Provenance,
  ReportChart,
} from './components';
import type { AnalyzeResponse, Health, UploadResponse } from './types';

const OBJECTIVE_EXAMPLES = [
  'Grow revenue next quarter — which regions, products and channels should we double down on?',
  'Cut costs without hurting sales: where is spend least efficient?',
  'Find our best customer segments and how to reach more of them.',
];

const NAV = [
  { id: 'setup', label: 'Setup' },
  { id: 'pipeline', label: 'Pipeline' },
  { id: 'report', label: 'Report' },
  { id: 'data', label: 'Data' },
] as const;

interface RunEntry {
  response: AnalyzeResponse;
  filename: string;
  at: string;
}

function scrollToSection(id: string) {
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  document.getElementById(id)?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
}

function StatusPill({ health, onRefresh }: { health: Health | null; onRefresh: () => void }) {
  const state = !health ? 'offline' : health.llm_configured ? 'ready' : 'no-key';
  const label = state === 'ready' ? 'LLM ready' : state === 'no-key' ? 'No API key' : 'Backend offline';
  const style =
    state === 'ready'
      ? 'border-success/40 text-success'
      : state === 'no-key'
        ? 'border-warn/40 text-warn'
        : 'border-danger/40 text-danger';
  const dot = state === 'ready' ? 'bg-success' : state === 'no-key' ? 'bg-warn' : 'bg-danger';
  return (
    <button
      className={`flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium ${style}`}
      title="Refresh backend status"
      onClick={onRefresh}
    >
      <span className={`h-2 w-2 rounded-full ${dot}`} />
      {label}
    </button>
  );
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [upload, setUpload] = useState<UploadResponse | null>(null);
  const [objective, setObjective] = useState(OBJECTIVE_EXAMPLES[0]);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [runs, setRuns] = useState<RunEntry[]>([]);
  const [busy, setBusy] = useState<'upload' | 'sample' | 'analyze' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const refreshHealth = useCallback(() => {
    getHealth().then(setHealth).catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    refreshHealth();
  }, [refreshHealth]);

  const currentFilename = result
    ? (runs.find((r) => r.response.run_id === result.run_id)?.filename ?? upload?.filename ?? null)
    : (upload?.filename ?? null);

  const handleFile = useCallback(async (file: File) => {
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setError('Only .csv files are accepted.');
      return;
    }
    setBusy('upload');
    setError(null);
    setResult(null);
    try {
      setUpload(await uploadCsv(file));
    } catch (e) {
      setUpload(null);
      setError(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setBusy(null);
    }
  }, []);

  const handleSample = useCallback(async () => {
    setBusy('sample');
    setError(null);
    setResult(null);
    try {
      setUpload(await uploadCsv(await fetchSampleFile()));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load sample data');
    } finally {
      setBusy(null);
    }
  }, []);

  const handleAnalyze = useCallback(async () => {
    if (!upload || busy !== null) return;
    if (objective.trim().length < 10) {
      setError('Describe your objective in at least 10 characters.');
      return;
    }
    setBusy('analyze');
    setError(null);
    scrollToSection('pipeline');
    try {
      const response = await analyze(upload.dataset_id, objective.trim());
      const entry: RunEntry = {
        response,
        filename: upload.filename,
        at: new Date().toLocaleTimeString(),
      };
      setRuns((prev) => [entry, ...prev].slice(0, 10));
      setResult(response);
      refreshHealth();
      scrollToSection('report');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Analysis failed');
    } finally {
      setBusy(null);
    }
  }, [upload, objective, busy, refreshHealth]);

  const selectRun = useCallback(
    (runId: string) => {
      const entry = runs.find((r) => r.response.run_id === runId);
      if (!entry) return;
      setError(null);
      setResult(entry.response);
      scrollToSection('report');
    },
    [runs],
  );

  return (
    <div className="min-h-screen lg:flex">
      {/* ---------- left navigation ---------- */}
      <aside className="hidden w-64 shrink-0 flex-col gap-5 border-r border-edge bg-panel/60 px-4 py-5 lg:flex">
        <div className="flex items-center gap-3 px-1">
          <svg width="34" height="34" viewBox="0 0 36 36" aria-hidden="true">
            <rect x="2" y="2" width="32" height="32" rx="8" fill="#4d84ff" />
            <circle cx="18" cy="18" r="6.5" fill="none" stroke="#090c12" strokeWidth="3" />
            <circle cx="18" cy="18" r="1.8" fill="#090c12" />
            <circle cx="28.5" cy="9.5" r="2.4" fill="#090c12" />
          </svg>
          <div>
            <p className="font-display text-base font-extrabold tracking-tight text-slate-50">OPERON AI</p>
            <p className="text-xs text-slate-500">Intelligence, Orchestrated.</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 px-1">
          <span className="rounded-md border border-edge bg-ink/60 px-2.5 py-1 font-mono text-xs text-slate-300">
            {health?.model ?? 'muse-spark-1.3'}
          </span>
          <StatusPill health={health} onRefresh={refreshHealth} />
        </div>

        <nav className="space-y-1" aria-label="Sections">
          {NAV.map((item) => (
            <button key={item.id} className="nav-link w-full" onClick={() => scrollToSection(item.id)}>
              {item.label}
            </button>
          ))}
        </nav>

        <div className="min-h-0 flex-1">
          <p className="section-label px-3">Runs this session</p>
          {runs.length === 0 ? (
            <p className="subtle mt-2 px-3 text-xs">No runs yet. Completed analyses appear here.</p>
          ) : (
            <ul className="mt-2 space-y-1 overflow-y-auto">
              {runs.map((run) => (
                <li key={run.response.run_id}>
                  <button
                    className={`nav-link w-full text-left ${result?.run_id === run.response.run_id ? 'nav-link-active' : ''}`}
                    onClick={() => selectRun(run.response.run_id)}
                    title={run.response.report.objective}
                  >
                    <span
                      className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                        run.response.status === 'complete' ? 'bg-success' : 'bg-warn'
                      }`}
                    />
                    <span className="min-w-0">
                      <span className="block truncate">{run.response.report.objective}</span>
                      <span className="block font-mono text-xs text-slate-500">
                        {run.response.run_id} · {run.at}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <p className="px-3 text-xs leading-relaxed text-slate-600">
          Meta Global AI Developer Hackathon 2026 · All LLM inference via Meta Model API
        </p>
      </aside>

      {/* ---------- main column ---------- */}
      <div className="min-w-0 flex-1">
        {/* mobile top bar */}
        <header className="border-b border-edge bg-panel/60 px-4 py-3 lg:hidden">
          <div className="flex items-center gap-2">
            <p className="font-display text-base font-extrabold tracking-tight text-slate-50">OPERON AI</p>
            <div className="ml-auto">
              <StatusPill health={health} onRefresh={refreshHealth} />
            </div>
          </div>
          <nav className="mt-2 flex gap-1 overflow-x-auto" aria-label="Sections">
            {NAV.map((item) => (
              <button key={item.id} className="nav-link shrink-0" onClick={() => scrollToSection(item.id)}>
                {item.label}
              </button>
            ))}
          </nav>
        </header>

        <main className="mx-auto max-w-6xl space-y-4 px-4 py-6 sm:px-6">
          {health === null && (
            <ErrorState
              message="Backend is unreachable at /api. Start it with: cd backend, then uvicorn app.main:app --port 8000."
              onRetry={refreshHealth}
            />
          )}
          {error && (
            <ErrorState
              message={error}
              onRetry={busy === null && upload && !result ? handleAnalyze : undefined}
            />
          )}

          {/* ---------- setup ---------- */}
          <section id="setup" className="grid scroll-mt-4 grid-cols-1 gap-4 xl:grid-cols-2">
            <div className="card">
              <h2 className="section-head">Data source</h2>
              <p className="subtle mt-1">Drop a CSV file or browse to upload it.</p>
              <div
                role="button"
                tabIndex={0}
                aria-label="Upload a CSV file"
                className={`mt-3 cursor-pointer rounded-lg border border-dashed px-4 py-6 text-center transition ${
                  dragActive ? 'border-accent bg-accent/10' : 'border-edge bg-ink/50 hover:border-accent'
                }`}
                onClick={() => fileInput.current?.click()}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') fileInput.current?.click();
                }}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragActive(true);
                }}
                onDragLeave={() => setDragActive(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragActive(false);
                  const f = e.dataTransfer.files?.[0];
                  if (f && busy === null) void handleFile(f);
                }}
              >
                <span className="text-sm font-medium text-slate-200">
                  {busy === 'upload' ? 'Uploading…' : dragActive ? 'Release to upload' : 'Choose a CSV file'}
                </span>
                <input
                  ref={fileInput}
                  type="file"
                  accept=".csv"
                  className="hidden"
                  disabled={busy !== null}
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) void handleFile(f);
                    e.target.value = '';
                  }}
                />
              </div>
              <button className="btn-ghost mt-2 w-full" disabled={busy !== null} onClick={() => void handleSample()}>
                {busy === 'sample' ? 'Loading…' : 'Load Sample Dataset'}
              </button>
              {upload && (
                <div className="mt-3 rounded-lg border border-edge bg-ink/50 p-3 text-sm">
                  <p className="font-medium text-slate-100">{upload.filename}</p>
                  <p className="subtle mt-0.5">
                    {upload.rows.toLocaleString()} rows · {upload.columns.length} columns
                  </p>
                </div>
              )}
            </div>

            <div className="card">
              <h2 className="section-head">Business objective</h2>
              <p className="subtle mt-1">State the outcome you want in plain language.</p>
              <textarea
                className="field mt-3 min-h-24"
                rows={4}
                value={objective}
                onChange={(e) => setObjective(e.target.value)}
                placeholder="e.g. Grow revenue next quarter…"
              />
              <div className="mt-2 space-y-1">
                {OBJECTIVE_EXAMPLES.map((ex) => (
                  <button
                    key={ex}
                    className="block w-full truncate rounded-md px-2 py-1 text-left text-xs text-slate-500 hover:bg-white/5 hover:text-slate-300"
                    title={ex}
                    onClick={() => setObjective(ex)}
                  >
                    {ex}
                  </button>
                ))}
              </div>
              <button className="btn-primary mt-3" disabled={busy !== null || !upload} onClick={() => void handleAnalyze()}>
                {busy === 'analyze' ? 'Agents running…' : 'Run analysis'}
              </button>
              {!upload && <p className="subtle mt-2 text-center">Upload data first to enable analysis.</p>}
            </div>
          </section>

          {/* ---------- pipeline ---------- */}
          <section id="pipeline" className="card scroll-mt-4">
            <h2 className="section-head">Agent pipeline</h2>
            <div className="mt-3">
              {busy === 'analyze' ? (
                <AgentTimeline transitions={[]} agentStates={[]} executing />
              ) : result ? (
                <AgentTimeline
                  transitions={result.transitions}
                  agentStates={result.report.agent_states}
                  executing={false}
                />
              ) : (
                <p className="subtle">
                  No run yet. Agent states — queued, running, succeeded, failed, skipped — appear here with
                  timings once a real analysis executes.
                </p>
              )}
            </div>
          </section>

          {/* ---------- report ---------- */}
          <section id="report" className="scroll-mt-4 space-y-4">
            {!result && busy !== 'analyze' && <EmptyState />}
            {busy === 'analyze' && !result && (
              <LoadingState label="Agents are executing on the server. The full report renders when the run completes." />
            )}
            {result && (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={`rounded-md px-2.5 py-1 font-display text-xs font-bold ${
                      result.status === 'complete' ? 'bg-success text-ink' : 'bg-warn text-ink'
                    }`}
                  >
                    {result.status === 'complete' ? 'COMPLETE' : 'PARTIAL'}
                  </span>
                  <span className="subtle">
                    Run {result.run_id} · model {result.report.model}
                  </span>
                  {runs.length > 1 && (
                    <select
                      className="btn-small ml-auto bg-panel"
                      aria-label="View a previous run"
                      value={result.run_id}
                      onChange={(e) => selectRun(e.target.value)}
                    >
                      {runs.map((run) => (
                        <option key={run.response.run_id} value={run.response.run_id}>
                          {run.response.run_id} · {run.response.status}
                        </option>
                      ))}
                    </select>
                  )}
                  <button
                    className={`btn-ghost ${runs.length > 1 ? '' : 'ml-auto'}`}
                    onClick={() => void downloadReport(result.run_id)}
                  >
                    Export report (.md)
                  </button>
                </div>

                {result.report.warnings.length > 0 && (
                  <div className="rounded-xl border border-warn/40 bg-warn/10 px-4 py-3 text-sm text-warn">
                    {result.report.warnings.map((w, i) => (
                      <p key={i}>{w}</p>
                    ))}
                    {!health?.llm_configured && (
                      <p className="mt-1 text-slate-300">
                        Set MODEL_API_KEY in backend/.env and restart the backend for full LLM insights.
                      </p>
                    )}
                  </div>
                )}

                <div className="card">
                  <h2 className="section-head">Key figures</h2>
                  <div className="mt-3">
                    <KpiGrid kpis={result.report.kpis} />
                  </div>
                </div>

                <div className="card">
                  <ReportChart chart={result.report.chart} />
                </div>

                <div className="card">
                  <h2 className="section-head">Data brief</h2>
                  <p className="mt-2 text-sm leading-relaxed text-slate-300">
                    {result.report.profile.data_brief || 'Unavailable for this run.'}
                  </p>
                  {result.report.plan && (
                    <p className="mt-2 text-sm leading-relaxed text-slate-500">
                      <span className="font-medium text-slate-400">Plan: </span>
                      {result.report.plan.rationale}
                    </p>
                  )}
                </div>

                <div className="card">
                  <h2 className="section-head">Insights</h2>
                  <div className="mt-3">
                    <InsightList insights={result.report.insights} metrics={result.report.metrics} />
                  </div>
                </div>

                <div className="card">
                  <h2 className="section-head">Recommended actions</h2>
                  <div className="mt-3">
                    <ActionList actions={result.report.actions} metrics={result.report.metrics} />
                  </div>
                </div>

                <div className="card">
                  <h2 className="section-head">Data provenance</h2>
                  <div className="mt-3">
                    <Provenance
                      report={result.report}
                      filename={currentFilename}
                      traceEvents={result.transitions.length}
                    />
                  </div>
                </div>
              </>
            )}
          </section>

          {/* ---------- data ---------- */}
          <section id="data" className="card scroll-mt-4">
            <h2 className="section-head">Source data</h2>
            {!upload ? (
              <p className="subtle mt-1">Upload a CSV or load the sample dataset to preview it here.</p>
            ) : (
              <>
                <p className="subtle mt-1">
                  {upload.filename} · showing {upload.preview.length} of {upload.rows.toLocaleString()} rows
                </p>
                <div className="mt-3">
                  <PreviewTable columns={upload.columns} preview={upload.preview} />
                </div>
              </>
            )}
          </section>
        </main>

        <footer className="mx-auto max-w-6xl px-4 pb-8 sm:px-6 lg:hidden">
          <p className="text-xs text-slate-600">
            Operon AI · Meta Global AI Developer Hackathon 2026 · All LLM inference via Meta Model API
            (muse-spark-1.3)
          </p>
        </footer>
      </div>
    </div>
  );
}
