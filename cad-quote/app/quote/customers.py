"""客户分级与多币种配置。

用法::

    profile = CustomerProfile(level="gold", discount_factor=0.95, currency="USD")
    quote = build_quote(items, strategy, customer=profile, exchange_rate=0.14)

* ``discount_factor``：在策略最终单价上**再乘**一次，0.95 即 95% 价格。
* ``currency``：报价单展示币种。
* ``exchange_rate``：1 单位 CNY 对应 ``customer.currency`` 的金额（例如 1 CNY ≈ 0.14 USD）。
  缺省 1.0 表示不换算。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class CustomerProfile:
    level: str
    discount_factor: float = 1.0
    currency: str = "CNY"
    exchange_rate: float = 1.0  # 1 CNY → currency
    description: str = ""

    def __post_init__(self) -> None:
        if self.discount_factor <= 0:
            raise ValueError("discount_factor 必须 > 0")
        if self.exchange_rate <= 0:
            raise ValueError("exchange_rate 必须 > 0")


@dataclass
class CustomerRegistry:
    """客户等级登记表，可由 YAML 加载。"""

    profiles: Dict[str, CustomerProfile] = field(default_factory=dict)

    @classmethod
    def builtin(cls) -> "CustomerRegistry":
        """内置默认等级。"""

        return cls(
            profiles={
                "default": CustomerProfile("default", 1.0, "CNY", 1.0, "标准客户"),
                "silver": CustomerProfile("silver", 0.97, "CNY", 1.0, "白银客户 -3%"),
                "gold": CustomerProfile("gold", 0.95, "CNY", 1.0, "黄金客户 -5%"),
                "platinum": CustomerProfile(
                    "platinum", 0.92, "CNY", 1.0, "铂金客户 -8%"
                ),
            }
        )

    @classmethod
    def from_yaml(cls, path: str) -> "CustomerRegistry":
        try:
            import yaml  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise ImportError("PyYAML 未安装；请 `pip install PyYAML`。") from exc
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        profiles: Dict[str, CustomerProfile] = {}
        for raw in data.get("customers", []) or []:
            level = str(raw["level"]).strip()
            profiles[level] = CustomerProfile(
                level=level,
                discount_factor=float(raw.get("discount_factor", 1.0)),
                currency=str(raw.get("currency", "CNY")).strip().upper(),
                exchange_rate=float(raw.get("exchange_rate", 1.0)),
                description=str(raw.get("description", "")),
            )
        return cls(profiles=profiles)

    def get(self, level: str) -> Optional[CustomerProfile]:
        if not level:
            return None
        return self.profiles.get(level) or self.profiles.get(level.lower())

    def list_levels(self) -> List[str]:
        return sorted(self.profiles)


_DEFAULT_REGISTRY: Optional[CustomerRegistry] = None


def default_registry() -> CustomerRegistry:
    """加载默认客户分级；若用户在 ``CAD_QUOTE_DATA_DIR/customers.yaml`` 中提供，则用之。"""

    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is not None:
        return _DEFAULT_REGISTRY
    data_dir = os.environ.get("CAD_QUOTE_DATA_DIR")
    if data_dir:
        candidate = os.path.join(data_dir, "customers.yaml")
        if os.path.isfile(candidate):
            _DEFAULT_REGISTRY = CustomerRegistry.from_yaml(candidate)
            return _DEFAULT_REGISTRY
    _DEFAULT_REGISTRY = CustomerRegistry.builtin()
    return _DEFAULT_REGISTRY


def reset_default_registry() -> None:
    """主要用于测试：清空缓存。"""

    global _DEFAULT_REGISTRY
    _DEFAULT_REGISTRY = None
