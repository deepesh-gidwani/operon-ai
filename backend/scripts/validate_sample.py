"""Independently validate the synthetic sample dataset + print ground-truth KPIs.

ALL DATA IS SYNTHETIC — this script verifies internal consistency only.

Deliberately stdlib-only (csv/datetime): it must NOT share code with the
pandas analytics pipeline, so agreement between the two is real evidence.

Checks: exact columns, 600 rows, unique order ids, revenue == quantity *
unit_price, 0 < unit_cost < unit_price, six-month span, >=3 categories, a
declining category, a high-revenue low-margin category, and seasonality.

Usage: python backend/scripts/validate_sample.py [--csv PATH]
Exit code 0 = all checks pass, 1 = any failure.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

DEFAULT_CSV = Path(__file__).resolve().parent.parent / "data" / "sample_sales.csv"
EXPECTED_COLUMNS = [
    "date",
    "order_id",
    "product",
    "category",
    "quantity",
    "unit_price",
    "unit_cost",
    "revenue",
]


class Failure(Exception):
    pass


def check(condition: bool, message: str, failures: list[str]) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {message}")
    if not condition:
        failures.append(message)


def load(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise Failure("CSV has no header row")
        return reader.fieldnames, list(reader)


def validate(path: Path) -> dict:
    failures: list[str] = []
    columns, rows = load(path)

    check(columns == EXPECTED_COLUMNS, f"columns == {EXPECTED_COLUMNS}", failures)
    check(len(rows) == 600, f"row count == 600 (got {len(rows)})", failures)

    order_ids = [r["order_id"] for r in rows]
    check(len(set(order_ids)) == len(rows), "order_id values are unique", failures)
    check(
        all(o.startswith("ORD-") and o[4:].isdigit() for o in order_ids),
        "order_id format is ORD-NNNN",
        failures,
    )

    parsed: list[tuple[date, str, int, float, float, float]] = []
    numeric_ok = True
    for r in rows:
        try:
            d = date.fromisoformat(r["date"])
            qty = int(r["quantity"])
            price, cost, revenue = float(r["unit_price"]), float(r["unit_cost"]), float(r["revenue"])
        except (ValueError, TypeError):
            numeric_ok = False
            break
        if qty <= 0 or not (0 < cost < price):
            numeric_ok = False
            break
        if abs(revenue - qty * price) > 0.01:
            numeric_ok = False
            break
        parsed.append((d, r["category"], qty, price, cost, revenue))
    check(numeric_ok, "quantity/unit_price/unit_cost/revenue internally consistent", failures)

    months = sorted({d.strftime("%Y-%m") for d, *_ in parsed})
    check(
        months == ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"],
        f"spans six months Jan–Jun 2026 (got {months})",
        failures,
    )

    categories = sorted({c for _, c, *_ in parsed})
    check(len(categories) >= 3, f">= 3 categories (got {categories})", failures)

    cat_revenue: dict[str, float] = defaultdict(float)
    cat_cost: dict[str, float] = defaultdict(float)
    cat_month: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    month_revenue: dict[str, float] = defaultdict(float)
    for d, cat, qty, price, cost, revenue in parsed:
        m = d.strftime("%Y-%m")
        cat_revenue[cat] += revenue
        cat_cost[cat] += qty * cost
        cat_month[cat][m] += revenue
        month_revenue[m] += revenue

    declining = [
        c
        for c in categories
        if sum(cat_month[c][m] for m in months[:3]) > 0
        and sum(cat_month[c][m] for m in months[3:])
        < 0.8 * sum(cat_month[c][m] for m in months[:3])
    ]
    check(len(declining) >= 1, f"declining category present (got {declining})", failures)

    margins = {c: 1.0 - cat_cost[c] / cat_revenue[c] for c in categories}
    top_revenue = max(cat_revenue, key=cat_revenue.get)  # type: ignore[arg-type]
    lowest_margin = min(margins, key=margins.get)  # type: ignore[arg-type]
    check(
        top_revenue == lowest_margin,
        f"top-revenue category '{top_revenue}' has lowest margin ({margins[top_revenue]:.1%})",
        failures,
    )

    peak = max(month_revenue.values())
    trough = min(month_revenue.values())
    check(peak / trough >= 1.3, f"seasonality peak/trough = {peak / trough:.2f} (>= 1.30)", failures)

    total_revenue = sum(cat_revenue.values())
    total_units = sum(q for _, _, q, *_ in parsed)
    kpis = {
        "transactions": len(rows),
        "total_revenue": round(total_revenue, 2),
        "total_units": total_units,
        "avg_order_value": round(total_revenue / len(rows), 2),
        "revenue_by_category": {c: round(cat_revenue[c], 2) for c in categories},
        "margin_by_category": {c: round(margins[c], 4) for c in categories},
        "revenue_by_month": {m: round(month_revenue[m], 2) for m in months},
    }
    return {"failures": failures, "kpis": kpis}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the synthetic sample dataset.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()
    print(f"Validating {args.csv} (ALL DATA SYNTHETIC)")
    try:
        result = validate(args.csv)
    except (Failure, OSError) as exc:
        print(f"[FAIL] {exc}")
        return 1
    print("\nGround-truth KPIs:")
    for key, value in result["kpis"].items():
        print(f"  {key}: {value}")
    if result["failures"]:
        print(f"\n{len(result['failures'])} check(s) FAILED")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
