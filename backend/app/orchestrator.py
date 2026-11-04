"""Orchestrator: interprets the objective, plans analyses, routes tasks.

Pipeline: plan -> Data agent -> Insight agent -> Action agent. Every real
state transition is logged; nothing is fabricated. If the LLM is unavailable,
the deterministic analytics still ship in a PARTIAL report.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pandas as pd

from . import analytics
from .agents import ActionAgent, DataAgent, InsightAgent
from .meta_client import MetaAPIError, MetaClient
from .models import (
    ActionItem,
    AgentState,
    AnalyzeResponse,
    DataProfile,
    EvidenceBundle,
    ExecutionPlan,
    Insight,
    PlannedAnalysis,
    Report,
    StateTransition,
    TaskName,
    TaskState,
)

TASK_ORDER: tuple[TaskName, ...] = ("data", "insight", "action")

# In-memory stores (SQLite unnecessary for an MVP demo; no data persists).
DATASETS: dict[str, pd.DataFrame] = {}
DATASET_NAMES: dict[str, str] = {}
REPORTS: dict[str, Report] = {}

_VALUE_HINTS = ("revenue", "sales", "amount", "profit", "total", "price", "cost", "units")
_FOCUS_KEYWORDS = (
    "revenue",
    "sales",
    "profit",
    "cost",
    "churn",
    "growth",
    "units",
    "region",
    "channel",
    "product",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _Tracker:
    """Records real state transitions as tasks execute."""

    def __init__(self) -> None:
        self.states: dict[TaskName, TaskState] = {t: "queued" for t in TASK_ORDER}
        self.transitions: list[StateTransition] = []
        self.started: dict[TaskName, str] = {}
        self.finished: dict[TaskName, str] = {}

    def move(self, task: TaskName, to_state: TaskState, detail: str = "") -> None:
        frm = self.states[task]
        self.states[task] = to_state
        at = _now()
        if to_state == "running":
            self.started[task] = at
        if to_state in ("succeeded", "failed", "skipped"):
            self.finished[task] = at
        self.transitions.append(
            StateTransition(task=task, from_state=frm, to_state=to_state, at=at, detail=detail)
        )

    def agent_states(self) -> list[AgentState]:
        out = []
        for task in TASK_ORDER:
            last_detail = ""
            for t in self.transitions:
                if t.task == task:
                    last_detail = t.detail
            out.append(
                AgentState(
                    task=task,
                    state=self.states[task],
                    started_at=self.started.get(task),
                    finished_at=self.finished.get(task),
                    detail=last_detail,
                )
            )
        return out


def _pick_value_column(df: pd.DataFrame) -> str | None:
    numerics = [str(c) for c in df.select_dtypes(include="number").columns]
    if not numerics:
        return None
    lowered = {c: c.lower() for c in numerics}
    for hint in _VALUE_HINTS:
        for col, low in lowered.items():
            if hint in low:
                return col
    return numerics[0]


def _categorical_columns(df: pd.DataFrame, limit: int = 3) -> list[str]:
    cats = [
        str(c)
        for c in df.columns
        if df[c].dtype == object or str(df[c].dtype) == "category"
    ]
    cats.sort(key=lambda c: df[c].nunique(dropna=True))
    return [c for c in cats if df[c].nunique(dropna=True) <= 100][:limit]


def build_execution_plan(objective: str, df: pd.DataFrame) -> ExecutionPlan:
    """Interpret the objective + CSV shape into a structured analysis plan.

    Deterministic: keyword matching over the objective and dtype inspection of
    the dataframe. Only allowlisted function names are ever selected.
    """
    lowered = objective.lower()
    ops: list[PlannedAnalysis] = [
        PlannedAnalysis(function="row_count", label="Count rows", reason="Dataset size")
    ]
    focus = [kw for kw in _FOCUS_KEYWORDS if kw in lowered]

    numerics = [str(c) for c in df.select_dtypes(include="number").columns]
    value_col = _pick_value_column(df)
    ordered = ([value_col] if value_col else []) + [c for c in numerics if c != value_col]
    for col in ordered[:3]:
        ops.append(
            PlannedAnalysis(
                function="numeric_summary",
                column=col,
                label=f"Summarize {col}",
                reason="Baseline distribution for a numeric field",
            )
        )
    for col in _categorical_columns(df):
        ops.append(
            PlannedAnalysis(
                function="top_values",
                column=col,
                label=f"Top values of {col}",
                reason="Find dominant segments",
            )
        )

    date_col = analytics.detect_date_column(df)
    if date_col and value_col:
        ops.append(
            PlannedAnalysis(
                function="trend_daily",
                column=date_col,
                secondary_column=value_col,
                label=f"Daily trend of {value_col}",
                reason="Objective asks about change over time" if not focus else "Track performance over time",
            )
        )
    if value_col:
        for col in _categorical_columns(df, limit=2):
            ops.append(
                PlannedAnalysis(
                    function="groupby_sum",
                    column=col,
                    secondary_column=value_col,
                    label=f"Sum of {value_col} by {col}",
                    reason="Compare segments on the key metric",
                )
            )
    if len(numerics) >= 2:
        ops.append(
            PlannedAnalysis(
                function="correlation",
                column=numerics[0],
                secondary_column=numerics[1],
                label=f"Correlate {numerics[0]} vs {numerics[1]}",
                reason="Surface relationships between drivers",
            )
        )

    rationale = (
        f"Objective mentions: {', '.join(focus) or 'general performance'}. "
        f"Dataset has {df.shape[0]:,} rows, {len(numerics)} numeric column(s)"
        + (f"; key metric '{value_col}'" if value_col else "")
        + (f"; date column '{date_col}'" if date_col else "")
        + "."
    )
    return ExecutionPlan(
        objective=objective,
        rationale=rationale,
        selected_analyses=ops[:14],
        insight_focus=focus or ["overall performance"],
    )


def _profile_context(profile: DataProfile) -> str:
    lines = [f"rows={profile.rows}, columns={[c.name for c in profile.columns]}"]
    for col, stats in profile.numeric_summary.items():
        lines.append(f"numeric[{col}]={stats}")
    for col, vals in profile.top_values.items():
        lines.append(f"top[{col}]={vals}")
    if profile.date_column:
        lines.append(f"date_column={profile.date_column}, trend_points={len(profile.trend)}")
    if profile.correlations:
        lines.append(f"correlations={profile.correlations}")
    return "\n".join(lines)


def run_analysis_on_df(
    df: pd.DataFrame,
    dataset_id: str,
    objective: str,
    meta: MetaClient | None = None,
) -> AnalyzeResponse:
    """Execute plan -> data -> insight -> action with a real transition log."""
    meta = meta or MetaClient()
    data_agent, insight_agent, action_agent = DataAgent(), InsightAgent(), ActionAgent()
    tracker = _Tracker()
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    warnings: list[str] = []

    plan = build_execution_plan(objective, df)
    bundle = EvidenceBundle()
    profile: DataProfile | None = None
    insights: list[Insight] = []
    actions: list[ActionItem] = []

    # --- Data task (deterministic pandas evidence + LLM brief) ---
    tracker.move("data", "running", "Profiling dataset with pandas")
    try:
        profile = data_agent.profile(df)
        bundle = data_agent.collect(df, plan)
        warnings.extend(bundle.warnings)
        profile.data_brief = data_agent.write_brief(objective, bundle, meta)
        tracker.move("data", "succeeded", f"{profile.rows} rows, {len(bundle.metrics)} metrics")
    except MetaAPIError as exc:
        # Deterministic part is still real and usable; keep it, mark partial.
        if profile is None:
            profile = analytics.profile_dataframe(df)
        if not bundle.metrics:
            bundle = data_agent.collect(df, plan)
            warnings.extend(bundle.warnings)
        profile.data_brief = ""
        warnings.append(f"Data brief unavailable: {exc}")
        tracker.move("data", "failed", str(exc)[:200])

    assert profile is not None
    kpis = analytics.build_kpis(df, profile)
    chart = analytics.build_chart(df, profile)

    # --- Insight task ---
    if tracker.states["data"] == "failed" and not meta.configured:
        tracker.move("insight", "skipped", "No MODEL_API_KEY; LLM insights unavailable")
    else:
        tracker.move("insight", "running", "Generating evidence-backed insights")
        try:
            insights, ref_warnings = insight_agent.run(
                objective, profile.data_brief, bundle, profile, meta,
                max_insights=plan.max_insights,
            )
            warnings.extend(ref_warnings)
            tracker.move("insight", "succeeded", f"{len(insights)} insights")
        except MetaAPIError as exc:
            warnings.append(f"Insights unavailable: {exc}")
            tracker.move("insight", "failed", str(exc)[:200])

    # --- Action task ---
    if not insights:
        tracker.move("action", "skipped", "No insights to act on")
    else:
        tracker.move("action", "running", "Prioritizing recommended actions")
        try:
            actions, ref_warnings = action_agent.run(
                objective, profile.data_brief, insights, bundle, meta,
                max_actions=plan.max_actions,
            )
            warnings.extend(ref_warnings)
            tracker.move("action", "succeeded", f"{len(actions)} actions")
        except MetaAPIError as exc:
            warnings.append(f"Actions unavailable: {exc}")
            tracker.move("action", "failed", str(exc)[:200])

    status = "complete" if (insights and actions) else "partial"
    report = Report(
        run_id=run_id,
        dataset_id=dataset_id,
        objective=objective,
        status=status,
        model=meta.model,
        kpis=kpis,
        chart=chart,
        profile=profile,
        insights=insights,
        actions=actions,
        warnings=warnings,
        plan=plan,
        metrics=bundle.metrics,
        agent_states=tracker.agent_states(),
    )
    REPORTS[run_id] = report
    return AnalyzeResponse(run_id=run_id, status=status, transitions=tracker.transitions, report=report)


def run_analysis(dataset_id: str, objective: str, meta: MetaClient | None = None) -> AnalyzeResponse:
    """Execute the pipeline for a previously uploaded dataset."""
    if dataset_id not in DATASETS:
        raise KeyError(f"Unknown dataset_id: {dataset_id}")
    return run_analysis_on_df(DATASETS[dataset_id], dataset_id, objective, meta)
