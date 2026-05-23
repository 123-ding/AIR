"""从 DXF 区域中识别设备型号，输出参数表。

P0 实现：优先使用 DXF 内的 TEXT/MTEXT 实体（精确），辅以 INSERT 块名作为型号；
找不到时调用可插拔的 OCR 后端兜底（默认未启用）。
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from ..cad.parser import BBox, CadDocument, CadInsert, CadText
from ..catalog.catalog import ProductCatalog
from .backends import OCRBackend


@dataclass
class EquipmentItem:
    """一条识别出的设备明细。"""

    model: str
    region: str
    quantity: int = 1
    unit: str = "台"
    params: Dict[str, str] = field(default_factory=dict)
    brand: Optional[str] = None
    note: str = ""


def _find_models_in_text(text: str, known_models: Sequence[str]) -> List[str]:
    """在一段文本中查找出现的已知型号（按长度优先，避免短型号误吞）。"""

    found: List[str] = []
    if not text:
        return found
    upper = text.upper()
    # 先匹配长的，匹配到就把对应位置打掩码，避免被短型号重复匹配
    masked = list(upper)
    for model in sorted(set(known_models), key=len, reverse=True):
        if not model:
            continue
        m = model.upper()
        start = 0
        while True:
            idx = "".join(masked).find(m, start)
            if idx == -1:
                break
            found.append(model)
            for i in range(idx, idx + len(m)):
                masked[i] = "\0"
            start = idx + len(m)
    return found


# 备注/数量的常见写法："×3"、"x 2"、"共 5 台"、"5pcs"
_QTY_PATTERNS = [
    re.compile(r"[×xX*]\s*(\d{1,4})\b"),
    re.compile(r"共\s*(\d{1,4})\s*[台个套件只]"),
    re.compile(r"\b(\d{1,4})\s*(?:pcs|PCS|台|个|套|件|只)\b"),
]


def _extract_quantity(text: str) -> Optional[int]:
    for pat in _QTY_PATTERNS:
        m = pat.search(text or "")
        if m:
            try:
                return max(1, int(m.group(1)))
            except ValueError:
                continue
    return None


def extract_from_region(
    document: CadDocument,
    bbox: BBox,
    region_name: str,
    catalog: ProductCatalog,
    ocr_backend: Optional[OCRBackend] = None,
    region_image: Optional[str] = None,
) -> List[EquipmentItem]:
    """从一个区域内识别设备项。

    :param ocr_backend: 可选 OCR 后端；当区域内没有可命中型号的 TEXT/MTEXT 时，
        会调用 ``ocr_backend.recognize(region_image)`` 兜底。
    :param region_image: 区域已渲染的 PNG 路径，仅在启用 ``ocr_backend`` 时使用。
    """

    texts: List[CadText] = document.texts_in(bbox)
    inserts: List[CadInsert] = document.inserts_in(bbox)
    known_models = catalog.all_models_and_aliases()

    counter: Counter[str] = Counter()
    qty_overrides: Dict[str, int] = {}
    notes: Dict[str, List[str]] = {}

    # 1) 从 TEXT/MTEXT 中提取型号
    for t in texts:
        models = _find_models_in_text(t.text, known_models)
        qty = _extract_quantity(t.text) or 0
        for m in models:
            canonical = catalog.canonicalize(m)
            counter[canonical] += 1
            if qty:
                qty_overrides[canonical] = max(qty_overrides.get(canonical, 0), qty)
            if t.text:
                notes.setdefault(canonical, []).append(t.text.strip())

    # 2) INSERT 块名作为型号兜底
    for ins in inserts:
        canonical = catalog.canonicalize(ins.name)
        if canonical in catalog:
            counter[canonical] += 1

    # 3) OCR 兜底：当 TEXT/INSERT 都没找到任何已知型号时，调用 OCR
    if ocr_backend is not None and region_image and not counter:
        try:
            ocr_lines = ocr_backend.recognize(region_image)
        except Exception:  # noqa: BLE001 - OCR 不应阻塞主流程
            ocr_lines = []
        for line in ocr_lines:
            models = _find_models_in_text(line.text, known_models)
            qty = _extract_quantity(line.text) or 0
            for m in models:
                canonical = catalog.canonicalize(m)
                counter[canonical] += 1
                if qty:
                    qty_overrides[canonical] = max(qty_overrides.get(canonical, 0), qty)
                if line.text:
                    notes.setdefault(canonical, []).append(f"[OCR] {line.text.strip()}")

    items: List[EquipmentItem] = []
    for model, count in counter.items():
        product = catalog.get(model)
        qty = qty_overrides.get(model, count)
        items.append(
            EquipmentItem(
                model=model,
                region=region_name,
                quantity=qty,
                unit=(product.unit if product else "台"),
                params=dict(product.params) if product else {},
                brand=(product.brand if product else None),
                note=" | ".join(notes.get(model, [])[:3]),
            )
        )
    return items


def extract_from_regions(
    document: CadDocument,
    regions: Iterable[Tuple[str, BBox]],
    catalog: ProductCatalog,
    ocr_backend: Optional[OCRBackend] = None,
    region_images: Optional[Dict[str, str]] = None,
) -> List[EquipmentItem]:
    """对多个 ``(name, bbox)`` 区域批量识别。

    :param region_images: 区域名 → 已渲染 PNG 路径，启用 OCR 兜底时使用。
    """

    out: List[EquipmentItem] = []
    region_images = region_images or {}
    for name, bbox in regions:
        out.extend(
            extract_from_region(
                document,
                bbox,
                name,
                catalog,
                ocr_backend=ocr_backend,
                region_image=region_images.get(name),
            )
        )
    return out


def items_to_dataframe(items: Sequence[EquipmentItem]):
    """把识别结果转成 pandas DataFrame，便于后续报价。"""

    try:
        import pandas as pd  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ImportError("pandas 未安装；请 `pip install pandas`。") from exc

    rows = []
    for idx, it in enumerate(items, start=1):
        rows.append(
            {
                "序号": idx,
                "位置": it.region,
                "型号": it.model,
                "品牌": it.brand or "",
                "规格": "; ".join(f"{k}={v}" for k, v in it.params.items()),
                "数量": it.quantity,
                "单位": it.unit,
                "备注": it.note,
            }
        )
    return pd.DataFrame(rows)
