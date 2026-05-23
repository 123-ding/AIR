"""可写型号库 + 价格历史。

P1 目标：在 P0 只读的 ``ProductCatalog`` 基础上，增加：

* 持久化到磁盘（YAML，结构兼容 ``default_catalog.yaml``）
* 增 / 删 / 改 / 查 API
* 价格变更历史（按型号追加 JSON 行：时间戳 / 旧价 / 新价 / 备注 / 操作人）

约定：
* 默认路径取环境变量 ``CAD_QUOTE_DATA_DIR``，缺省为 ``<repo>/cad-quote/data``。
* 历史用 JSON Lines（``price_history.jsonl``），便于追加 / 不破坏旧记录。
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from .catalog import Product, ProductCatalog


def default_data_dir() -> str:
    env = os.environ.get("CAD_QUOTE_DATA_DIR")
    if env:
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "data"))


@dataclass
class PriceHistoryEntry:
    model: str
    old_price: float
    new_price: float
    timestamp: float = field(default_factory=time.time)
    user: str = ""
    note: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def _product_to_dict(p: Product) -> Dict[str, object]:
    return {
        "model": p.model,
        "brand": p.brand,
        "unit": p.unit,
        "base_price": p.base_price,
        "aliases": list(p.aliases),
        "params": dict(p.params),
    }


def _dict_to_product(raw: Dict[str, object]) -> Product:
    params_raw = raw.get("params") or {}
    aliases_raw = raw.get("aliases") or []
    return Product(
        model=str(raw["model"]).strip(),
        brand=str(raw.get("brand", "")).strip(),
        unit=str(raw.get("unit", "台")).strip(),
        base_price=float(raw.get("base_price", 0.0)),
        params={str(k): str(v) for k, v in dict(params_raw).items()},
        aliases=[str(a).strip() for a in list(aliases_raw)],
    )


class CatalogStore:
    """可写型号库。线程安全，文件操作加锁。"""

    CATALOG_FILE = "user_catalog.yaml"
    HISTORY_FILE = "price_history.jsonl"

    def __init__(self, data_dir: Optional[str] = None) -> None:
        self.data_dir = data_dir or default_data_dir()
        os.makedirs(self.data_dir, exist_ok=True)
        self._catalog_path = os.path.join(self.data_dir, self.CATALOG_FILE)
        self._history_path = os.path.join(self.data_dir, self.HISTORY_FILE)
        self._lock = threading.RLock()
        # 内存中持有一份 ProductCatalog
        self._catalog = self._load_catalog()

    # ---- 持久化 ----
    def _load_catalog(self) -> ProductCatalog:
        if not os.path.exists(self._catalog_path):
            return ProductCatalog()
        try:
            return ProductCatalog.from_yaml(self._catalog_path)
        except Exception:
            return ProductCatalog()

    def _dump_catalog(self) -> None:
        try:
            import yaml  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise ImportError("PyYAML 未安装；请 `pip install PyYAML`。") from exc
        data = {
            "products": [
                _product_to_dict(p) for p in sorted(
                    self._catalog._by_model.values(), key=lambda x: x.model
                )
            ]
        }
        tmp = self._catalog_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
        os.replace(tmp, self._catalog_path)

    # ---- 查询 ----
    def catalog(self) -> ProductCatalog:
        return self._catalog

    def list_products(self) -> List[Dict[str, object]]:
        with self._lock:
            return [_product_to_dict(p) for p in self._catalog._by_model.values()]

    def get_product(self, model: str) -> Optional[Product]:
        with self._lock:
            return self._catalog.get(model)

    # ---- 增/改/删 ----
    def upsert_product(self, raw: Dict[str, object], user: str = "") -> Product:
        product = _dict_to_product(raw)
        if not product.model:
            raise ValueError("型号 (model) 不能为空。")
        with self._lock:
            existing = self._catalog.get(product.model)
            old_price = existing.base_price if existing else None
            self._catalog.add(product)
            self._dump_catalog()
            if existing and old_price is not None and old_price != product.base_price:
                self._append_history(
                    PriceHistoryEntry(
                        model=product.model,
                        old_price=float(old_price),
                        new_price=float(product.base_price),
                        user=user,
                        note="upsert",
                    )
                )
        return product

    def delete_product(self, model: str) -> bool:
        with self._lock:
            canon = self._catalog.canonicalize(model)
            if canon not in self._catalog._by_model:
                return False
            product = self._catalog._by_model.pop(canon)
            # 同步清理别名映射
            keys_to_drop = [
                k for k, v in self._catalog._alias_to_model.items() if v == canon
            ]
            for k in keys_to_drop:
                self._catalog._alias_to_model.pop(k, None)
            self._dump_catalog()
            return product is not None

    def update_price(
        self, model: str, new_price: float, user: str = "", note: str = ""
    ) -> Product:
        with self._lock:
            product = self._catalog.get(model)
            if product is None:
                raise KeyError(f"型号 {model!r} 不存在。")
            old_price = product.base_price
            product.base_price = float(new_price)
            self._dump_catalog()
            if old_price != new_price:
                self._append_history(
                    PriceHistoryEntry(
                        model=product.model,
                        old_price=float(old_price),
                        new_price=float(new_price),
                        user=user,
                        note=note,
                    )
                )
            return product

    # ---- 价格历史 ----
    def _append_history(self, entry: PriceHistoryEntry) -> None:
        with open(self._history_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

    def price_history(self, model: Optional[str] = None) -> List[Dict[str, object]]:
        if not os.path.exists(self._history_path):
            return []
        canon = self._catalog.canonicalize(model) if model else None
        out: List[Dict[str, object]] = []
        with open(self._history_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if canon is not None and str(rec.get("model", "")).upper() != canon:
                    continue
                out.append(rec)
        return out
