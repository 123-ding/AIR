"""FastAPI 入口：上传 DXF → 区域识别 → 报价单。

启动：``uvicorn cad_quote.app.api.main:app --reload``
或从仓库根目录：``uvicorn app.api.main:app --app-dir cad-quote --reload``
"""

from __future__ import annotations

import os
import tempfile
from typing import List, Optional

try:
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile  # type: ignore
    from fastapi.middleware.cors import CORSMiddleware  # type: ignore
    from fastapi.responses import FileResponse, JSONResponse  # type: ignore
    from pydantic import BaseModel  # type: ignore
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "fastapi 未安装；请 `pip install fastapi uvicorn python-multipart`。"
    ) from exc

from ..cad.auto_regions import detect_regions
from ..cad.parser import parse_cad
from ..catalog.catalog import ProductCatalog
from ..ocr.backends import make_backend
from ..ocr.extractor import extract_from_regions
from ..quote.customers import default_registry as default_customer_registry
from ..quote.engine import build_quote
from ..quote.exporter import to_excel, to_pdf, quote_to_rows
from ..quote.strategies import available_strategies, create_strategy
from .admin import get_store, router as admin_router


app = FastAPI(title="CAD 图纸解析与报价清单生成", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(admin_router)


# 如果前端已构建（cad-quote/frontend/dist），就把它挂在 / 上提供静态服务，
# 实现「单进程交付」。前端没构建时，用户访问 / 会得到 API 的健康状态而非 404。
def _mount_frontend() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    dist = os.path.normpath(os.path.join(here, "..", "..", "frontend", "dist"))
    if not os.path.isdir(dist):
        return
    try:
        from fastapi.staticfiles import StaticFiles  # type: ignore
    except ImportError:  # pragma: no cover
        return
    app.mount("/ui", StaticFiles(directory=dist, html=True), name="frontend")


_mount_frontend()


class Region(BaseModel):
    name: str
    bbox: List[float]  # [xmin, ymin, xmax, ymax]


class QuoteRequest(BaseModel):
    regions: List[Region]
    strategy: str = "standard"
    strategy_params: dict = {}
    ocr_backend: Optional[str] = None
    ocr_params: dict = {}
    customer_level: Optional[str] = None
    currency: Optional[str] = None
    exchange_rate: Optional[float] = None
    llm_backend: Optional[str] = None
    llm_params: dict = {}


_DEFAULT_CATALOG: Optional[ProductCatalog] = None


def get_catalog() -> ProductCatalog:
    """优先使用用户管理的型号库（CatalogStore）；为空时退化到内置默认库。"""

    store = get_store()
    cat = store.catalog()
    if len(cat) > 0:
        return cat
    global _DEFAULT_CATALOG
    if _DEFAULT_CATALOG is None:
        _DEFAULT_CATALOG = ProductCatalog.default()
    return _DEFAULT_CATALOG


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/strategies")
def list_strategies():
    return {"strategies": available_strategies()}


@app.get("/catalog")
def list_catalog():
    cat = get_catalog()
    return {"count": len(cat), "models": cat.models()}


def _validate_body_and_suffix(file: UploadFile, body: "QuoteRequest") -> str:
    if not body.regions:
        raise HTTPException(status_code=400, detail="至少需要 1 个区域。")
    suffix = os.path.splitext(file.filename or "")[1].lower() or ".dxf"
    if suffix not in (".dxf", ".dwg"):
        raise HTTPException(status_code=400, detail="仅支持 .dxf / .dwg 文件。")
    return suffix


async def _read_file(file: UploadFile) -> bytes:
    return await file.read()


def _apply_customer_and_llm(items, catalog, body: "QuoteRequest"):
    """LLM 补全 + 选择客户档案；返回 ``(items, customer)``。"""

    if body.llm_backend:
        from ..llm import complete_items, make_backend as make_llm_backend

        try:
            llm_backend = make_llm_backend(body.llm_backend, **(body.llm_params or {}))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"LLM 后端构造失败: {exc}")
        items = complete_items(items, llm_backend, catalog=catalog)

    customer = None
    if body.customer_level:
        customer = default_customer_registry().get(body.customer_level)
        if customer is None:
            raise HTTPException(
                status_code=400, detail=f"未知客户等级: {body.customer_level}"
            )
    return items, customer


def _build_quote_from_upload(
    file_bytes: bytes, suffix: str, body: "QuoteRequest"
):
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name
    try:
        document = parse_cad(tmp_path)
        catalog = get_catalog()
        regions = [(r.name, tuple(r.bbox)) for r in body.regions]

        ocr_backend = None
        region_images = None
        if body.ocr_backend:
            try:
                ocr_backend = make_backend(
                    body.ocr_backend, **(body.ocr_params or {})
                )
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(
                    status_code=400, detail=f"OCR 后端构造失败: {exc}"
                )
            try:
                from ..cad.renderer import render_regions

                tmp_dir = tempfile.mkdtemp(prefix="ocr_regions_")
                paths = render_regions(
                    tmp_path, [tuple(r.bbox) for r in body.regions], tmp_dir
                )
                region_images = {
                    body.regions[i].name: paths[i]
                    for i in range(min(len(paths), len(body.regions)))
                }
            except Exception:  # noqa: BLE001
                region_images = None

        items = extract_from_regions(
            document,
            regions,
            catalog,
            ocr_backend=ocr_backend,
            region_images=region_images,
        )
        items, customer = _apply_customer_and_llm(items, catalog, body)

        try:
            strategy = create_strategy(body.strategy, **body.strategy_params)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        currency = body.currency or (customer.currency if customer else "CNY")
        return build_quote(
            items,
            strategy,
            catalog=catalog,
            currency=currency,
            customer=customer,
            exchange_rate=body.exchange_rate,
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@app.post("/quote")
async def quote_endpoint(
    file: UploadFile = File(..., description="DXF / DWG 文件"),
    request_json: str = Form(..., description="JSON 字符串，结构同 QuoteRequest"),
):
    import json

    try:
        body = QuoteRequest(**json.loads(request_json))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"无效的 request_json: {exc}")
    suffix = _validate_body_and_suffix(file, body)
    file_bytes = await _read_file(file)
    quote = _build_quote_from_upload(file_bytes, suffix, body)
    return JSONResponse(
        {
            "strategy": quote.strategy_name,
            "currency": quote.currency,
            "customer_level": quote.customer_level,
            "exchange_rate": quote.exchange_rate,
            "lines": quote_to_rows(quote),
            "subtotal": quote.subtotal,
            "extras": [{"label": l, "amount": a} for l, a in quote.extras],
            "total": quote.total,
        }
    )


@app.post("/quote/excel")
async def quote_excel(
    file: UploadFile = File(...),
    request_json: str = Form(...),
):
    import json

    body = QuoteRequest(**json.loads(request_json))
    suffix = _validate_body_and_suffix(file, body)
    file_bytes = await _read_file(file)
    quote = _build_quote_from_upload(file_bytes, suffix, body)

    out_dir = tempfile.mkdtemp(prefix="quote_")
    out_path = os.path.join(out_dir, "quote.xlsx")
    to_excel(quote, out_path)
    return FileResponse(
        out_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="quote.xlsx",
    )


@app.post("/quote/pdf")
async def quote_pdf(
    file: UploadFile = File(...),
    request_json: str = Form(...),
    customer_name: str = Form(""),
):
    import json

    body = QuoteRequest(**json.loads(request_json))
    suffix = _validate_body_and_suffix(file, body)
    file_bytes = await _read_file(file)
    quote = _build_quote_from_upload(file_bytes, suffix, body)

    out_dir = tempfile.mkdtemp(prefix="quote_pdf_")
    out_path = os.path.join(out_dir, "quote.pdf")
    try:
        to_pdf(quote, out_path, customer_name=customer_name)
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return FileResponse(
        out_path,
        media_type="application/pdf",
        filename="quote.pdf",
    )


@app.get("/customers")
def list_customers():
    registry = default_customer_registry()
    return {
        "customers": [
            {
                "level": p.level,
                "discount_factor": p.discount_factor,
                "currency": p.currency,
                "exchange_rate": p.exchange_rate,
                "description": p.description,
            }
            for p in (registry.profiles[k] for k in registry.list_levels())
        ]
    }


@app.post("/auto-regions")
async def auto_regions(
    file: UploadFile = File(..., description="DXF 文件"),
    prefer: str = Form("auto", description="rectangle / layer / auto"),
):
    """根据 DXF 自动识别候选区域。"""

    suffix = os.path.splitext(file.filename or "")[1].lower() or ".dxf"
    if suffix not in (".dxf", ".dwg"):
        raise HTTPException(status_code=400, detail="仅支持 .dxf / .dwg 文件。")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        document = parse_cad(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    regions = detect_regions(document, prefer=prefer)
    return {
        "extents": list(document.extents) if document.extents else None,
        "regions": [
            {"name": name, "bbox": list(bbox)} for name, bbox in regions
        ],
    }


@app.post("/preview")
async def preview(
    file: UploadFile = File(..., description="DXF 文件"),
    dpi: int = Form(120),
):
    """渲染整张 DXF 为 PNG 用于前端预览。

    返回 ``{"image": "/preview/<token>.png", "extents": [xmin, ymin, xmax, ymax],
    "size": [w, h]}``。前端可基于 ``extents`` 把像素 bbox 反算回 DXF 坐标。
    """

    suffix = os.path.splitext(file.filename or "")[1].lower() or ".dxf"
    if suffix not in (".dxf", ".dwg"):
        raise HTTPException(status_code=400, detail="仅支持 .dxf / .dwg 文件。")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        dxf_path = tmp.name

    try:
        document = parse_cad(dxf_path)
        # 选取整张图作为 bbox：优先使用 EXTMIN/EXTMAX，缺失时用文档 bbox
        from ..cad.auto_regions import _document_bbox  # 内部工具
        from ..cad.renderer import render_regions

        bbox = document.extents or _document_bbox(document)
        if bbox is None:
            raise HTTPException(status_code=400, detail="DXF 中没有可渲染的实体。")
        out_dir = tempfile.mkdtemp(prefix="preview_")
        paths = render_regions(dxf_path, [bbox], out_dir, dpi=dpi)
        if not paths:
            raise HTTPException(status_code=500, detail="渲染失败。")
        try:
            from PIL import Image  # type: ignore

            with Image.open(paths[0]) as im:
                size = [im.width, im.height]
        except Exception:
            size = [0, 0]
        return FileResponse(
            paths[0],
            media_type="image/png",
            headers={
                "X-Cad-Extents": ",".join(str(v) for v in bbox),
                "X-Cad-Size": ",".join(str(v) for v in size),
            },
        )
    finally:
        try:
            os.unlink(dxf_path)
        except OSError:
            pass
