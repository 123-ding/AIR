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


def to_pdf(
    quote: Quote,
    out_path: str,
    title: str = "报价单",
    customer_name: str = "",
) -> str:
    """输出 PDF 报价单（reportlab，懒加载）。

    页面样式简洁：标题 + 元信息 + 明细表 + 汇总。中文字体优先使用系统中的
    ``SimSun`` / ``NotoSansCJK``；找不到则回退到 reportlab 默认字体（仅 ASCII 可读）。
    """

    try:
        from reportlab.lib import colors  # type: ignore
        from reportlab.lib.pagesizes import A4  # type: ignore
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # type: ignore
        from reportlab.lib.units import mm  # type: ignore
        from reportlab.pdfbase import pdfmetrics  # type: ignore
        from reportlab.pdfbase.ttfonts import TTFont  # type: ignore
        from reportlab.platypus import (  # type: ignore
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "reportlab 未安装；请 `pip install reportlab` 后再导出 PDF。"
        ) from exc

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)

    # 注册中文字体（best-effort）
    font_name = "Helvetica"
    for candidate in (
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/msyh.ttc",
    ):
        if os.path.isfile(candidate):
            try:
                pdfmetrics.registerFont(TTFont("CJK", candidate))
                font_name = "CJK"
                break
            except Exception:  # noqa: BLE001
                continue

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "title",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=18,
    )
    body_style = ParagraphStyle(
        "body",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=10,
    )

    doc = SimpleDocTemplate(
        out_path,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=title,
    )

    story = [Paragraph(title, title_style), Spacer(1, 6)]
    meta_lines = [f"策略：{quote.strategy_name}", f"币种：{quote.currency}"]
    if quote.customer_level:
        meta_lines.append(f"客户等级：{quote.customer_level}")
    if customer_name:
        meta_lines.insert(0, f"客户：{customer_name}")
    if quote.exchange_rate and quote.exchange_rate != 1.0:
        meta_lines.append(f"汇率：1 CNY ≈ {quote.exchange_rate} {quote.currency}")
    story.append(Paragraph(" | ".join(meta_lines), body_style))
    story.append(Spacer(1, 8))

    header = ["序号", "型号", "品牌", "数量", "单位", "单价", "折扣", "小计"]
    data = [header]
    for idx, line in enumerate(quote.lines, start=1):
        data.append(
            [
                str(idx),
                line.model,
                line.brand,
                str(line.quantity),
                line.unit,
                f"{line.unit_price:.2f}",
                f"{line.discount:.3f}",
                f"{line.subtotal:.2f}",
            ]
        )
    data.append([""] * 7 + [f"小计：{quote.subtotal:.2f}"])
    for label, amount in quote.extras:
        data.append([""] * 6 + [label, f"{amount:.2f}"])
    data.append([""] * 6 + ["合计", f"{quote.total:.2f} {quote.currency}"])

    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dde7f3")),
                ("GRID", (0, 0), (-1, len(quote.lines)), 0.5, colors.grey),
                ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("FONTNAME", (-2, -1), (-1, -1), font_name),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return out_path
