# Operon AI — Hackathon Submission

**Tagline:** Intelligence, Orchestrated.

## Project description

Operon AI is a multi-agent business operations intelligence platform. A business user
uploads a CSV, states an objective in plain language ("Grow revenue next quarter —
which regions should we double down on?"), and three specialized agents produce a
structured report: deterministic metrics and KPIs, evidence-backed insights, and
prioritized recommended actions with expected impact and uncertainty.

What makes it trustworthy rather than a demo toy:

- **Real execution engine.** An orchestrator builds a typed execution plan from the
  objective and the CSV shape, then routes Data → Insight → Action, logging every
  genuine state transition with timings. The dashboard timeline renders only these
  real events.
- **Evidence grounding.** The Data Agent computes metrics with an allowlist of
  deterministic pandas functions — the model can never run code or invent numbers.
  Every insight and action cites metric ids that are validated against the computed
  evidence; unknown references are dropped, never rendered.
- **Meta-exclusive intelligence.** All generative AI flows through one client module
  to the Meta Model API using `muse-spark-1.3`. No other LLM provider appears in
  the codebase.
- **Honest failure.** Missing API keys, timeouts, malformed JSON, and bad uploads
  produce clear partial states and warnings — never fabricated progress or results.

## Implemented vs planned

### Implemented (shipped)

- Orchestrator with deterministic execution planning + sequential agent routing
- Data Agent: CSV validation, pandas profiling, 8 allowlisted metric functions
- Insight Agent (`muse-spark-1.3`): claims with quoted statistics + metric references
- Action Agent (`muse-spark-1.3`): ranked actions with impact, effort, uncertainty
- Typed Pydantic schemas for plans, metrics, insights, actions, agent states, reports
- Bounded retries for model timeouts / 429 / 5xx / malformed JSON
- REST API: health, upload, analyze (dataset or inline CSV), report fetch + Markdown export
- Dashboard: sidebar nav, CSV drop zone, sample dataset, real-state agent timeline with
  durations, 4 KPI cards, interactive revenue chart, insights, actions, provenance, export
- Empty / loading / success / error UI states; session run history
- 36 backend tests + strict TypeScript production build, all passing

### Planned (not built)

- Persistent storage (currently in-memory; restarts clear datasets and reports)
- Streaming agent progress (currently one synchronous request per analysis)
- Additional connectors (Excel, JSON, databases) beyond CSV upload
- Multi-chart reports and user-configurable KPIs
- Authentication, multi-user workspaces, and audit logging
- Conversation-style follow-up questions against a finished report
- Hosted production deployment (currently local run + static build)
