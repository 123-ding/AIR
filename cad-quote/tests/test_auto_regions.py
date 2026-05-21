"""测试自动区域识别。"""

from app.cad.auto_regions import (
    detect_layer_regions,
    detect_rectangle_regions,
    detect_regions,
)
from app.cad.parser import CadDocument, CadInsert, CadPolyline, CadText


def _rect_polyline(xmin, ymin, xmax, ymax, layer="0", closed=True) -> CadPolyline:
    return CadPolyline(
        vertices=[(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)],
        layer=layer,
        closed=closed,
    )


def test_detect_rectangle_regions_basic():
    doc = CadDocument(
        polylines=[
            _rect_polyline(0, 0, 100, 50),
            _rect_polyline(120, 0, 200, 50),
        ],
        extents=(0, 0, 200, 100),
    )
    regions = detect_rectangle_regions(doc)
    bboxes = sorted([bbox for _, bbox in regions])
    assert (0, 0, 100, 50) in bboxes
    assert (120, 0, 200, 50) in bboxes


def test_open_polylines_are_ignored():
    doc = CadDocument(
        polylines=[_rect_polyline(0, 0, 100, 50, closed=False)],
        extents=(0, 0, 200, 100),
    )
    assert detect_rectangle_regions(doc) == []


def test_title_block_layer_skipped():
    doc = CadDocument(
        polylines=[
            _rect_polyline(0, 0, 50, 50, layer="TITLE-BLOCK"),
            _rect_polyline(60, 0, 100, 50, layer="DEVICES"),
        ],
        extents=(0, 0, 100, 100),
    )
    regions = detect_rectangle_regions(doc)
    assert len(regions) == 1
    assert regions[0][1] == (60, 0, 100, 50)


def test_too_small_or_too_large_rectangles_filtered():
    doc = CadDocument(
        polylines=[
            _rect_polyline(0, 0, 1, 1),  # 极小 → 被过滤
            _rect_polyline(0, 0, 1000, 1000),  # 占满整图 → 被过滤
            _rect_polyline(100, 100, 400, 400),  # 合理 → 保留
        ],
        extents=(0, 0, 1000, 1000),
    )
    regions = detect_rectangle_regions(doc)
    assert [bbox for _, bbox in regions] == [(100, 100, 400, 400)]


def test_detect_layer_regions_groups_by_layer():
    doc = CadDocument(
        texts=[
            CadText(text="A", x=10, y=10, layer="AREA-1"),
            CadText(text="A", x=80, y=40, layer="AREA-1"),
            CadText(text="B", x=200, y=10, layer="ZONE-2"),
            CadText(text="B", x=250, y=60, layer="ZONE-2"),
            CadText(text="ignored", x=0, y=0, layer="DEFPOINTS"),
        ],
        inserts=[CadInsert(name="X", x=20, y=20, layer="AREA-1")],
    )
    regions = dict(detect_layer_regions(doc))
    assert "AREA-1" in regions
    assert regions["AREA-1"] == (10, 10, 80, 40)
    assert regions["ZONE-2"] == (200, 10, 250, 60)
    assert "DEFPOINTS" not in regions


def test_detect_regions_combines_and_dedupes_overlap():
    # 矩形 (0,0,100,100) 与 layer "AREA-1" 内的点 (20,20)~(80,80) 重叠 → 应去重保留矩形
    doc = CadDocument(
        texts=[
            CadText(text="x", x=20, y=20, layer="AREA-1"),
            CadText(text="x", x=80, y=80, layer="AREA-1"),
            CadText(text="y", x=200, y=200, layer="AREA-2"),
            CadText(text="y", x=300, y=250, layer="AREA-2"),
        ],
        polylines=[_rect_polyline(0, 0, 100, 100)],
        extents=(0, 0, 400, 400),
    )
    regions = detect_regions(doc)
    bboxes = [bbox for _, bbox in regions]
    assert (0, 0, 100, 100) in bboxes  # 矩形保留
    # AREA-2 与矩形不重叠 → 应被加入
    assert (200, 200, 300, 250) in bboxes
    # AREA-1 与矩形重叠 → 不应再加
    overlapping = [b for b in bboxes if b == (20, 20, 80, 80)]
    assert overlapping == []


def test_detect_regions_prefer_modes():
    doc = CadDocument(
        texts=[
            CadText(text="x", x=20, y=20, layer="AREA-1"),
            CadText(text="x", x=80, y=80, layer="AREA-1"),
        ],
        polylines=[_rect_polyline(0, 0, 100, 100)],
        extents=(0, 0, 200, 200),
    )
    rects = detect_regions(doc, prefer="rectangle")
    layers = detect_regions(doc, prefer="layer")
    assert [b for _, b in rects] == [(0, 0, 100, 100)]
    assert [b for _, b in layers] == [(20, 20, 80, 80)]
