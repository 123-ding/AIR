from app.cad.parser import CadDocument, CadInsert, CadText
from app.catalog.catalog import Product, ProductCatalog
from app.ocr.extractor import (
    _extract_quantity,
    _find_models_in_text,
    extract_from_region,
    extract_from_regions,
    items_to_dataframe,
)


def _catalog():
    return ProductCatalog(
        [
            Product(model="ABC-100", brand="ACME", base_price=1280.0, aliases=["ABC100"]),
            Product(model="XYZ-DN50", brand="NovaFlow", base_price=320.0),
        ]
    )


def test_find_models_prefers_longer_match():
    found = _find_models_in_text("使用 ABC-100 设备", ["ABC", "ABC-100"])
    assert "ABC-100" in found
    # 不应被短前缀重复匹配
    assert found.count("ABC") == 0


def test_extract_quantity_patterns():
    assert _extract_quantity("ABC-100 × 3") == 3
    assert _extract_quantity("共 5 台") == 5
    assert _extract_quantity("LED-T8-18W 10pcs") == 10
    assert _extract_quantity("没有数字") is None


def test_extract_from_region_uses_text_and_inserts():
    doc = CadDocument(
        texts=[
            CadText(text="设备 ABC-100 × 2", x=10, y=10),
            CadText(text="XYZ-DN50 阀门", x=20, y=20),
            CadText(text="区外的 ABC-100", x=999, y=999),  # 不在框内
        ],
        inserts=[
            CadInsert(name="ABC-100", x=30, y=30),
            CadInsert(name="UNKNOWN-BLOCK", x=40, y=40),
        ],
    )
    items = extract_from_region(doc, (0, 0, 100, 100), "A区", _catalog())
    by_model = {it.model: it for it in items}
    assert "ABC-100" in by_model
    # 文字中显式标了 ×2，覆盖单次计数
    assert by_model["ABC-100"].quantity == 2
    assert by_model["ABC-100"].brand == "ACME"
    assert "XYZ-DN50" in by_model
    # 未知块名不应进入清单
    assert "UNKNOWN-BLOCK" not in by_model


def test_extract_from_regions_and_dataframe():
    doc = CadDocument(
        texts=[
            CadText(text="ABC-100", x=10, y=10),
            CadText(text="XYZ-DN50", x=110, y=10),
        ],
        inserts=[],
    )
    regions = [("A区", (0, 0, 100, 100)), ("B区", (100, 0, 200, 100))]
    items = extract_from_regions(doc, regions, _catalog())
    assert {it.region for it in items} == {"A区", "B区"}
    df = items_to_dataframe(items)
    assert list(df.columns) == [
        "序号",
        "位置",
        "型号",
        "品牌",
        "规格",
        "数量",
        "单位",
        "备注",
    ]
    assert len(df) == 2


def test_alias_is_canonicalized():
    doc = CadDocument(
        texts=[CadText(text="ABC100 备品", x=5, y=5)],
        inserts=[],
    )
    items = extract_from_region(doc, (0, 0, 100, 100), "A区", _catalog())
    assert any(it.model == "ABC-100" for it in items)
