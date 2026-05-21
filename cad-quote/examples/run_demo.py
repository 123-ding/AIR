"""演示：生成示例 DXF → 解析 → 三种报价方式输出。

运行：

    cd cad-quote
    pip install -r requirements.txt
    python examples/run_demo.py
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # 让 `app` 可被导入

import ezdxf  # noqa: E402

from app.cad.parser import parse_dxf  # noqa: E402
from app.catalog.catalog import ProductCatalog  # noqa: E402
from app.ocr.extractor import extract_from_regions, items_to_dataframe  # noqa: E402
from app.quote.engine import build_quote  # noqa: E402
from app.quote.exporter import to_excel  # noqa: E402
from app.quote.strategies import create_strategy  # noqa: E402


def _make_sample_dxf(path: str) -> None:
    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()
    # A区：配电柜
    msp.add_text("ABC-100 × 2", dxfattribs={"height": 2.5, "insert": (10, 10)})
    msp.add_text("ABC-200", dxfattribs={"height": 2.5, "insert": (40, 40)})
    # B区：管道阀门
    msp.add_text("XYZ-DN50 × 4", dxfattribs={"height": 2.5, "insert": (110, 10)})
    msp.add_text("XYZ-DN100 × 2", dxfattribs={"height": 2.5, "insert": (150, 40)})
    # C区：照明
    msp.add_text("LED-T8-18W × 12", dxfattribs={"height": 2.5, "insert": (20, 120)})
    doc.saveas(path)


def main() -> None:
    out_dir = os.path.join(HERE, "out")
    os.makedirs(out_dir, exist_ok=True)
    dxf_path = os.path.join(out_dir, "sample.dxf")
    _make_sample_dxf(dxf_path)

    document = parse_dxf(dxf_path)
    catalog = ProductCatalog.default()
    with open(os.path.join(HERE, "regions.json"), "r", encoding="utf-8") as f:
        regions = [(r["name"], tuple(r["bbox"])) for r in json.load(f)]

    items = extract_from_regions(document, regions, catalog)
    print("=== 识别清单 ===")
    print(items_to_dataframe(items).to_string(index=False))

    for name, params in [
        ("standard", {"tax_rate": 0.13}),
        ("discount", {"discount": 0.85, "customer_level": "gold",
                      "customer_level_factors": {"gold": 0.98}}),
        ("tiered", {"tiers": [
            {"min_qty": 1, "price": 1280},
            {"min_qty": 10, "price": 1100},
        ]}),
        ("bundle", {"labor": 500, "transport": 200, "extra_pct": 0.05}),
    ]:
        s = create_strategy(name, **params)
        quote = build_quote(items, s, catalog=catalog)
        out_xlsx = os.path.join(out_dir, f"quote_{name}.xlsx")
        to_excel(quote, out_xlsx)
        print(f"[{name}] 合计 {quote.total} → {out_xlsx}")


if __name__ == "__main__":
    main()
