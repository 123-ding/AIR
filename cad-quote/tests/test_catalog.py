from app.catalog.catalog import Product, ProductCatalog


def test_default_catalog_loads():
    cat = ProductCatalog.default()
    assert len(cat) > 0
    assert "ABC-100" in cat
    p = cat.get("ABC-100")
    assert p is not None
    assert p.brand == "ACME"
    assert p.base_price > 0


def test_aliases_and_canonicalize():
    cat = ProductCatalog.default()
    # 别名 + 大小写不敏感
    assert cat.canonicalize("abc100") == "ABC-100"
    assert cat.get("ABC100") is not None
    assert cat.get("abc_100") is not None
    # 未知型号原样返回（大写）
    assert cat.canonicalize("unknown-x") == "UNKNOWN-X"
    assert cat.get("unknown-x") is None


def test_in_memory_catalog():
    cat = ProductCatalog(
        [
            Product(model="M1", base_price=100.0, aliases=["m-1"]),
            Product(model="M2", base_price=50.0),
        ]
    )
    assert len(cat) == 2
    assert cat.get("m-1").model == "M1"
    assert sorted(cat.models()) == ["M1", "M2"]
    assert "ABC-100" not in cat
