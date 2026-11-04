"""Engine tests: real metrics, evidence-linked recommendations, safe failures.

No network: the Meta client is stubbed or its transport is monkeypatched.
Deterministic checks recompute expectations with independent pandas calls.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from app import analytics, orchestrator
from app.agents import ActionAgent, InsightAgent
from app.analytics import ALLOWED_ANALYSES, MissingColumnError, NonNumericColumnError
from app.meta_client import MetaAPIError, MetaClient
from app.models import EvidenceBundle, Insight, PlannedAnalysis

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample_sales.csv"


def _allowed_ids(user_text: str) -> list[str]:
    marker = "Allowed metric ids:"
    idx = user_text.find(marker)
    assert idx != -1, "prompt must list allowed metric ids"
    return re.findall(r"'([^']+)'", user_text[idx:])


class EvidenceAwareStub:
    """Stub that cites real metric ids from the prompt, plus one bogus id."""

    model = "muse-spark-1.3-test"
    configured = True

    def chat_json(self, messages, max_tokens=2000):
        full_text = "\n".join(m["content"] for m in messages)
        if '"insights"' in full_text:
            real = _allowed_ids(full_text)[:2]
            return {
                "insights": [
                    {
                        "title": "Revenue concentrates in top regions",
                        "body": "Regional totals differ materially; see the group totals.",
                        "evidence": ["group totals differ"],
                        "metric_refs": [*real, "bogus:metric"],
                    }
                ]
            }
        if '"actions"' in full_text:
            real = _allowed_ids(full_text)[:1]
            return {
                "actions": [
                    {
                        "title": "Double down on top region",
                        "body": "Shift spend toward the leading region.",
                        "expected_impact": "Higher revenue efficiency",
                        "effort": "medium",
                        "evidence_refs": [*real, "bogus:metric"],
                        "uncertainty": "Assumes regional mix stays stable",
                    }
                ]
            }
        if "data_brief" in full_text:
            return {"data_brief": "Test brief: regional sales over time."}
        raise AssertionError("unexpected prompt")


def _sample_df() -> pd.DataFrame:
    return analytics.read_csv_text("sample_sales.csv", SAMPLE.read_text(encoding="utf-8"))


# --- Metrics match the sample CSV -------------------------------------------

def test_sample_csv_metrics_match_independent_computation():
    df = _sample_df()
    assert len(df) == 600  # header + 600 data rows on disk
    plan = orchestrator.build_execution_plan("Grow revenue next quarter", df)
    bundle = analytics.collect_evidence(df, plan.selected_analyses)
    assert bundle.warnings == []
    by_id = {m.id: m for m in bundle.metrics}

    revenue = by_id["summary:revenue"].value
    assert revenue["sum"] == pytest.approx(float(df["revenue"].sum()), abs=0.01)
    assert revenue["mean"] == pytest.approx(float(df["revenue"].mean()), abs=0.0001)
    assert revenue["max"] == pytest.approx(float(df["revenue"].max()), abs=0.0001)

    group_metrics = [m for m in bundle.metrics if m.function == "groupby_sum"]
    assert group_metrics, "plan should include at least one groupby_sum"
    for metric in group_metrics:
        rest = metric.id.removeprefix("group_sum:")
        val_col, grp_col = rest.split(":by:")
        actual = {row["group"]: row["sum"] for row in metric.value}
        expected = (
            pd.to_numeric(df[val_col]).groupby(df[grp_col].astype(str)).sum().sort_values(ascending=False)
        )
        assert set(actual) == set(expected.head(5).index)
        for group, total in expected.head(5).items():
            assert actual[group] == pytest.approx(round(float(total), 2))

    trend = by_id["trend:revenue:by:date"].value
    days = pd.to_datetime(df["date"])
    assert trend["points"] == (days.max() - days.min()).days + 1  # full daily series incl. zero days
    assert by_id["rows"].value == 600


def test_plan_selects_only_allowlisted_functions():
    df = _sample_df()
    plan = orchestrator.build_execution_plan("Cut costs and grow revenue by region", df)
    assert plan.selected_analyses
    assert plan.rationale
    for op in plan.selected_analyses:
        assert op.function in ALLOWED_ANALYSES
    assert "revenue" in plan.insight_focus and "region" in plan.insight_focus


# --- Recommendations reference real evidence ---------------------------------

def test_full_pipeline_links_recommendations_to_real_evidence():
    df = _sample_df()
    orchestrator.DATASETS["ds_engine"] = df
    resp = orchestrator.run_analysis("ds_engine", "Grow revenue next quarter", EvidenceAwareStub())
    assert resp.status == "complete"
    assert resp.report.plan is not None and resp.report.plan.selected_analyses
    metric_ids = {m.id for m in resp.report.metrics}
    assert metric_ids  # evidence is non-empty

    for insight in resp.report.insights:
        assert insight.metric_refs, "each insight must cite at least one metric"
        assert set(insight.metric_refs) <= metric_ids
    for action in resp.report.actions:
        assert action.evidence_refs, "each action must cite at least one metric"
        assert set(action.evidence_refs) <= metric_ids
        assert action.expected_impact
        assert action.uncertainty  # uncertainty is required, never skipped
    # Bogus references were dropped honestly, with warnings.
    assert any("unknown metric reference" in w for w in resp.report.warnings)
    assert all(t.task in ("data", "insight", "action") for t in resp.transitions)
    assert [s.task for s in resp.report.agent_states] == ["data", "insight", "action"]


def test_unknown_refs_filtered_without_dropping_claims():
    bundle = EvidenceBundle.model_validate(
        {"metrics": [{"id": "summary:revenue", "label": "rev", "function": "numeric_summary"}]}
    )
    insights, dropped = InsightAgent.filter_refs(
        [Insight(title="t", body="b", metric_refs=["summary:revenue", "nope"])], bundle
    )
    assert dropped == 1
    assert insights[0].metric_refs == ["summary:revenue"]


# --- Missing columns and bad input fail safely --------------------------------

def test_missing_column_raises_typed_error():
    df = pd.DataFrame({"a": [1, 2]})
    with pytest.raises(MissingColumnError, match="nope"):
        analytics.run_planned(df, PlannedAnalysis(function="numeric_summary", column="nope"))


def test_non_numeric_column_raises_typed_error():
    df = pd.DataFrame({"name": ["x", "y"]})
    with pytest.raises(NonNumericColumnError, match="name"):
        analytics.run_planned(df, PlannedAnalysis(function="numeric_summary", column="name"))


def test_allowlist_rejects_unknown_function():
    df = pd.DataFrame({"a": [1, 2]})
    with pytest.raises(ValueError, match="Unknown analysis function"):
        analytics.run_planned(df, PlannedAnalysis(function="exec_sql", column="a"))


def test_collect_evidence_converts_failures_to_warnings():
    df = pd.DataFrame({"a": [1, 2]})
    bundle = analytics.collect_evidence(
        df,
        [
            PlannedAnalysis(function="row_count"),
            PlannedAnalysis(function="numeric_summary", column="missing"),
        ],
    )
    assert [m.id for m in bundle.metrics] == ["rows"]
    assert len(bundle.warnings) == 1 and "missing" in bundle.warnings[0]


def test_pipeline_survives_sparse_dataframe():
    df = pd.DataFrame({"note": ["x", "y", "z"]})
    orchestrator.DATASETS["ds_sparse"] = df
    resp = orchestrator.run_analysis("ds_sparse", "Find any pattern in notes", EvidenceAwareStub())
    assert resp.status == "complete"  # no numeric cols, still completes honestly
    assert resp.report.metrics


# --- Model failures fail honestly ---------------------------------------------

class FailingInsightStub(EvidenceAwareStub):
    def chat_json(self, messages, max_tokens=2000):
        if any('"insights"' in m["content"] for m in messages):
            raise MetaAPIError("Model did not return valid JSON: {{{")
        return super().chat_json(messages, max_tokens=max_tokens)


def test_malformed_insight_json_yields_partial_not_fake():
    orchestrator.DATASETS["ds_badjson"] = _sample_df()
    resp = orchestrator.run_analysis(
        "ds_badjson", "Grow revenue next quarter", FailingInsightStub()
    )
    assert resp.status == "partial"
    assert resp.report.insights == [] and resp.report.actions == []
    assert resp.report.metrics  # deterministic evidence intact
    states = [(t.task, t.to_state) for t in resp.transitions]
    assert ("insight", "failed") in states and ("action", "skipped") in states
    assert any("valid JSON" in w for w in resp.report.warnings)


class EmptyInsightsStub(EvidenceAwareStub):
    def chat_json(self, messages, max_tokens=2000):
        if any('"insights"' in m["content"] for m in messages):
            return {"insights": []}  # schema violation: min_length=1
        return super().chat_json(messages, max_tokens=max_tokens)


def test_schema_violation_fails_honestly_after_bounded_retry():
    orchestrator.DATASETS["ds_empty"] = _sample_df()
    resp = orchestrator.run_analysis(
        "ds_empty", "Grow revenue next quarter", EmptyInsightsStub()
    )
    assert resp.status == "partial"
    assert resp.report.insights == []


# --- Meta client retries --------------------------------------------------------

def _ok_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        status_code=200,
        text=text,
        json=lambda: {"choices": [{"message": {"content": text}}]},
    )


def test_chat_retries_transient_http_then_succeeds(monkeypatch):
    calls: list[int] = []
    script = [SimpleNamespace(status_code=503, text="busy"), _ok_response("hi")]

    def fake_post(*args, **kwargs):
        calls.append(1)
        return script[min(len(calls) - 1, len(script) - 1)]

    monkeypatch.setattr("app.meta_client.httpx.post", fake_post)
    monkeypatch.setattr("app.meta_client.time.sleep", lambda s: None)
    client = MetaClient(api_key="k", base_url="https://x.test", max_retries=2)
    assert client.chat([{"role": "user", "content": "hi"}]) == "hi"
    assert len(calls) == 2


def test_chat_exhausts_retries_and_raises(monkeypatch):
    monkeypatch.setattr(
        "app.meta_client.httpx.post",
        lambda *a, **k: SimpleNamespace(status_code=503, text="busy"),
    )
    monkeypatch.setattr("app.meta_client.time.sleep", lambda s: None)
    client = MetaClient(api_key="k", base_url="https://x.test", max_retries=1)
    with pytest.raises(MetaAPIError, match="HTTP 503"):
        client.chat([{"role": "user", "content": "hi"}])


def test_chat_json_retries_malformed_json_then_parses(monkeypatch):
    monkeypatch.setattr("app.meta_client.time.sleep", lambda s: None)
    client = MetaClient(api_key="k", base_url="https://x.test", max_retries=1)
    script = ["not json {{{", '{"data_brief": "ok"}']
    monkeypatch.setattr(client, "chat", lambda messages, max_tokens=2000: script.pop(0))
    assert client.chat_json([{"role": "user", "content": "x"}]) == {"data_brief": "ok"}


def test_chat_json_raises_after_persistent_malformed(monkeypatch):
    monkeypatch.setattr("app.meta_client.time.sleep", lambda s: None)
    client = MetaClient(api_key="k", base_url="https://x.test", max_retries=1)
    monkeypatch.setattr(client, "chat", lambda messages, max_tokens=2000: "still {{{ broken")
    with pytest.raises(MetaAPIError, match="valid JSON"):
        client.chat_json([{"role": "user", "content": "x"}])


# --- AnalyzeRequest validation --------------------------------------------------

def test_analyze_request_accepts_csv_text():
    from app.models import AnalyzeRequest

    req = AnalyzeRequest(csv_text="a,b\n1,2\n", objective="Explore this dataset now")
    assert req.csv_text and req.dataset_id is None


def test_analyze_request_rejects_neither():
    from app.models import AnalyzeRequest

    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AnalyzeRequest(objective="Explore this dataset now")


def test_analyze_endpoint_accepts_inline_csv(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "MetaClient", lambda: EvidenceAwareStub())
    csv_text = SAMPLE.read_text(encoding="utf-8")
    resp = main.analyze(
        main.AnalyzeRequest(csv_text=csv_text, filename="inline.csv", objective="Grow revenue fast now")
    )
    assert resp.status == "complete"
    assert resp.report.metrics
    assert resp.report.dataset_id.startswith("ds_")


def test_action_agent_normalizes_effort_and_ranks():
    from app.models import ActionItem, ActionListResponse

    # Unknown effort spellings from the model coerce to "medium", never crash.
    parsed = ActionListResponse.model_validate(
        {"actions": [{"title": "b", "body": "x", "effort": "Extreme "}]}
    )
    assert parsed.actions[0].effort == "medium"

    actions = ActionAgent._normalize(
        [
            ActionItem(rank=9, title="b", body="x"),
            ActionItem(rank=3, title="a", body="y"),
        ],
        EvidenceBundle(),
    )
    assert [a.rank for a in actions] == [1, 2]
