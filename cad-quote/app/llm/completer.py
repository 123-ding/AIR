"""把 LLM 后端应用到设备清单上，补全缺失参数。"""

from __future__ import annotations

from typing import List, Optional, Sequence

from ..catalog.catalog import ProductCatalog
from ..ocr.extractor import EquipmentItem
from .backends import LLMBackend


def complete_items(
    items: Sequence[EquipmentItem],
    backend: LLMBackend,
    catalog: Optional[ProductCatalog] = None,
    schema: Optional[List[str]] = None,
    only_missing: bool = True,
) -> List[EquipmentItem]:
    """对设备清单逐条调 LLM 后端补全参数。

    :param only_missing: ``True`` 时仅对参数为空的项调用，避免不必要请求。
    :return: 一个**新列表**，元素是补完后的 :class:`EquipmentItem`（不就地修改）。
    """

    out: List[EquipmentItem] = []
    for it in items:
        existing_params = dict(it.params or {})
        # 若 catalog 已经给出参数且 only_missing，直接跳过
        if only_missing and existing_params:
            out.append(it)
            continue

        # 给 LLM 一些上下文：catalog 中相关品牌、原始 note
        hint_parts: List[str] = []
        if it.note:
            hint_parts.append(it.note)
        if catalog is not None:
            product = catalog.get(it.model)
            if product is not None and product.params:
                hint_parts.append(
                    "; ".join(f"{k}={v}" for k, v in product.params.items())
                )
        hint = " | ".join(hint_parts)

        try:
            suggestion = backend.complete_params(
                model=it.model,
                known_params=existing_params,
                hint_text=hint,
                schema=schema,
            )
        except Exception:  # noqa: BLE001 - LLM 失败不应中断流程
            out.append(it)
            continue

        merged = dict(existing_params)
        for k, v in (suggestion.params or {}).items():
            if k not in merged and v:
                merged[k] = str(v)

        if merged == existing_params:
            out.append(it)
            continue

        new_note = it.note
        if suggestion.params:
            tag = f"[LLM:{suggestion.source}]"
            new_note = f"{new_note} {tag}".strip() if new_note else tag

        out.append(
            EquipmentItem(
                model=it.model,
                region=it.region,
                quantity=it.quantity,
                unit=it.unit,
                params=merged,
                brand=it.brand,
                note=new_note,
            )
        )
    return out
