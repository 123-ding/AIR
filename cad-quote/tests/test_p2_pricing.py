"""测试客户分级 + 多币种 + PDF 导出。"""

import os

import pytest

from app.ocr.extractor import EquipmentItem
from app.quote.customers import (
    CustomerProfile,
    CustomerRegistry,
    default_registry,
    reset_default_registry,
)
from app.quote.engine import build_quote
from app.quote.exporter import to_excel, to_pdf
from app.quote.strategies import BundleStrategy, StandardStrategy


def _items():
    return [
        EquipmentItem(model="A", region="r1", quantity=2, unit="台"),
        EquipmentItem(model="B", region="r2", quantity=3, unit="台"),
    ]


class _FakeCatalog:
    """只为提供 base_price 的最小桩。"""

    def __init__(self, prices):
        self._prices = prices

    def get(self, model):
        from app.catalog.catalog import Product

        if model in self._prices:
            return Product(model=model, base_price=self._prices[model])
        return None


def test_customer_profile_validates():
    with pytest.raises(ValueError):
        CustomerProfile(level="x", discount_factor=0)
    with pytest.raises(ValueError):
        CustomerProfile(level="x", exchange_rate=-1)


def test_builtin_registry_has_default_levels():
    reg = CustomerRegistry.builtin()
    assert {"default", "silver", "gold", "platinum"}.issubset(set(reg.list_levels()))
    assert reg.get("gold").discount_factor == 0.95
    assert reg.get("UNKNOWN") is None


def test_registry_from_yaml(tmp_path):
    p = tmp_path / "customers.yaml"
    p.write_text(
        """
customers:
  - level: vip
    discount_factor: 0.9
    currency: USD
    exchange_rate: 0.14
    description: 海外大客户
""",
        encoding="utf-8",
    )
    reg = CustomerRegistry.from_yaml(str(p))
    vip = reg.get("vip")
    assert vip.discount_factor == 0.9
    assert vip.currency == "USD"
    assert vip.exchange_rate == 0.14


def test_default_registry_loads_user_yaml(tmp_path, monkeypatch):
    p = tmp_path / "customers.yaml"
    p.write_text(
        "customers:\n  - level: only\n    discount_factor: 0.5\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CAD_QUOTE_DATA_DIR", str(tmp_path))
    reset_default_registry()
    try:
        reg = default_registry()
        assert reg.list_levels() == ["only"]
    finally:
        reset_default_registry()


def test_build_quote_applies_customer_factor():
    catalog = _FakeCatalog({"A": 100, "B": 200})
    customer = CustomerProfile("vip", discount_factor=0.9)
    q = build_quote(_items(), StandardStrategy(), catalog=catalog, customer=customer)
    # A: 2 × 100 × 0.9 = 180; B: 3 × 200 × 0.9 = 540 → 720
    assert q.subtotal == pytest.approx(720)
    assert q.total == pytest.approx(720)
    assert q.customer_level == "vip"
    assert any("客户[vip]" in ln.note for ln in q.lines)


def test_build_quote_applies_exchange_rate():
    catalog = _FakeCatalog({"A": 100, "B": 200})
    customer = CustomerProfile("us", discount_factor=1.0, currency="USD", exchange_rate=0.14)
    q = build_quote(_items(), StandardStrategy(), catalog=catalog, customer=customer)
    assert q.currency == "USD"
    # A: 2 × 100 × 0.14 = 28; B: 3 × 200 × 0.14 = 84 → 112
    assert q.subtotal == pytest.approx(112)
    assert q.exchange_rate == 0.14


def test_explicit_exchange_rate_overrides_customer():
    catalog = _FakeCatalog({"A": 100, "B": 200})
    customer = CustomerProfile("us", currency="USD", exchange_rate=0.14)
    q = build_quote(
        _items(),
        StandardStrategy(),
        catalog=catalog,
        customer=customer,
        exchange_rate=0.20,  # 覆盖
    )
    # A: 2 × 100 × 0.20 = 40; B: 3 × 200 × 0.20 = 120 → 160
    assert q.subtotal == pytest.approx(160)
    assert q.exchange_rate == 0.20


def test_bundle_strategy_extras_apply_factor_and_rate():
    catalog = _FakeCatalog({"A": 100, "B": 200})
    customer = CustomerProfile("eu", discount_factor=0.9, currency="EUR", exchange_rate=0.13)
    strategy = BundleStrategy(labor=1000, transport=500, extra_pct=0.1)
    q = build_quote(_items(), strategy, catalog=catalog, customer=customer)
    # 行小计：A: 2×100×0.9×0.13 = 23.4; B: 3×200×0.9×0.13 = 70.2 → subtotal=93.6
    assert q.subtotal == pytest.approx(93.6, rel=1e-3)
    labor_amt = next(a for label, a in q.extras if label == "人工费")
    assert labor_amt == pytest.approx(1000 * 0.9 * 0.13, rel=1e-3)
    transport_amt = next(a for label, a in q.extras if label == "运输费")
    assert transport_amt == pytest.approx(500 * 0.9 * 0.13, rel=1e-3)


def test_pdf_export_smoke(tmp_path):
    pytest.importorskip("reportlab")

    catalog = _FakeCatalog({"A": 100, "B": 200})
    q = build_quote(_items(), StandardStrategy(), catalog=catalog)
    out = str(tmp_path / "q.pdf")
    to_pdf(q, out, customer_name="Acme")
    assert os.path.isfile(out)
    with open(out, "rb") as f:
        head = f.read(8)
    assert head.startswith(b"%PDF")


def test_pdf_export_with_customer(tmp_path):
    pytest.importorskip("reportlab")
    catalog = _FakeCatalog({"A": 100, "B": 200})
    customer = CustomerProfile("gold", 0.95, "USD", 0.14)
    q = build_quote(_items(), StandardStrategy(), catalog=catalog, customer=customer)
    out = str(tmp_path / "q.pdf")
    to_pdf(q, out, customer_name="Globex")
    assert os.path.getsize(out) > 100


def test_excel_still_works_with_customer(tmp_path):
    catalog = _FakeCatalog({"A": 100, "B": 200})
    customer = CustomerProfile("gold", 0.95)
    q = build_quote(_items(), StandardStrategy(), catalog=catalog, customer=customer)
    out = str(tmp_path / "q.xlsx")
    to_excel(q, out)
    assert os.path.isfile(out)
