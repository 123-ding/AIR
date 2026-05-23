"""报价引擎：把识别出来的设备清单按报价策略汇总为报价单。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence

from ..catalog.catalog import ProductCatalog
from ..ocr.extractor import EquipmentItem
from .customers import CustomerProfile
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
    customer_level: str = ""
    exchange_rate: float = 1.0


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
    customer: Optional[CustomerProfile] = None,
    exchange_rate: Optional[float] = None,
) -> Quote:
    """根据设备清单与报价策略构建一份报价单。

    :param aggregate: 是否按型号合并数量（默认 True）。
    :param customer: 可选客户档案；其 ``discount_factor`` 会作用在每行单价/小计，
        其 ``currency`` / ``exchange_rate`` 会决定最终报价币种和换算系数。
    :param exchange_rate: 显式覆盖换算系数（1 CNY → ``currency``）。
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

    # ---- 客户分级折扣（在策略报价之上再叠加）----
    cust_factor = 1.0
    final_currency = currency
    rate = exchange_rate if exchange_rate is not None else 1.0
    customer_level = ""
    if customer is not None:
        cust_factor = float(customer.discount_factor)
        final_currency = customer.currency or currency
        if exchange_rate is None:
            rate = float(customer.exchange_rate)
        customer_level = customer.level

    if cust_factor != 1.0 or rate != 1.0:
        new_lines: List[QuoteLine] = []
        for ln in lines:
            new_unit = round(ln.unit_price * cust_factor * rate, 2)
            new_subtotal = round(new_unit * ln.quantity, 2)
            extra_note = []
            if cust_factor != 1.0 and customer is not None:
                extra_note.append(
                    f"客户[{customer.level}]×{cust_factor:.3f}"
                )
            if rate != 1.0:
                extra_note.append(f"汇率×{rate:.4f}→{final_currency}")
            note = ln.note
            if extra_note:
                note = f"{note} | {' '.join(extra_note)}" if note else " ".join(extra_note)
            new_lines.append(
                QuoteLine(
                    model=ln.model,
                    quantity=ln.quantity,
                    unit=ln.unit,
                    unit_price=new_unit,
                    discount=round(ln.discount * cust_factor, 4),
                    subtotal=new_subtotal,
                    brand=ln.brand,
                    note=note,
                )
            )
        lines = new_lines

    subtotal = round(sum(l.subtotal for l in lines), 2)
    extras: List[tuple] = []
    total = subtotal

    if isinstance(strategy, BundleStrategy):
        # 注意：人工/运输也按客户因子与汇率换算
        if strategy.labor:
            extras.append(("人工费", round(strategy.labor * cust_factor * rate, 2)))
        if strategy.transport:
            extras.append(
                ("运输费", round(strategy.transport * cust_factor * rate, 2))
            )
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
        currency=final_currency,
        customer_level=customer_level,
        exchange_rate=rate,
    )
