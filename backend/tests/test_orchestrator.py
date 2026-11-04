"""Orchestrator tests with a stubbed Meta client (no network)."""

import pandas as pd

from app import orchestrator
from app.meta_client import MetaAPIError


class StubMeta:
    """Test double: canned agent outputs, honoring the MetaClient interface."""

    model = "muse-spark-1.3-test"
    configured = True

    def chat_json(self, messages, max_tokens=2000):
        user_text = messages[-1]["content"]
        if '"insights"' in user_text:
            return {
                "insights": [
                    {"title": "Revenue grows", "body": "Revenue rises over time.", "evidence": ["max=300"]}
                ]
            }
        if '"actions"' in user_text:
            return {
                "actions": [
                    {"title": "Push North", "body": "Invest more.", "expected_impact": "Higher sales", "effort": "low"}
                ]
            }
        if "data_brief" in user_text:
            return {"data_brief": "Test brief: 3 rows of regional revenue."}
        raise AssertionError("unexpected prompt")


class UnconfiguredMeta(StubMeta):
    configured = False

    def chat_json(self, messages, max_tokens=2000):
        raise MetaAPIError("MODEL_API_KEY is not configured")


def _seed_dataset() -> str:
    df = pd.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "region": ["North", "South", "North"],
            "revenue": [100.0, 200.0, 300.0],
        }
    )
    dataset_id = "ds_test"
    orchestrator.DATASETS[dataset_id] = df
    orchestrator.DATASET_NAMES[dataset_id] = "test.csv"
    return dataset_id


def test_full_pipeline_succeeds_sequentially():
    dataset_id = _seed_dataset()
    resp = orchestrator.run_analysis(dataset_id, "Grow revenue next quarter", StubMeta())
    assert resp.status == "complete"
    states = [(t.task, t.to_state) for t in resp.transitions]
    assert states == [
        ("data", "running"),
        ("data", "succeeded"),
        ("insight", "running"),
        ("insight", "succeeded"),
        ("action", "running"),
        ("action", "succeeded"),
    ]
    assert resp.report.profile.data_brief.startswith("Test brief")
    assert len(resp.report.insights) == 1
    assert resp.report.actions[0].rank == 1
    assert resp.report.kpis and resp.report.chart.data


def test_missing_key_yields_partial_report_not_fake_data():
    dataset_id = _seed_dataset()
    resp = orchestrator.run_analysis(dataset_id, "Grow revenue next quarter", UnconfiguredMeta())
    assert resp.status == "partial"
    assert resp.report.insights == [] and resp.report.actions == []
    # Deterministic analytics are still real.
    assert resp.report.kpis[0].value == "3"
    assert resp.report.chart.data
    assert any("MODEL_API_KEY" in w for w in resp.report.warnings)
    states = [(t.task, t.to_state) for t in resp.transitions]
    assert ("insight", "skipped") in states and ("action", "skipped") in states
