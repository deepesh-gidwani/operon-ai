"""Deterministic analytics tests (no LLM, no network)."""

import pandas as pd
import pytest

from app import analytics


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
            "region": ["North", "South", "North", "East"],
            "revenue": [100.0, 200.0, 150.0, 300.0],
        }
    )


def test_read_csv_valid():
    df = analytics.read_csv_text("sales.csv", "a,b\n1,2\n3,4\n")
    assert df.shape == (2, 2)
    assert list(df.columns) == ["a", "b"]


def test_read_csv_rejects_non_csv():
    with pytest.raises(ValueError, match="Only .csv"):
        analytics.read_csv_text("sales.xlsx", "a\n1\n")


def test_read_csv_rejects_empty():
    with pytest.raises(ValueError, match="empty"):
        analytics.read_csv_text("sales.csv", "   \n")


def test_read_csv_rejects_header_only():
    with pytest.raises(ValueError, match="no data rows"):
        analytics.read_csv_text("sales.csv", "a,b\n")


def test_profile_stats_are_real():
    profile = analytics.profile_dataframe(_df())
    assert profile.rows == 4
    assert profile.numeric_summary["revenue"]["max"] == 300.0
    assert profile.numeric_summary["revenue"]["mean"] == 187.5
    assert profile.top_values["region"][0] == {"value": "North", "count": 2}
    assert profile.date_column == "date"
    assert len(profile.trend) == 4


def test_chart_prefers_time_series():
    df = _df()
    chart = analytics.build_chart(df, analytics.profile_dataframe(df))
    assert chart.kind == "line"
    assert chart.x_key == "x"
    assert len(chart.data) == 4


def test_chart_falls_back_to_bar():
    df = pd.DataFrame({"region": ["A", "B", "A"], "note": ["x", "y", "z"]})
    chart = analytics.build_chart(df, analytics.profile_dataframe(df))
    assert chart.kind == "bar"
    assert chart.data[0]["x"] == "A"


def test_kpis_bounded_and_real():
    df = _df()
    kpis = analytics.build_kpis(df, analytics.profile_dataframe(df))
    assert 1 <= len(kpis) <= 4
    assert kpis[0].label == "Rows" and kpis[0].value == "4"
    assert kpis[1].label == "Total revenue" and kpis[1].value == "750.00"
