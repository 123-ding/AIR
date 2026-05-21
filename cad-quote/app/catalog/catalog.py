"""型号库 (ProductCatalog)。

数据来源：YAML 文件，结构如下::

    products:
      - model: ABC-100
        brand: ACME
        unit: 台
        base_price: 1280.00
        aliases: [ABC100, ABC_100]
        params:
          power: 1.5kW
          voltage: 220V

支持别名映射 → 规范型号；查询接口 ``catalog.get(model)``、``model in catalog``。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional


@dataclass
class Product:
    model: str
    brand: str = ""
    unit: str = "台"
    base_price: float = 0.0
    params: Dict[str, str] = field(default_factory=dict)
    aliases: List[str] = field(default_factory=list)


class ProductCatalog:
    """型号库。可从 YAML 加载，也可在内存构造（便于测试）。"""

    def __init__(self, products: Optional[Iterable[Product]] = None) -> None:
        self._by_model: Dict[str, Product] = {}
        self._alias_to_model: Dict[str, str] = {}
        if products:
            for p in products:
                self.add(p)

    # ---- 构造与加载 ----
    @classmethod
    def from_yaml(cls, path: str) -> "ProductCatalog":
        try:
            import yaml  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise ImportError("PyYAML 未安装；请 `pip install PyYAML`。") from exc
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        products = []
        for raw in data.get("products", []) or []:
            products.append(
                Product(
                    model=str(raw["model"]).strip(),
                    brand=str(raw.get("brand", "")).strip(),
                    unit=str(raw.get("unit", "台")).strip(),
                    base_price=float(raw.get("base_price", 0.0)),
                    params={str(k): str(v) for k, v in (raw.get("params") or {}).items()},
                    aliases=[str(a).strip() for a in (raw.get("aliases") or [])],
                )
            )
        return cls(products)

    @classmethod
    def default(cls) -> "ProductCatalog":
        """加载内置的默认型号库。"""
        here = os.path.dirname(os.path.abspath(__file__))
        return cls.from_yaml(os.path.join(here, "default_catalog.yaml"))

    # ---- 增/查 ----
    def add(self, product: Product) -> None:
        key = product.model.upper()
        self._by_model[key] = product
        self._alias_to_model[key] = key
        for alias in product.aliases:
            self._alias_to_model[alias.upper()] = key

    def canonicalize(self, model: str) -> str:
        """把任意写法 / 别名归一化成规范型号。未知则返回原值（大写）。"""
        if not model:
            return ""
        key = model.upper().strip()
        return self._alias_to_model.get(key, key)

    def get(self, model: str) -> Optional[Product]:
        canon = self.canonicalize(model)
        return self._by_model.get(canon)

    def __contains__(self, model: str) -> bool:
        return self.get(model) is not None

    def __len__(self) -> int:
        return len(self._by_model)

    def all_models_and_aliases(self) -> List[str]:
        """返回所有型号与别名（保留原大小写），供文本扫描使用。"""
        out: List[str] = []
        for p in self._by_model.values():
            out.append(p.model)
            out.extend(p.aliases)
        return out

    def models(self) -> List[str]:
        return [p.model for p in self._by_model.values()]
