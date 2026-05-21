"""自动区域识别。

P1 目标：在用户**没有手工框选**的情况下，自动从 DXF 中推断出若干分区，
作为后续报价的候选区域。

策略（按优先级）：

1. **闭合矩形多段线**：在图纸上常用一个 4 顶点闭合的 LWPOLYLINE 框出一个分区。
   返回所有面积合理（占图纸总面积 0.1% ~ 90%）的矩形 polyline 的 bbox。
2. **图层聚合**：当图层名匹配 ``AREA-*`` / ``ZONE-*`` / ``FRAME-*`` / 包含
   ``区`` / ``分区`` 等关键词时，把该图层上的所有文本/块的外包矩形作为一个分区。
3. **标题栏剔除**：图层名/文本中包含 ``TITLE`` / ``标题栏`` / ``图签`` 时跳过。

如果两种策略都没结果，会返回 ``[]`` —— 调用方此时应退化到"整张图"或要求用户手工框选。
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

from .parser import BBox, CadDocument, CadPolyline


_TITLE_RE = re.compile(r"(TITLE|标题栏|图签|图框)", re.IGNORECASE)
_AREA_LAYER_RE = re.compile(
    r"(AREA|ZONE|FRAME|REGION|分区|区域)", re.IGNORECASE
)


def _is_title_layer(layer: str) -> bool:
    return bool(_TITLE_RE.search(layer or ""))


def _is_area_layer(layer: str) -> bool:
    if _is_title_layer(layer):
        return False
    return bool(_AREA_LAYER_RE.search(layer or "")) or bool(
        re.search(r"区", layer or "")
    )


def _is_rectangle(poly: CadPolyline, tolerance: float = 1e-6) -> Optional[BBox]:
    """判断闭合多段线是否近似为轴对齐矩形；是则返回 bbox。"""

    if not poly.closed or len(poly.vertices) < 4:
        return None
    # 取唯一顶点（首尾相同时去重）
    verts = list(poly.vertices)
    if verts[0] == verts[-1]:
        verts = verts[:-1]
    if len(verts) != 4:
        return None
    xs = sorted({round(v[0], 6) for v in verts})
    ys = sorted({round(v[1], 6) for v in verts})
    if len(xs) != 2 or len(ys) != 2:
        return None
    # 4 个顶点必须正好对应 2x2 网格
    expected = {(xs[0], ys[0]), (xs[0], ys[1]), (xs[1], ys[0]), (xs[1], ys[1])}
    actual = {(round(v[0], 6), round(v[1], 6)) for v in verts}
    if expected != actual:
        return None
    width = xs[1] - xs[0]
    height = ys[1] - ys[0]
    if width <= tolerance or height <= tolerance:
        return None
    return (xs[0], ys[0], xs[1], ys[1])


def _bbox_area(bbox: BBox) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _document_bbox(document: CadDocument) -> Optional[BBox]:
    if document.extents:
        return document.extents
    pts: List[Tuple[float, float]] = []
    for t in document.texts:
        pts.append((t.x, t.y))
    for ins in document.inserts:
        pts.append((ins.x, ins.y))
    for p in document.polylines:
        pts.extend(p.vertices)
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _bboxes_overlap(a: BBox, b: BBox) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def detect_rectangle_regions(
    document: CadDocument,
    min_area_ratio: float = 0.001,
    max_area_ratio: float = 0.9,
) -> List[Tuple[str, BBox]]:
    """通过闭合矩形多段线检测区域。"""

    doc_bbox = _document_bbox(document)
    doc_area = _bbox_area(doc_bbox) if doc_bbox else 0.0

    found: List[Tuple[str, BBox]] = []
    for idx, poly in enumerate(document.polylines):
        if _is_title_layer(poly.layer):
            continue
        rect = _is_rectangle(poly)
        if rect is None:
            continue
        area = _bbox_area(rect)
        if doc_area > 0:
            ratio = area / doc_area
            if ratio < min_area_ratio or ratio > max_area_ratio:
                continue
        found.append((f"区域{idx + 1}", rect))
    return found


def detect_layer_regions(document: CadDocument) -> List[Tuple[str, BBox]]:
    """按图层名聚合文本/块为区域。"""

    by_layer: Dict[str, List[Tuple[float, float]]] = {}
    for t in document.texts:
        if _is_area_layer(t.layer):
            by_layer.setdefault(t.layer, []).append((t.x, t.y))
    for ins in document.inserts:
        if _is_area_layer(ins.layer):
            by_layer.setdefault(ins.layer, []).append((ins.x, ins.y))

    regions: List[Tuple[str, BBox]] = []
    for layer, pts in by_layer.items():
        if len(pts) < 2:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        bbox = (min(xs), min(ys), max(xs), max(ys))
        if _bbox_area(bbox) <= 0:
            continue
        regions.append((layer, bbox))
    return regions


def detect_regions(
    document: CadDocument,
    prefer: str = "auto",
) -> List[Tuple[str, BBox]]:
    """综合策略：先矩形，后图层；自动去重重叠区域。

    :param prefer: ``"rectangle"`` / ``"layer"`` / ``"auto"``。
    :return: 形如 ``[("区域1", (xmin, ymin, xmax, ymax)), ...]``。
    """

    rect_regions = detect_rectangle_regions(document)
    layer_regions = detect_layer_regions(document)

    if prefer == "rectangle":
        return rect_regions
    if prefer == "layer":
        return layer_regions

    # auto：矩形优先；图层区域若与已选矩形不重叠则补充
    chosen: List[Tuple[str, BBox]] = list(rect_regions)
    for name, bbox in layer_regions:
        if any(_bboxes_overlap(bbox, b) for _, b in chosen):
            continue
        chosen.append((name, bbox))
    return chosen
