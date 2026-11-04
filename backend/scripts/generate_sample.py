"""Generate the reproducible synthetic retail sample dataset.

ALL DATA IS SYNTHETIC — invented for demo purposes, not from any real business.

Output: backend/data/sample_sales.csv — 600 transactions, Jan–Jun 2026, with:
- 4 product categories (Electronics, Apparel, Home Goods, Grocery)
- seasonal demand (spring peak in May + weekend uplift)
- a declining category (Home Goods share falls every month)
- a high-revenue but low-margin category (Electronics, ~10% margin)

Deterministic: fixed seed (42), stdlib `random` only. Re-running produces
byte-identical CSV. Numeric relationships are exact:
revenue = quantity * unit_price, and 0 < unit_cost < unit_price per product.

Usage: python backend/scripts/generate_sample.py
"""

from __future__ import annotations

import calendar
import csv
import random
from datetime import date
from pathlib import Path

SEED = 42
N_TRANSACTIONS = 600
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "sample_sales.csv"

# product -> (category, unit_price, unit_cost)
PRODUCTS: dict[str, tuple[str, float, float]] = {
    "Laptop Pro": ("Electronics", 1200.0, 1080.0),
    "Phone X": ("Electronics", 800.0, 720.0),
    "Tablet S": ("Electronics", 450.0, 405.0),
    "Jacket": ("Apparel", 120.0, 70.0),
    "T-Shirt": ("Apparel", 25.0, 12.0),
    "Jeans": ("Apparel", 80.0, 44.0),
    "Lamp": ("Home Goods", 60.0, 33.0),
    "Chair": ("Home Goods", 150.0, 84.0),
    "Rug": ("Home Goods", 200.0, 110.0),
    "Coffee": ("Grocery", 15.0, 7.0),
    "Pasta Box": ("Grocery", 8.0, 3.5),
    "Olive Oil": ("Grocery", 20.0, 9.0),
}

BY_CATEGORY: dict[str, list[str]] = {}
for _product, (_cat, _, _) in PRODUCTS.items():
    BY_CATEGORY.setdefault(_cat, []).append(_product)

# Overall monthly demand weights (seasonal: May peak).
MONTH_WEIGHTS = [0.80, 0.85, 1.00, 1.10, 1.25, 1.00]  # Jan..Jun 2026

# Per-month category shares. Home Goods declines every month; Apparel peaks
# in May; Electronics holds steady; Grocery takes the remainder.
CATEGORY_SHARES = {
    "Electronics": [0.28, 0.28, 0.28, 0.28, 0.28, 0.28],
    "Apparel": [0.15, 0.17, 0.25, 0.30, 0.33, 0.25],
    "Home Goods": [0.25, 0.22, 0.18, 0.13, 0.10, 0.07],
}
CATEGORIES = ["Electronics", "Apparel", "Home Goods", "Grocery"]

# quantity choices + weights per category: (values, weights)
QUANTITIES = {
    "Electronics": ([1, 2], [0.85, 0.15]),
    "Apparel": ([1, 2, 3, 4], [0.45, 0.30, 0.15, 0.10]),
    "Home Goods": ([1, 2, 3], [0.55, 0.30, 0.15]),
    "Grocery": ([1, 2, 3, 4, 6, 8], [0.30, 0.25, 0.18, 0.12, 0.08, 0.07]),
}


def _month_counts(rng: random.Random) -> list[int]:
    months = rng.choices(range(6), weights=MONTH_WEIGHTS, k=N_TRANSACTIONS)
    return [months.count(m) for m in range(6)]


def _sample_day(rng: random.Random, month: int) -> date:
    days_in_month = calendar.monthrange(2026, month + 1)[1]
    days = list(range(1, days_in_month + 1))
    weights = [1.6 if date(2026, month + 1, d).weekday() >= 5 else 1.0 for d in days]
    return date(2026, month + 1, rng.choices(days, weights=weights, k=1)[0])


def _sample_category(rng: random.Random, month: int) -> str:
    shares = [CATEGORY_SHARES[c][month] if c != "Grocery" else 0.0 for c in CATEGORIES]
    shares[3] = max(0.0, 1.0 - sum(shares[:3]))
    return rng.choices(CATEGORIES, weights=shares, k=1)[0]


def generate(rng: random.Random | None = None) -> list[dict[str, str]]:
    rng = rng or random.Random(SEED)
    rows: list[tuple[date, dict[str, str]]] = []
    for month, count in enumerate(_month_counts(rng)):
        for _ in range(count):
            day = _sample_day(rng, month)
            category = _sample_category(rng, month)
            product = rng.choice(BY_CATEGORY[category])
            _, price, cost = PRODUCTS[product]
            values, weights = QUANTITIES[category]
            qty = rng.choices(values, weights=weights, k=1)[0]
            revenue = round(qty * price, 2)
            rows.append(
                (
                    day,
                    {
                        "date": day.isoformat(),
                        "product": product,
                        "category": category,
                        "quantity": str(qty),
                        "unit_price": f"{price:.2f}",
                        "unit_cost": f"{cost:.2f}",
                        "revenue": f"{revenue:.2f}",
                    },
                )
            )
    rows.sort(key=lambda r: r[0])
    out = []
    for i, (_, row) in enumerate(rows, start=1):
        out.append({"order_id": f"ORD-{i:04d}", **row})
    return out


def main() -> None:
    rows = generate()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "date",
                "order_id",
                "product",
                "category",
                "quantity",
                "unit_price",
                "unit_cost",
                "revenue",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUT_PATH}")


if __name__ == "__main__":
    main()
