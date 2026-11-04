# Sample dataset

**ALL DATA IS SYNTHETIC.** `sample_sales.csv` is invented for demo purposes:
fictional products, prices, and transactions. It does not come from any real
business and must not be treated as real sales data.

## Contents

600 retail transactions across six months (Jan–Jun 2026).

Columns: `date`, `order_id`, `product`, `category`, `quantity`, `unit_price`,
`unit_cost`, `revenue`.

Built-in patterns (all intentional, all verified by the validator):

- 4 categories: Electronics, Apparel, Home Goods, Grocery
- Seasonal demand: spring peak in May + weekend uplift
- Declining category: Home Goods (share falls every month)
- High-revenue, low-margin category: Electronics (~10% margin vs ~45%+ elsewhere)

Numeric relationships are exact: `revenue = quantity * unit_price` per row and
`0 < unit_cost < unit_price` per product.

## Regenerate (deterministic)

```powershell
cd backend
.\.venv\Scripts\python.exe scripts/generate_sample.py
.\.venv\Scripts\python.exe scripts/validate_sample.py
```

The generator uses fixed seed 42 and stdlib `random` only — re-running produces
a byte-identical CSV. The validator is stdlib-only on purpose: it shares no code
with the pandas analytics pipeline, so its agreement with the app is a genuine
cross-check. Ground-truth KPIs: 600 transactions, $192,587.00 revenue,
1,207 units, $320.98 average order value.
