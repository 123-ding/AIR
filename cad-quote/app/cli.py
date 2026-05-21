"""命令行入口：

    python -m app.cli quote \\
        --dxf path/to/drawing.dxf \\
        --regions regions.json \\
        --strategy discount \\
        --strategy-params '{"discount": 0.85}' \\
        --excel out/quote.xlsx \\
        --image out/composite.png

``regions.json`` 形如：

    [
      {"name": "A区", "bbox": [0, 0, 100, 100]},
      {"name": "B区", "bbox": [100, 0, 200, 100]}
    ]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List

from .cad.parser import parse_dxf
from .catalog.catalog import ProductCatalog
from .ocr.extractor import extract_from_regions, items_to_dataframe
from .quote.engine import build_quote
from .quote.exporter import to_csv, to_excel
from .quote.strategies import available_strategies, create_strategy


def _load_regions(path: str):
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    regions = []
    for item in raw:
        regions.append((item["name"], tuple(item["bbox"])))
    return regions


def _build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cad-quote", description="CAD 解析与报价")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_quote = sub.add_parser("quote", help="解析 DXF 并生成报价单")
    p_quote.add_argument("--dxf", required=True, help="DXF 文件路径")
    p_quote.add_argument("--regions", required=True, help="区域 JSON 文件")
    p_quote.add_argument("--catalog", default=None, help="自定义型号库 YAML")
    p_quote.add_argument(
        "--strategy", default="standard", choices=available_strategies()
    )
    p_quote.add_argument(
        "--strategy-params", default="{}", help="策略参数 JSON 字符串"
    )
    p_quote.add_argument("--excel", default=None, help="输出 Excel 路径")
    p_quote.add_argument("--csv", default=None, help="输出 CSV 路径")
    p_quote.add_argument("--image", default=None, help="输出拼图路径")
    p_quote.add_argument("--dpi", type=int, default=120)

    sub.add_parser("strategies", help="列出所有可用报价策略")
    sub.add_parser("catalog", help="列出默认型号库的所有型号")

    p_auto = sub.add_parser("auto-regions", help="自动识别 DXF 中的候选区域")
    p_auto.add_argument("--dxf", required=True, help="DXF 文件路径")
    p_auto.add_argument(
        "--prefer", default="auto", choices=["auto", "rectangle", "layer"]
    )
    p_auto.add_argument("--out", default=None, help="把结果写入此 JSON 文件，省略则打印到 stdout")
    return parser


def main(argv: List[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)

    if args.cmd == "strategies":
        for s in available_strategies():
            print(s)
        return 0

    if args.cmd == "catalog":
        cat = ProductCatalog.default()
        for m in cat.models():
            print(m)
        return 0

    if args.cmd == "auto-regions":
        from .cad.auto_regions import detect_regions

        document = parse_dxf(args.dxf)
        regions = detect_regions(document, prefer=args.prefer)
        payload = [{"name": name, "bbox": list(bbox)} for name, bbox in regions]
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        if args.out:
            os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"已写入 {len(payload)} 个区域到 {args.out}")
        else:
            print(text)
        return 0

    if args.cmd == "quote":
        catalog = (
            ProductCatalog.from_yaml(args.catalog)
            if args.catalog
            else ProductCatalog.default()
        )
        document = parse_dxf(args.dxf)
        regions = _load_regions(args.regions)
        items = extract_from_regions(document, regions, catalog)

        df = items_to_dataframe(items)
        print("识别出的设备清单：")
        print(df.to_string(index=False))

        strategy = create_strategy(args.strategy, **json.loads(args.strategy_params))
        quote = build_quote(items, strategy, catalog=catalog)

        print(f"\n报价策略：{quote.strategy_name}")
        for line in quote.lines:
            print(
                f"  {line.model} × {line.quantity} {line.unit} "
                f"@ {line.unit_price} = {line.subtotal}  [{line.note}]"
            )
        print(f"小计：{quote.subtotal}")
        for label, amount in quote.extras:
            print(f"{label}: {amount}")
        print(f"合计：{quote.total} {quote.currency}")

        if args.excel:
            to_excel(quote, args.excel)
            print(f"\nExcel 已写入：{args.excel}")
        if args.csv:
            to_csv(quote, args.csv)
            print(f"CSV 已写入：{args.csv}")
        if args.image:
            # 延迟导入：渲染依赖 matplotlib
            from .cad.renderer import render_regions
            from .cad.compositor import composite_grid

            os.makedirs(os.path.dirname(os.path.abspath(args.image)) or ".", exist_ok=True)
            tmp_dir = os.path.join(
                os.path.dirname(os.path.abspath(args.image)) or ".", "_regions"
            )
            bboxes = [bbox for _, bbox in regions]
            labels = [name for name, _ in regions]
            paths = render_regions(args.dxf, bboxes, tmp_dir, dpi=args.dpi)
            composite_grid(paths, args.image, labels=labels)
            print(f"拼图已写入：{args.image}")
        return 0

    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
