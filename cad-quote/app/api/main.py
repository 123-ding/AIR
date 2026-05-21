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
    from fastapi.responses import FileResponse, JSONResponse  # type: ignore
    from pydantic import BaseModel  # type: ignore
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "fastapi 未安装；请 `pip install fastapi uvicorn python-multipart`。"
    ) from exc

from ..cad.parser import parse_dxf
from ..catalog.catalog import ProductCatalog
from ..ocr.extractor import extract_from_regions
from ..quote.engine import build_quote
from ..quote.exporter import to_excel, quote_to_rows
from ..quote.strategies import available_strategies, create_strategy


app = FastAPI(title="CAD 图纸解析与报价清单生成", version="0.1.0")


class Region(BaseModel):
    name: str
    bbox: List[float]  # [xmin, ymin, xmax, ymax]


class QuoteRequest(BaseModel):
    regions: List[Region]
    strategy: str = "standard"
    strategy_params: dict = {}


_CATALOG: Optional[ProductCatalog] = None


def get_catalog() -> ProductCatalog:
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = ProductCatalog.default()
    return _CATALOG


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


@app.post("/quote")
async def quote_endpoint(
    file: UploadFile = File(..., description="DXF 文件"),
    request_json: str = Form(..., description="JSON 字符串，结构同 QuoteRequest"),
):
    import json

    try:
        body = QuoteRequest(**json.loads(request_json))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"无效的 request_json: {exc}")

    if not body.regions:
        raise HTTPException(status_code=400, detail="至少需要 1 个区域。")

    suffix = os.path.splitext(file.filename or "")[1].lower() or ".dxf"
    if suffix != ".dxf":
        raise HTTPException(
            status_code=400,
            detail="仅支持 .dxf 文件，请先将 .dwg 转换为 .dxf。",
        )

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        document = parse_dxf(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    catalog = get_catalog()
    regions = [(r.name, tuple(r.bbox)) for r in body.regions]
    items = extract_from_regions(document, regions, catalog)

    try:
        strategy = create_strategy(body.strategy, **body.strategy_params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    quote = build_quote(items, strategy, catalog=catalog)
    return JSONResponse(
        {
            "strategy": quote.strategy_name,
            "currency": quote.currency,
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
    if not body.regions:
        raise HTTPException(status_code=400, detail="至少需要 1 个区域。")

    suffix = os.path.splitext(file.filename or "")[1].lower() or ".dxf"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        document = parse_dxf(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    catalog = get_catalog()
    regions = [(r.name, tuple(r.bbox)) for r in body.regions]
    items = extract_from_regions(document, regions, catalog)
    strategy = create_strategy(body.strategy, **body.strategy_params)
    quote = build_quote(items, strategy, catalog=catalog)

    out_dir = tempfile.mkdtemp(prefix="quote_")
    out_path = os.path.join(out_dir, "quote.xlsx")
    to_excel(quote, out_path)
    return FileResponse(
        out_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="quote.xlsx",
    )
