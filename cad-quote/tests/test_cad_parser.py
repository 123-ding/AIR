"""DXF 解析端到端测试。生成一个最小 DXF，再读回校验。"""

import pytest

ezdxf = pytest.importorskip("ezdxf")

from app.cad.parser import parse_dxf  # noqa: E402
from app.catalog.catalog import ProductCatalog  # noqa: E402
from app.ocr.extractor import extract_from_regions  # noqa: E402


def _make_sample_dxf(path: str) -> None:
    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()
    msp.add_text(
        "ABC-100 × 2",
        dxfattribs={"height": 2.5, "insert": (10, 10)},
    )
    msp.add_text(
        "XYZ-DN50 阀门",
        dxfattribs={"height": 2.5, "insert": (110, 10)},
    )
    msp.add_text(
        "区外 ABC-100",
        dxfattribs={"height": 2.5, "insert": (1000, 1000)},
    )
    doc.saveas(path)


def test_parse_and_extract_from_real_dxf(tmp_path):
    dxf_path = tmp_path / "sample.dxf"
    _make_sample_dxf(str(dxf_path))

    document = parse_dxf(str(dxf_path))
    texts = [t.text for t in document.texts]
    assert any("ABC-100" in t for t in texts)
    assert any("XYZ-DN50" in t for t in texts)

    cat = ProductCatalog.default()
    regions = [
        ("A区", (0.0, 0.0, 100.0, 100.0)),
        ("B区", (100.0, 0.0, 200.0, 100.0)),
    ]
    items = extract_from_regions(document, regions, cat)
    by_region = {it.region: it for it in items}
    assert "A区" in by_region and by_region["A区"].model == "ABC-100"
    assert by_region["A区"].quantity == 2  # 来自文本里的 "× 2"
    assert "B区" in by_region and by_region["B区"].model == "XYZ-DN50"
    # 区外的不应进入
    assert all(it.region in {"A区", "B区"} for it in items)
