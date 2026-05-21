"""测试导出（CSV + Excel）。Excel 需要 openpyxl。"""

import os

import pytest

from app.catalog.catalog import Product, ProductCatalog
from app.ocr.extractor import EquipmentItem
from app.quote.engine import build_quote
from app.quote.exporter import quote_to_rows, to_csv, to_excel
from app.quote.strategies import create_strategy


def _build_quote():
    cat = ProductCatalog(
        [
            Product(model="M1", brand="ACME", base_price=100.0, unit="台"),
            Product(model="M2", brand="NovaFlow", base_price=50.0, unit="件"),
        ]
    )
    items = [
        EquipmentItem(model="M1", region="A", quantity=2, brand="ACME"),
        EquipmentItem(model="M2", region="B", quantity=3, brand="NovaFlow"),
    ]
    return build_quote(items, create_strategy("standard"), catalog=cat)


def test_quote_to_rows_structure():
    quote = _build_quote()
    rows = quote_to_rows(quote)
    assert len(rows) == 2
    assert set(rows[0].keys()) == {
        "序号", "型号", "品牌", "数量", "单位", "单价", "折扣", "小计", "备注"
    }


def test_to_csv(tmp_path):
    quote = _build_quote()
    out = tmp_path / "q.csv"
    to_csv(quote, str(out))
    assert out.exists()
    content = out.read_text(encoding="utf-8-sig")
    assert "M1" in content and "合计" in content


def test_to_excel(tmp_path):
    pytest.importorskip("openpyxl")
    quote = _build_quote()
    out = tmp_path / "q.xlsx"
    to_excel(quote, str(out))
    assert out.exists()
    assert os.path.getsize(out) > 0
