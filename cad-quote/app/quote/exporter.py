"""把 :class:`Quote` 导出为 Excel / CSV / DataFrame。"""

from __future__ import annotations

import csv
import os
from typing import List

from .engine import Quote


def quote_to_rows(quote: Quote) -> List[dict]:
    rows = []
    for idx, line in enumerate(quote.lines, start=1):
        rows.append(
            {
                "序号": idx,
                "型号": line.model,
                "品牌": line.brand,
                "数量": line.quantity,
                "单位": line.unit,
                "单价": line.unit_price,
                "折扣": line.discount,
                "小计": line.subtotal,
                "备注": line.note,
            }
        )
    return rows


def to_dataframe(quote: Quote):
    try:
        import pandas as pd  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ImportError("pandas 未安装；请 `pip install pandas`。") from exc
    return pd.DataFrame(quote_to_rows(quote))


def to_csv(quote: Quote, out_path: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    rows = quote_to_rows(quote)
    fieldnames = (
        list(rows[0].keys())
        if rows
        else ["序号", "型号", "品牌", "数量", "单位", "单价", "折扣", "小计", "备注"]
    )
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        # 附加汇总
        writer.writerow({})
        writer.writerow({"型号": "小计", "小计": quote.subtotal})
        for label, amount in quote.extras:
            writer.writerow({"型号": label, "小计": amount})
        writer.writerow({"型号": "合计", "小计": quote.total})
    return out_path


def to_excel(quote: Quote, out_path: str, sheet_name: str = "报价单") -> str:
    """输出 Excel，含明细 + 汇总。"""

    try:
        from openpyxl import Workbook  # type: ignore
        from openpyxl.styles import Font, Alignment  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ImportError("openpyxl 未安装；请 `pip install openpyxl`。") from exc

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name

    header = ["序号", "型号", "品牌", "数量", "单位", "单价", "折扣", "小计", "备注"]
    ws.append(header)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")

    for idx, line in enumerate(quote.lines, start=1):
        ws.append(
            [
                idx,
                line.model,
                line.brand,
                line.quantity,
                line.unit,
                line.unit_price,
                line.discount,
                line.subtotal,
                line.note,
            ]
        )

    ws.append([])
    ws.append(["", "", "", "", "", "", "小计", quote.subtotal, ""])
    for label, amount in quote.extras:
        ws.append(["", "", "", "", "", "", label, amount, ""])
    ws.append(["", "", "", "", "", "", "合计", quote.total, f"币种：{quote.currency}"])

    # 列宽
    widths = [6, 18, 12, 8, 6, 12, 8, 14, 40]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[chr(64 + i)].width = w

    wb.save(out_path)
    return out_path
