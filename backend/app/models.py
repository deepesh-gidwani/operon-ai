"""Pydantic schemas for the Operon AI API.

All inter-agent payloads and all model responses are validated against these
schemas. Unknown metric references from the model are rejected, never trusted.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, BeforeValidator, Field, model_validator
from typing import Annotated

TaskName = Literal["data", "insight", "action"]
TaskState = Literal["queued", "running", "succeeded", "failed", "skipped"]


class StateTransition(BaseModel):
    task: TaskName
    from_state: TaskState
    to_state: TaskState
    at: str = Field(description="ISO-8601 UTC timestamp of the transition")
    detail: str = ""


# The execution trace returned with every report is the real transition log:
# entries are appended only as tasks genuinely move between states.
TraceEvent = StateTransition


class AgentState(BaseModel):
    task: TaskName
    state: TaskState
    started_at: str | None = None
    finished_at: str | None = None
    detail: str = ""


class ColumnInfo(BaseModel):
    name: str
    dtype: str
    missing: int
    missing_pct: float
    unique: int


class UploadResponse(BaseModel):
    dataset_id: str
    filename: str
    rows: int
    columns: list[ColumnInfo]
    preview: list[dict[str, Any]]


class AnalyzeRequest(BaseModel):
    dataset_id: str | None = None
    csv_text: str | None = Field(default=None, description="Inline CSV data")
    filename: str = "upload.csv"
    objective: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def _needs_dataset_or_csv(self) -> AnalyzeRequest:
        if not self.dataset_id and not (self.csv_text or "").strip():
            raise ValueError("Provide either dataset_id or csv_text.")
        return self


class PlannedAnalysis(BaseModel):
    function: str = Field(description="Name in the allowlisted analysis registry")
    column: str | None = None
    secondary_column: str | None = None
    label: str = ""
    reason: str = ""


class ExecutionPlan(BaseModel):
    objective: str
    rationale: str = ""
    selected_analyses: list[PlannedAnalysis] = []
    insight_focus: list[str] = []
    max_insights: int = 5
    max_actions: int = 5


class MetricValue(BaseModel):
    id: str = Field(description="Stable id, e.g. 'sum:revenue' or 'top:region'")
    label: str
    function: str
    column: str | None = None
    value: Any = None
    detail: str = ""


class EvidenceBundle(BaseModel):
    metrics: list[MetricValue] = []
    warnings: list[str] = []

    def ids(self) -> set[str]:
        return {m.id for m in self.metrics}


class DataProfile(BaseModel):
    rows: int
    columns: list[ColumnInfo]
    numeric_summary: dict[str, dict[str, float]]
    top_values: dict[str, list[dict[str, Any]]]
    date_column: str | None = None
    trend: list[dict[str, Any]] = []
    correlations: list[dict[str, Any]] = []
    data_brief: str = ""


class KPI(BaseModel):
    label: str
    value: str
    detail: str = ""


class ChartSpec(BaseModel):
    kind: Literal["line", "bar"]
    title: str
    x_key: str
    y_keys: list[str]
    data: list[dict[str, Any]]


class DataBriefResponse(BaseModel):
    data_brief: str = Field(min_length=1, max_length=3000)


class Insight(BaseModel):
    title: str
    body: str
    evidence: list[str] = []
    metric_refs: list[str] = Field(
        default_factory=list,
        description="Metric ids from the evidence bundle backing this claim",
    )


class InsightListResponse(BaseModel):
    insights: list[Insight] = Field(min_length=1, max_length=5)


def _normalize_effort(value: Any) -> str:
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned in ("low", "medium", "high"):
            return cleaned
    return "medium"


Effort = Annotated[Literal["low", "medium", "high"], BeforeValidator(_normalize_effort)]


class ActionItem(BaseModel):
    rank: int = 0  # reassigned sequentially by the Action agent
    title: str
    body: str
    expected_impact: str = ""
    effort: Effort = "medium"
    evidence_refs: list[str] = Field(
        default_factory=list,
        description="Metric ids from the evidence bundle backing this action",
    )
    uncertainty: str = Field(
        default="",
        description="What is uncertain about this recommendation",
    )


class ActionListResponse(BaseModel):
    actions: list[ActionItem] = Field(min_length=1, max_length=5)


class Report(BaseModel):
    run_id: str
    dataset_id: str
    objective: str
    status: Literal["complete", "partial"]
    model: str
    kpis: list[KPI]
    chart: ChartSpec
    profile: DataProfile
    insights: list[Insight]
    actions: list[ActionItem]
    warnings: list[str] = []
    plan: ExecutionPlan | None = None
    metrics: list[MetricValue] = []
    agent_states: list[AgentState] = []


class AnalyzeResponse(BaseModel):
    run_id: str
    status: Literal["complete", "partial"]
    transitions: list[StateTransition]
    report: Report
