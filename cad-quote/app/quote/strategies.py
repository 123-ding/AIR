"""报价策略（Strategy Pattern）。

每个策略实现 :meth:`QuoteStrategy.price_line`，输入一行 :class:`QuoteInput`
（型号、基准价、数量、单位），返回 :class:`QuoteLine`（单价、折扣、小计、备注）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Type


@dataclass
class QuoteInput:
    model: str
    base_price: float
    quantity: int
    unit: str = "台"
    brand: str = ""


@dataclass
class QuoteLine:
    model: str
    quantity: int
    unit: str
    unit_price: float
    discount: float  # 实际折扣率 (0~1)
    subtotal: float
    brand: str = ""
    note: str = ""


# ---------- 抽象基类 ----------
class QuoteStrategy:
    """报价策略基类。子类应实现 :meth:`price_line`。"""

    type_name: str = "abstract"

    def __init__(self, **params) -> None:
        self.params: Dict = params

    def price_line(self, item: QuoteInput) -> QuoteLine:  # pragma: no cover - 抽象
        raise NotImplementedError

    def price_all(self, items: List[QuoteInput]) -> List[QuoteLine]:
        return [self.price_line(it) for it in items]


# ---------- 注册表 ----------
_REGISTRY: Dict[str, Type[QuoteStrategy]] = {}


def register(cls: Type[QuoteStrategy]) -> Type[QuoteStrategy]:
    _REGISTRY[cls.type_name] = cls
    return cls


def create_strategy(type_name: str, **params) -> QuoteStrategy:
    if type_name not in _REGISTRY:
        raise ValueError(
            f"未知报价策略 '{type_name}'。可用策略：{sorted(_REGISTRY)}"
        )
    return _REGISTRY[type_name](**params)


def available_strategies() -> List[str]:
    return sorted(_REGISTRY)


# ---------- 标准定价 ----------
@register
class StandardStrategy(QuoteStrategy):
    """标准价：单价 = base_price × (1 + tax_rate)。"""

    type_name = "standard"

    def __init__(self, tax_rate: float = 0.0) -> None:
        super().__init__(tax_rate=tax_rate)
        self.tax_rate = float(tax_rate)

    def price_line(self, item: QuoteInput) -> QuoteLine:
        unit_price = round(item.base_price * (1 + self.tax_rate), 2)
        subtotal = round(unit_price * item.quantity, 2)
        note = f"标准价，税率 {self.tax_rate:.0%}"
        return QuoteLine(
            model=item.model,
            quantity=item.quantity,
            unit=item.unit,
            unit_price=unit_price,
            discount=1.0,
            subtotal=subtotal,
            brand=item.brand,
            note=note,
        )


# ---------- 折扣定价 ----------
@register
class DiscountStrategy(QuoteStrategy):
    """折扣价：单价 = base_price × discount × brand_factor × customer_level_factor。"""

    type_name = "discount"

    def __init__(
        self,
        discount: float = 1.0,
        brand_factors: Optional[Dict[str, float]] = None,
        customer_level: str = "default",
        customer_level_factors: Optional[Dict[str, float]] = None,
        tax_rate: float = 0.0,
    ) -> None:
        super().__init__(
            discount=discount,
            brand_factors=brand_factors,
            customer_level=customer_level,
            customer_level_factors=customer_level_factors,
            tax_rate=tax_rate,
        )
        if not 0 < discount <= 1.0:
            raise ValueError("discount 必须在 (0, 1] 之间。")
        self.discount = float(discount)
        self.brand_factors = brand_factors or {}
        self.customer_level = customer_level
        self.customer_level_factors = customer_level_factors or {"default": 1.0}
        self.tax_rate = float(tax_rate)

    def price_line(self, item: QuoteInput) -> QuoteLine:
        brand_factor = float(self.brand_factors.get(item.brand, 1.0))
        cust_factor = float(
            self.customer_level_factors.get(self.customer_level, 1.0)
        )
        effective = self.discount * brand_factor * cust_factor
        unit_price = round(item.base_price * effective * (1 + self.tax_rate), 2)
        subtotal = round(unit_price * item.quantity, 2)
        note = (
            f"折扣 {self.discount:.2f} × 品牌系数 {brand_factor:.2f} × "
            f"客户等级[{self.customer_level}] {cust_factor:.2f}，税率 {self.tax_rate:.0%}"
        )
        return QuoteLine(
            model=item.model,
            quantity=item.quantity,
            unit=item.unit,
            unit_price=unit_price,
            discount=round(effective, 4),
            subtotal=subtotal,
            brand=item.brand,
            note=note,
        )


# ---------- 阶梯定价 ----------
@dataclass
class Tier:
    min_qty: int
    price: float  # 该档位单价（覆盖 base_price）


@register
class TieredStrategy(QuoteStrategy):
    """阶梯价：按数量落入档位取对应单价。

    ``tiers`` 形如 ``[{"min_qty": 1, "price": 1200}, {"min_qty": 10, "price": 1080}]``。
    fallback 行为：若没有任何一档 ``min_qty <= qty``，使用 ``base_price``。
    """

    type_name = "tiered"

    def __init__(self, tiers: List[Dict], tax_rate: float = 0.0) -> None:
        super().__init__(tiers=tiers, tax_rate=tax_rate)
        if not tiers:
            raise ValueError("tiers 不能为空。")
        self.tiers: List[Tier] = sorted(
            [Tier(int(t["min_qty"]), float(t["price"])) for t in tiers],
            key=lambda t: t.min_qty,
        )
        self.tax_rate = float(tax_rate)

    def _pick(self, qty: int, base_price: float) -> Tier:
        chosen: Optional[Tier] = None
        for tier in self.tiers:
            if qty >= tier.min_qty:
                chosen = tier
        return chosen or Tier(min_qty=qty, price=base_price)

    def price_line(self, item: QuoteInput) -> QuoteLine:
        tier = self._pick(item.quantity, item.base_price)
        unit_price = round(tier.price * (1 + self.tax_rate), 2)
        subtotal = round(unit_price * item.quantity, 2)
        discount = round(tier.price / item.base_price, 4) if item.base_price else 1.0
        note = f"阶梯价：数量≥{tier.min_qty} → 单价 {tier.price:.2f}（税率 {self.tax_rate:.0%}）"
        return QuoteLine(
            model=item.model,
            quantity=item.quantity,
            unit=item.unit,
            unit_price=unit_price,
            discount=discount,
            subtotal=subtotal,
            brand=item.brand,
            note=note,
        )


# ---------- 打包定价 ----------
@register
class BundleStrategy(QuoteStrategy):
    """项目打包价：在标准价基础上加入人工、运输并按总价上浮。"""

    type_name = "bundle"

    def __init__(
        self,
        labor: float = 0.0,
        transport: float = 0.0,
        extra_pct: float = 0.0,
        tax_rate: float = 0.0,
    ) -> None:
        super().__init__(
            labor=labor, transport=transport, extra_pct=extra_pct, tax_rate=tax_rate
        )
        self.labor = float(labor)
        self.transport = float(transport)
        self.extra_pct = float(extra_pct)
        self.tax_rate = float(tax_rate)

    def price_line(self, item: QuoteInput) -> QuoteLine:
        # 单行先按标准计算，最终在汇总时叠加 labor/transport/extra_pct
        unit_price = round(item.base_price * (1 + self.tax_rate), 2)
        subtotal = round(unit_price * item.quantity, 2)
        note = "打包价（人工/运输/上浮在汇总中应用）"
        return QuoteLine(
            model=item.model,
            quantity=item.quantity,
            unit=item.unit,
            unit_price=unit_price,
            discount=1.0,
            subtotal=subtotal,
            brand=item.brand,
            note=note,
        )
