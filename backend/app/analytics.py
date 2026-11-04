"""Deterministic CSV analytics with pandas. No LLM calls here."""

from __future__ import annotations

from io import StringIO
from typing import Any

import pandas as pd

from .models import ChartSpec, ColumnInfo, DataProfile, EvidenceBundle, KPI, MetricValue, PlannedAnalysis

MAX_ROWS = 500_000
MAX_COLS = 200


class MissingColumnError(ValueError):
    """An allowlisted analysis referenced a column that is not in the CSV."""


class NonNumericColumnError(ValueError):
    """An allowlisted analysis needed numbers but the column is not numeric."""


def _jsonable(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, TypeError):
            pass
    return value


def read_csv_text(filename: str, text: str) -> pd.DataFrame:
    """Parse and validate an uploaded CSV. Raises ValueError with a clear message."""
    if not filename.lower().endswith(".csv"):
        raise ValueError("Only .csv files are accepted.")
    if not text.strip():
        raise ValueError("The uploaded file is empty.")
    try:
        df = pd.read_csv(StringIO(text))
    except Exception as exc:
        raise ValueError(f"Could not parse CSV: {exc}") from exc
    if df.shape[0] == 0:
        raise ValueError("The CSV has a header but no data rows.")
    if df.shape[1] == 0:
        raise ValueError("The CSV has no columns.")
    if df.shape[0] > MAX_ROWS:
        raise ValueError(f"Too many rows ({df.shape[0]:,}); limit is {MAX_ROWS:,}.")
    if df.shape[1] > MAX_COLS:
        raise ValueError(f"Too many columns ({df.shape[1]}); limit is {MAX_COLS}.")
    df.columns = [str(c).strip() or f"col_{i}" for i, c in enumerate(df.columns)]
    return df


def _column_infos(df: pd.DataFrame) -> list[ColumnInfo]:
    infos = []
    for col in df.columns:
        s = df[col]
        missing = int(s.isna().sum())
        infos.append(
            ColumnInfo(
                name=str(col),
                dtype=str(s.dtype),
                missing=missing,
                missing_pct=round(100 * missing / len(df), 2) if len(df) else 0.0,
                unique=int(s.nunique(dropna=True)),
            )
        )
    return infos


def _numeric_summary(df: pd.DataFrame) -> dict[str, dict[str, float]]:
    summary: dict[str, dict[str, float]] = {}
    for col in df.select_dtypes(include="number").columns:
        desc = df[col].describe()
        summary[str(col)] = {
            k: round(float(v), 4)
            for k, v in desc.items()
            if k in ("count", "mean", "std", "min", "25%", "50%", "75%", "max")
        }
    return summary


def _top_values(df: pd.DataFrame, limit_cols: int = 6, limit_vals: int = 5) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    cat_cols = [c for c in df.columns if df[c].dtype == object or str(df[c].dtype) == "category"]
    for col in cat_cols[:limit_cols]:
        vc = df[col].value_counts(dropna=True).head(limit_vals)
        out[str(col)] = [{"value": _jsonable(v), "count": int(c)} for v, c in vc.items()]
    return out


def detect_date_column(df: pd.DataFrame) -> str | None:
    return _detect_date_column(df)


def _detect_date_column(df: pd.DataFrame) -> str | None:
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            return str(col)
        if df[col].dtype == object:
            sample = df[col].dropna().head(50)
            if len(sample) < 3:
                continue
            try:
                parsed = pd.to_datetime(sample, format="mixed", errors="coerce")
            except Exception:
                continue
            if parsed.notna().mean() >= 0.8:
                return str(col)
    return None


def _trend(df: pd.DataFrame, date_col: str, max_points: int = 60) -> list[dict[str, Any]]:
    dates = pd.to_datetime(df[date_col], format="mixed", errors="coerce")
    numeric = df.select_dtypes(include="number")
    if numeric.empty:
        counts = dates.dt.to_period("D").value_counts().sort_index()
        return [{"x": str(p), "rows": int(c)} for p, c in counts.tail(max_points).items()]
    col = numeric.columns[0]
    grouped = (
        pd.DataFrame({"d": dates, "v": numeric[col]})
        .dropna(subset=["d"])
        .groupby(pd.Grouper(key="d", freq="D"))["v"]
        .sum()
    )
    return [{"x": d.date().isoformat(), str(col): round(float(v), 2)} for d, v in grouped.tail(max_points).items()]


def _correlations(df: pd.DataFrame, limit: int = 5) -> list[dict[str, Any]]:
    numeric = df.select_dtypes(include="number")
    if numeric.shape[1] < 2:
        return []
    corr = numeric.corr(numeric_only=True).abs()
    pairs = []
    cols = list(corr.columns)
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            pairs.append({"a": str(cols[i]), "b": str(cols[j]), "abs_corr": round(float(corr.iloc[i, j]), 4)})
    pairs.sort(key=lambda p: p["abs_corr"], reverse=True)
    return pairs[:limit]


def profile_dataframe(df: pd.DataFrame) -> DataProfile:
    date_col = _detect_date_column(df)
    return DataProfile(
        rows=int(df.shape[0]),
        columns=_column_infos(df),
        numeric_summary=_numeric_summary(df),
        top_values=_top_values(df),
        date_column=date_col,
        trend=_trend(df, date_col) if date_col else [],
        correlations=_correlations(df),
    )


def _kpi_order(columns: list[str]) -> list[str]:
    """Value-like columns (revenue, sales, ...) first; stable otherwise."""

    def key(col: str) -> tuple[int, int]:
        low = col.lower()
        for i, hint in enumerate(("revenue", "sales", "amount", "profit", "total")):
            if hint in low:
                return (0, i)
        return (1, 0)

    return sorted(columns, key=key)


def build_kpis(df: pd.DataFrame, profile: DataProfile) -> list[KPI]:
    kpis = [KPI(label="Rows", value=f"{len(df):,}", detail=f"{len(df.columns)} columns")]
    ordered = [c for c in _kpi_order(list(profile.numeric_summary)) if c in df.columns]
    for col in ordered[:3]:
        stats = profile.numeric_summary[col]
        kpis.append(
            KPI(
                label=f"Total {col}",
                value=f"{df[col].sum():,.2f}",
                detail=f"mean {stats.get('mean', 0):,.2f} · max {stats.get('max', 0):,.2f}",
            )
        )
    for col, vals in list(profile.top_values.items())[: max(0, 4 - len(kpis))]:
        if vals:
            kpis.append(
                KPI(label=f"Top {col}", value=str(vals[0]["value"]), detail=f"{vals[0]['count']:,} occurrences")
            )
    return kpis[:4]


def build_chart(df: pd.DataFrame, profile: DataProfile) -> ChartSpec:
    if profile.date_column and profile.trend:
        y_keys = [k for k in profile.trend[0] if k != "x"]
        return ChartSpec(
            kind="line",
            title=f"{y_keys[0]} over time ({profile.date_column})",
            x_key="x",
            y_keys=y_keys,
            data=profile.trend,
        )
    if profile.top_values:
        col = next(iter(profile.top_values))
        data = [{"x": str(v["value"]), "count": v["count"]} for v in profile.top_values[col]]
        return ChartSpec(kind="bar", title=f"Top values: {col}", x_key="x", y_keys=["count"], data=data)
    numeric = df.select_dtypes(include="number")
    if not numeric.empty:
        col = str(numeric.columns[0])
        hist = df[col].value_counts(bins=min(10, df[col].nunique()), sort=False)
        data = [{"x": str(iv), "count": int(c)} for iv, c in hist.items()]
        return ChartSpec(kind="bar", title=f"Distribution: {col}", x_key="x", y_keys=["count"], data=data)
    return ChartSpec(kind="bar", title="Rows", x_key="x", y_keys=["count"], data=[{"x": "rows", "count": len(df)}])


def preview_rows(df: pd.DataFrame, limit: int = 8) -> list[dict[str, Any]]:
    return [{str(k): _jsonable(v) for k, v in row.items()} for row in df.head(limit).to_dict(orient="records")]


# ---------------------------------------------------------------------------
# Allowlisted analysis functions (the Data Agent's only tools).
#
# The model NEVER generates Python or SQL. It never names a function to run:
# the orchestrator's plan selects entries from ALLOWED_ANALYSES and the
# dispatcher below executes them. Anything not in the registry is rejected.
# ---------------------------------------------------------------------------

def _require_column(df: pd.DataFrame, column: str | None, op: str) -> str:
    if not column:
        raise ValueError(f"Analysis '{op}' needs a column.")
    if column not in df.columns:
        raise MissingColumnError(
            f"Analysis '{op}': column '{column}' is not in the CSV "
            f"(available: {', '.join(str(c) for c in df.columns)})."
        )
    return column


def _require_numeric(df: pd.DataFrame, column: str, op: str) -> pd.Series:
    series = pd.to_numeric(df[column], errors="coerce")
    if series.notna().sum() == 0:
        raise NonNumericColumnError(
            f"Analysis '{op}': column '{column}' has no numeric values."
        )
    return series


def fn_row_count(df: pd.DataFrame, op: PlannedAnalysis) -> list[MetricValue]:
    _ = op
    return [
        MetricValue(
            id="rows",
            label="Row count",
            function="row_count",
            value=int(df.shape[0]),
            detail=f"{int(df.shape[1])} columns",
        )
    ]


def fn_column_profile(df: pd.DataFrame, op: PlannedAnalysis) -> list[MetricValue]:
    col = _require_column(df, op.column, "column_profile")
    s = df[col]
    missing = int(s.isna().sum())
    return [
        MetricValue(
            id=f"profile:{col}",
            label=f"Profile of {col}",
            function="column_profile",
            column=col,
            value={"missing": missing, "unique": int(s.nunique(dropna=True)), "dtype": str(s.dtype)},
            detail=f"missing={missing}, unique={int(s.nunique(dropna=True))}, dtype={s.dtype}",
        )
    ]


def fn_numeric_summary(df: pd.DataFrame, op: PlannedAnalysis) -> list[MetricValue]:
    col = _require_column(df, op.column, "numeric_summary")
    series = _require_numeric(df, col, "numeric_summary")
    stats = {
        "count": int(series.count()),
        "sum": round(float(series.sum()), 2),
        "mean": round(float(series.mean()), 4),
        "min": round(float(series.min()), 4),
        "max": round(float(series.max()), 4),
    }
    return [
        MetricValue(
            id=f"summary:{col}",
            label=f"Numeric summary of {col}",
            function="numeric_summary",
            column=col,
            value=stats,
            detail=f"sum={stats['sum']:,.2f}, mean={stats['mean']:,.2f}, max={stats['max']:,.2f}",
        )
    ]


def fn_groupby_sum(df: pd.DataFrame, op: PlannedAnalysis) -> list[MetricValue]:
    group_col = _require_column(df, op.column, "groupby_sum")
    val_col = _require_column(df, op.secondary_column, "groupby_sum")
    values = _require_numeric(df, val_col, "groupby_sum")
    grouped = values.groupby(df[group_col].astype(str)).sum().sort_values(ascending=False)
    top = [{"group": _jsonable(g), "sum": round(float(v), 2)} for g, v in grouped.head(5).items()]
    top_txt = ", ".join(f"{t['group']}={t['sum']:,.2f}" for t in top) if top else "no groups"
    return [
        MetricValue(
            id=f"group_sum:{val_col}:by:{group_col}",
            label=f"Sum of {val_col} by {group_col}",
            function="groupby_sum",
            column=group_col,
            value=top,
            detail=f"top: {top_txt}",
        )
    ]


def fn_groupby_mean(df: pd.DataFrame, op: PlannedAnalysis) -> list[MetricValue]:
    group_col = _require_column(df, op.column, "groupby_mean")
    val_col = _require_column(df, op.secondary_column, "groupby_mean")
    values = _require_numeric(df, val_col, "groupby_mean")
    grouped = values.groupby(df[group_col].astype(str)).mean().sort_values(ascending=False)
    top = [{"group": _jsonable(g), "mean": round(float(v), 2)} for g, v in grouped.head(5).items()]
    top_txt = ", ".join(f"{t['group']}={t['mean']:,.2f}" for t in top) if top else "no groups"
    return [
        MetricValue(
            id=f"group_mean:{val_col}:by:{group_col}",
            label=f"Mean of {val_col} by {group_col}",
            function="groupby_mean",
            column=group_col,
            value=top,
            detail=f"top: {top_txt}",
        )
    ]


def fn_top_values(df: pd.DataFrame, op: PlannedAnalysis) -> list[MetricValue]:
    col = _require_column(df, op.column, "top_values")
    vc = df[col].value_counts(dropna=True).head(5)
    vals = [{"value": _jsonable(v), "count": int(c)} for v, c in vc.items()]
    txt = ", ".join(f"{t['value']}={t['count']:,}" for t in vals) if vals else "no values"
    return [
        MetricValue(
            id=f"top:{col}",
            label=f"Top values of {col}",
            function="top_values",
            column=col,
            value=vals,
            detail=f"top: {txt}",
        )
    ]


def fn_trend_daily(df: pd.DataFrame, op: PlannedAnalysis) -> list[MetricValue]:
    date_col = _require_column(df, op.column, "trend_daily")
    val_col = _require_column(df, op.secondary_column, "trend_daily")
    dates = pd.to_datetime(df[date_col], format="mixed", errors="coerce")
    if dates.notna().sum() < 2:
        raise ValueError(f"Analysis 'trend_daily': column '{date_col}' has no parseable dates.")
    values = _require_numeric(df, val_col, "trend_daily")
    daily = (
        pd.DataFrame({"d": dates, "v": values})
        .dropna(subset=["d"])
        .groupby(pd.Grouper(key="d", freq="D"))["v"]
        .sum()
        .sort_index()
    )
    first, last = float(daily.iloc[0]), float(daily.iloc[-1])
    pct = (100 * (last - first) / first) if first else 0.0
    return [
        MetricValue(
            id=f"trend:{val_col}:by:{date_col}",
            label=f"Daily trend of {val_col} by {date_col}",
            function="trend_daily",
            column=date_col,
            value={
                "points": int(len(daily)),
                "first_day": daily.index[0].date().isoformat(),
                "last_day": daily.index[-1].date().isoformat(),
                "first_sum": round(first, 2),
                "last_sum": round(last, 2),
                "change_pct": round(pct, 2),
            },
            detail=(
                f"{len(daily)} days, {daily.index[0].date().isoformat()}={first:,.2f} -> "
                f"{daily.index[-1].date().isoformat()}={last:,.2f} ({pct:+.1f}%)"
            ),
        )
    ]


def fn_correlation(df: pd.DataFrame, op: PlannedAnalysis) -> list[MetricValue]:
    col_a = _require_column(df, op.column, "correlation")
    col_b = _require_column(df, op.secondary_column, "correlation")
    a = _require_numeric(df, col_a, "correlation")
    b = _require_numeric(df, col_b, "correlation")
    corr = float(a.corr(b))
    return [
        MetricValue(
            id=f"corr:{col_a}:{col_b}",
            label=f"Correlation {col_a} vs {col_b}",
            function="correlation",
            column=col_a,
            value=round(corr, 4),
            detail=f"pearson r={corr:.3f}",
        )
    ]


ALLOWED_ANALYSES = {
    "row_count": fn_row_count,
    "column_profile": fn_column_profile,
    "numeric_summary": fn_numeric_summary,
    "groupby_sum": fn_groupby_sum,
    "groupby_mean": fn_groupby_mean,
    "top_values": fn_top_values,
    "trend_daily": fn_trend_daily,
    "correlation": fn_correlation,
}


def run_planned(df: pd.DataFrame, op: PlannedAnalysis) -> list[MetricValue]:
    """Execute one planned analysis. Only allowlisted functions can run."""
    fn = ALLOWED_ANALYSES.get(op.function)
    if fn is None:
        raise ValueError(
            f"Unknown analysis function: '{op.function}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_ANALYSES))}."
        )
    return fn(df, op)


def collect_evidence(df: pd.DataFrame, ops: list[PlannedAnalysis]) -> EvidenceBundle:
    """Run every planned analysis; per-op failures become warnings, never crashes."""
    bundle = EvidenceBundle()
    for op in ops:
        try:
            bundle.metrics.extend(run_planned(df, op))
        except (MissingColumnError, NonNumericColumnError, ValueError) as exc:
            bundle.warnings.append(str(exc))
    return bundle
