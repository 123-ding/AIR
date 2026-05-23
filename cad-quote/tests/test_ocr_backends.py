"""测试 OCR 兜底：当 TEXT/INSERT 都没有命中型号时，从 OCR 后端识别文本中提取。"""

from app.cad.parser import CadDocument, CadText
from app.catalog.catalog import Product, ProductCatalog
from app.ocr.backends import OCRLine, StubOCRBackend, make_backend
from app.ocr.extractor import extract_from_region


def _catalog() -> ProductCatalog:
    return ProductCatalog(
        [
            Product(model="ABC-100", brand="ACME", base_price=1280.0, aliases=["ABC100"]),
            Product(model="XYZ-DN50", brand="NovaFlow", base_price=320.0),
        ]
    )


def test_ocr_fallback_kicks_in_when_no_text_match():
    # 区域内没有可命中的 TEXT/INSERT
    doc = CadDocument(texts=[], inserts=[])
    backend = StubOCRBackend(default_lines=["设备 ABC-100 × 4"])
    items = extract_from_region(
        doc,
        (0, 0, 100, 100),
        "A区",
        _catalog(),
        ocr_backend=backend,
        region_image="anything.png",
    )
    by_model = {it.model: it for it in items}
    assert "ABC-100" in by_model
    assert by_model["ABC-100"].quantity == 4
    assert "[OCR]" in by_model["ABC-100"].note


def test_ocr_not_called_when_text_already_matched():
    doc = CadDocument(texts=[CadText(text="ABC-100", x=10, y=10)], inserts=[])

    class _BoomBackend(StubOCRBackend):
        def recognize(self, image_path):  # type: ignore[override]
            raise AssertionError("不应在 TEXT 命中时调用 OCR")

    items = extract_from_region(
        doc,
        (0, 0, 100, 100),
        "A区",
        _catalog(),
        ocr_backend=_BoomBackend(),
        region_image="anything.png",
    )
    assert any(it.model == "ABC-100" for it in items)


def test_ocr_swallows_backend_errors():
    doc = CadDocument(texts=[], inserts=[])

    class _FlakyBackend(StubOCRBackend):
        def recognize(self, image_path):  # type: ignore[override]
            raise RuntimeError("paddle exploded")

    items = extract_from_region(
        doc,
        (0, 0, 100, 100),
        "A区",
        _catalog(),
        ocr_backend=_FlakyBackend(),
        region_image="anything.png",
    )
    assert items == []


def test_ocr_skipped_when_no_image_path():
    doc = CadDocument(texts=[], inserts=[])
    backend = StubOCRBackend(default_lines=["ABC-100"])
    # 没有 region_image → 不应触发 OCR
    items = extract_from_region(
        doc, (0, 0, 100, 100), "A区", _catalog(), ocr_backend=backend
    )
    assert items == []


def test_make_backend_factory():
    assert isinstance(make_backend("stub"), StubOCRBackend)
    assert make_backend("stub", default_lines=["x"]).recognize("p")[0].text == "x"


def test_make_backend_unknown_raises():
    import pytest

    with pytest.raises(ValueError):
        make_backend("does-not-exist")


def test_stub_backend_mapping_by_basename():
    backend = StubOCRBackend(mapping={"region_001.png": ["XYZ-DN50"]})
    lines = backend.recognize("/tmp/abc/region_001.png")
    assert [l.text for l in lines] == ["XYZ-DN50"]


def test_ocr_line_dataclass():
    line = OCRLine(text="hello", confidence=0.9)
    assert line.text == "hello"
    assert 0 < line.confidence <= 1
