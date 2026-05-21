"""报价引擎：把识别出来的设备清单按报价策略汇总为报价单。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence

from ..catalog.catalog import ProductCatalog
from ..ocr.extractor import EquipmentItem
from .strategies import (
    BundleStrategy,
    QuoteInput,
    QuoteLine,
    QuoteStrategy,
)


@dataclass
class Quote:
    """一份报价单。"""

    strategy_name: str
    lines: List[QuoteLine] = field(default_factory=list)
    subtotal: float = 0.0
    extras: List[tuple] = field(default_factory=list)  # [(label, amount), ...]
    total: float = 0.0
    currency: str = "CNY"


def _aggregate_items(
    items: Sequence[EquipmentItem],
) -> List[EquipmentItem]:
    """同型号合并数量，便于报价。"""

    agg: dict = {}
    for it in items:
        key = it.model
        if key in agg:
            existing = agg[key]
            agg[key] = EquipmentItem(
                model=existing.model,
                region=", ".join(sorted({existing.region, it.region})),
                quantity=existing.quantity + it.quantity,
                unit=existing.unit or it.unit,
                params=existing.params or it.params,
                brand=existing.brand or it.brand,
                note=existing.note,
            )
        else:
            agg[key] = it
    return list(agg.values())


def build_quote(
    items: Iterable[EquipmentItem],
    strategy: QuoteStrategy,
    catalog: Optional[ProductCatalog] = None,
    currency: str = "CNY",
    aggregate: bool = True,
) -> Quote:
    """根据设备清单与报价策略构建一份报价单。

    :param aggregate: 是否按型号合并数量（默认 True）。
    """

    item_list = list(items)
    if aggregate:
        item_list = _aggregate_items(item_list)

    quote_inputs: List[QuoteInput] = []
    for it in item_list:
        base_price = 0.0
        brand = it.brand or ""
        unit = it.unit or "台"
        if catalog is not None:
            product = catalog.get(it.model)
            if product is not None:
                base_price = product.base_price
                brand = brand or product.brand
                unit = unit or product.unit
        quote_inputs.append(
            QuoteInput(
                model=it.model,
                base_price=base_price,
                quantity=it.quantity,
                unit=unit,
                brand=brand,
            )
        )

    lines = strategy.price_all(quote_inputs)
    subtotal = round(sum(l.subtotal for l in lines), 2)
    extras: List[tuple] = []
    total = subtotal

    if isinstance(strategy, BundleStrategy):
        if strategy.labor:
            extras.append(("人工费", round(strategy.labor, 2)))
        if strategy.transport:
            extras.append(("运输费", round(strategy.transport, 2)))
        total = subtotal + sum(amount for _, amount in extras)
        if strategy.extra_pct:
            uplift = round(total * strategy.extra_pct, 2)
            extras.append((f"整体上浮 {strategy.extra_pct:.0%}", uplift))
            total += uplift

    total = round(total, 2)
    return Quote(
        strategy_name=strategy.type_name,
        lines=lines,
        subtotal=subtotal,
        extras=extras,
        total=total,
        currency=currency,
    )
