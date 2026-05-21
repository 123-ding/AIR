"""型号库管理 API（``/admin/catalog/...``）。"""

from __future__ import annotations

from typing import Dict, List, Optional

try:
    from fastapi import APIRouter, HTTPException  # type: ignore
    from pydantic import BaseModel, Field  # type: ignore
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "fastapi 未安装；请 `pip install fastapi uvicorn python-multipart`。"
    ) from exc

from ..catalog.store import CatalogStore


router = APIRouter(prefix="/admin/catalog", tags=["catalog-admin"])


_STORE: Optional[CatalogStore] = None


def get_store() -> CatalogStore:
    global _STORE
    if _STORE is None:
        _STORE = CatalogStore()
    return _STORE


def set_store(store: CatalogStore) -> None:
    """供测试 / API 启动时注入定制的 ``CatalogStore``。"""

    global _STORE
    _STORE = store


class ProductIn(BaseModel):
    model: str
    brand: str = ""
    unit: str = "台"
    base_price: float = 0.0
    aliases: List[str] = Field(default_factory=list)
    params: Dict[str, str] = Field(default_factory=dict)


class PriceUpdateIn(BaseModel):
    price: float
    user: str = ""
    note: str = ""


@router.get("/products")
def list_products():
    store = get_store()
    products = store.list_products()
    return {"count": len(products), "products": products}


@router.get("/products/{model}")
def get_product(model: str):
    store = get_store()
    p = store.get_product(model)
    if p is None:
        raise HTTPException(status_code=404, detail=f"型号 {model!r} 不存在。")
    return {
        "model": p.model,
        "brand": p.brand,
        "unit": p.unit,
        "base_price": p.base_price,
        "aliases": list(p.aliases),
        "params": dict(p.params),
    }


@router.post("/products")
def upsert_product(payload: ProductIn, user: str = ""):
    store = get_store()
    try:
        product = store.upsert_product(payload.model_dump(), user=user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "model": product.model}


@router.delete("/products/{model}")
def delete_product(model: str):
    store = get_store()
    deleted = store.delete_product(model)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"型号 {model!r} 不存在。")
    return {"ok": True, "model": model}


@router.post("/products/{model}/price")
def update_price(model: str, payload: PriceUpdateIn):
    store = get_store()
    try:
        product = store.update_price(
            model, payload.price, user=payload.user, note=payload.note
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"ok": True, "model": product.model, "base_price": product.base_price}


@router.get("/products/{model}/price-history")
def price_history(model: str):
    store = get_store()
    return {"model": model, "history": store.price_history(model)}


@router.get("/price-history")
def all_price_history():
    store = get_store()
    return {"history": store.price_history()}
