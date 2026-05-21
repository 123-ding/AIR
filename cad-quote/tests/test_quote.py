import pytest

from app.catalog.catalog import Product, ProductCatalog
from app.ocr.extractor import EquipmentItem
from app.quote.engine import build_quote
from app.quote.strategies import (
    QuoteInput,
    available_strategies,
    create_strategy,
)


def _catalog():
    return ProductCatalog(
        [
            Product(model="M1", brand="ACME", base_price=1000.0, unit="台"),
            Product(model="M2", brand="NovaFlow", base_price=200.0, unit="件"),
        ]
    )


def _items():
    return [
        EquipmentItem(model="M1", region="A", quantity=2, unit="台", brand="ACME"),
        EquipmentItem(model="M2", region="B", quantity=10, unit="件", brand="NovaFlow"),
        EquipmentItem(model="M1", region="C", quantity=1, unit="台", brand="ACME"),
    ]


def test_available_strategies_contains_all():
    names = available_strategies()
    for expected in ["standard", "discount", "tiered", "bundle"]:
        assert expected in names


def test_standard_strategy_pricing():
    s = create_strategy("standard", tax_rate=0.1)
    line = s.price_line(QuoteInput(model="M1", base_price=1000.0, quantity=3))
    assert line.unit_price == 1100.0
    assert line.subtotal == 3300.0
    assert line.discount == 1.0


def test_discount_strategy_with_brand_and_customer_level():
    s = create_strategy(
        "discount",
        discount=0.9,
        brand_factors={"ACME": 0.95},
        customer_level="gold",
        customer_level_factors={"default": 1.0, "gold": 0.98},
    )
    line = s.price_line(
        QuoteInput(model="M1", base_price=1000.0, quantity=2, brand="ACME")
    )
    expected_unit = round(1000.0 * 0.9 * 0.95 * 0.98, 2)
    assert line.unit_price == expected_unit
    assert line.subtotal == round(expected_unit * 2, 2)


def test_discount_strategy_rejects_invalid_discount():
    with pytest.raises(ValueError):
        create_strategy("discount", discount=0)
    with pytest.raises(ValueError):
        create_strategy("discount", discount=1.5)


def test_tiered_strategy_picks_correct_tier():
    s = create_strategy(
        "tiered",
        tiers=[
            {"min_qty": 1, "price": 1000.0},
            {"min_qty": 10, "price": 900.0},
            {"min_qty": 50, "price": 800.0},
        ],
    )
    l1 = s.price_line(QuoteInput(model="M1", base_price=1000.0, quantity=5))
    assert l1.unit_price == 1000.0
    l2 = s.price_line(QuoteInput(model="M1", base_price=1000.0, quantity=20))
    assert l2.unit_price == 900.0
    l3 = s.price_line(QuoteInput(model="M1", base_price=1000.0, quantity=60))
    assert l3.unit_price == 800.0


def test_bundle_strategy_adds_extras_in_engine():
    cat = _catalog()
    strategy = create_strategy(
        "bundle", labor=500.0, transport=200.0, extra_pct=0.05
    )
    quote = build_quote(_items(), strategy, catalog=cat)
    # M1*3 = 3000, M2*10 = 2000 → 小计 5000
    assert quote.subtotal == 5000.0
    labels = [e[0] for e in quote.extras]
    assert "人工费" in labels and "运输费" in labels
    # 总额 = (5000 + 500 + 200) * 1.05 = 5985
    assert quote.total == 5985.0


def test_build_quote_aggregates_same_model():
    cat = _catalog()
    strategy = create_strategy("standard")
    quote = build_quote(_items(), strategy, catalog=cat)
    models = [l.model for l in quote.lines]
    # M1 出现两次但应聚合
    assert models.count("M1") == 1
    m1_line = next(l for l in quote.lines if l.model == "M1")
    assert m1_line.quantity == 3
    assert m1_line.subtotal == 3000.0


def test_unknown_strategy_raises():
    with pytest.raises(ValueError):
        create_strategy("unknown-strategy")
