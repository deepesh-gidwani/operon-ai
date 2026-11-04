"""Sample dataset tests: reproducibility + independent validation.

The committed CSV must be byte-identical to the seeded generator output, and
the stdlib-only validator (no shared code with the pandas pipeline) must pass.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
SAMPLE = DATA_DIR / "sample_sales.csv"


def _load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generator_is_deterministic():
    generate_sample = _load_module("generate_sample", "generate_sample.py")
    first = generate_sample.generate()
    second = generate_sample.generate()
    assert len(first) == 600
    assert first == second


def test_committed_csv_matches_generator():
    import csv

    generate_sample = _load_module("generate_sample", "generate_sample.py")
    expected = generate_sample.generate()
    with SAMPLE.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == [
            "date",
            "order_id",
            "product",
            "category",
            "quantity",
            "unit_price",
            "unit_cost",
            "revenue",
        ]
        assert list(reader) == expected


def test_independent_validator_passes_with_ground_truth():
    validate_sample = _load_module("validate_sample", "validate_sample.py")
    result = validate_sample.validate(SAMPLE)
    assert result["failures"] == []
    kpis = result["kpis"]
    assert kpis["transactions"] == 600
    assert kpis["total_revenue"] == 192587.0
    assert kpis["total_units"] == 1207
    # Cross-check one relationship the validator itself asserts structurally:
    assert abs(kpis["avg_order_value"] - kpis["total_revenue"] / 600) < 0.01
