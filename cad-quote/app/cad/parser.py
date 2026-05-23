"""DXF 解析器。

读取 DXF 文件并提取实体（TEXT、MTEXT、INSERT 块引用）。
对所有功能保持 ``ezdxf`` 为可选依赖：未安装时给出明确的提示。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Tuple


BBox = Tuple[float, float, float, float]  # (xmin, ymin, xmax, ymax)


@dataclass
class CadText:
    """一段图上的文字（TEXT 或 MTEXT）。"""

    text: str
    x: float
    y: float
    layer: str = "0"
    height: float = 0.0

    def in_bbox(self, bbox: BBox) -> bool:
        xmin, ymin, xmax, ymax = bbox
        return xmin <= self.x <= xmax and ymin <= self.y <= ymax


@dataclass
class CadInsert:
    """一个图块引用 (INSERT)，``name`` 通常对应设备/符号的型号。"""

    name: str
    x: float
    y: float
    layer: str = "0"
    attribs: dict = field(default_factory=dict)

    def in_bbox(self, bbox: BBox) -> bool:
        xmin, ymin, xmax, ymax = bbox
        return xmin <= self.x <= xmax and ymin <= self.y <= ymax


@dataclass
class CadPolyline:
    """一段折线 / 多段线，顶点为 ``(x, y)`` 列表。"""

    vertices: List[Tuple[float, float]] = field(default_factory=list)
    layer: str = "0"
    closed: bool = False

    def bbox(self) -> Optional[BBox]:
        if not self.vertices:
            return None
        xs = [v[0] for v in self.vertices]
        ys = [v[1] for v in self.vertices]
        return (min(xs), min(ys), max(xs), max(ys))


@dataclass
class CadDocument:
    """已解析的 CAD 图纸内容。"""

    texts: List[CadText] = field(default_factory=list)
    inserts: List[CadInsert] = field(default_factory=list)
    polylines: List[CadPolyline] = field(default_factory=list)
    extents: Optional[BBox] = None

    # ---- 查询便捷方法 ----
    def texts_in(self, bbox: BBox) -> List[CadText]:
        return [t for t in self.texts if t.in_bbox(bbox)]

    def inserts_in(self, bbox: BBox) -> List[CadInsert]:
        return [i for i in self.inserts if i.in_bbox(bbox)]


def parse_dxf(path: str) -> CadDocument:
    """解析 DXF 文件并返回 :class:`CadDocument`。

    需要安装 ``ezdxf``；如果未安装则抛出明确的 :class:`ImportError`。
    """

    try:
        import ezdxf  # type: ignore
    except ImportError as exc:  # pragma: no cover - 依赖说明
        raise ImportError(
            "ezdxf 未安装。请运行 `pip install ezdxf` 后再解析 DXF 文件。"
        ) from exc

    doc = ezdxf.readfile(path)
    msp = doc.modelspace()

    texts: List[CadText] = []
    inserts: List[CadInsert] = []
    polylines: List[CadPolyline] = []

    for entity in msp:
        dxftype = entity.dxftype()
        if dxftype == "TEXT":
            texts.append(
                CadText(
                    text=str(entity.dxf.text),
                    x=float(entity.dxf.insert[0]),
                    y=float(entity.dxf.insert[1]),
                    layer=str(entity.dxf.layer),
                    height=float(getattr(entity.dxf, "height", 0.0) or 0.0),
                )
            )
        elif dxftype == "MTEXT":
            try:
                content = entity.plain_text()  # type: ignore[attr-defined]
            except Exception:
                content = str(entity.dxf.text)
            texts.append(
                CadText(
                    text=content,
                    x=float(entity.dxf.insert[0]),
                    y=float(entity.dxf.insert[1]),
                    layer=str(entity.dxf.layer),
                    height=float(getattr(entity.dxf, "char_height", 0.0) or 0.0),
                )
            )
        elif dxftype == "INSERT":
            attribs = {}
            try:
                for att in entity.attribs:  # type: ignore[attr-defined]
                    attribs[str(att.dxf.tag)] = str(att.dxf.text)
            except Exception:
                pass
            inserts.append(
                CadInsert(
                    name=str(entity.dxf.name),
                    x=float(entity.dxf.insert[0]),
                    y=float(entity.dxf.insert[1]),
                    layer=str(entity.dxf.layer),
                    attribs=attribs,
                )
            )
        elif dxftype in ("LWPOLYLINE", "POLYLINE"):
            verts: List[Tuple[float, float]] = []
            try:
                if dxftype == "LWPOLYLINE":
                    for pt in entity.get_points("xy"):  # type: ignore[attr-defined]
                        verts.append((float(pt[0]), float(pt[1])))
                else:
                    for v in entity.vertices:  # type: ignore[attr-defined]
                        loc = v.dxf.location
                        verts.append((float(loc[0]), float(loc[1])))
            except Exception:
                verts = []
            try:
                closed = bool(entity.closed)  # type: ignore[attr-defined]
            except Exception:
                closed = False
            if verts:
                polylines.append(
                    CadPolyline(
                        vertices=verts,
                        layer=str(entity.dxf.layer),
                        closed=closed,
                    )
                )

    extents: Optional[BBox] = None
    try:
        # ezdxf 提供 doc.header['$EXTMIN'/'$EXTMAX']，可能不可用
        emin = doc.header.get("$EXTMIN")
        emax = doc.header.get("$EXTMAX")
        if emin and emax:
            extents = (float(emin[0]), float(emin[1]), float(emax[0]), float(emax[1]))
    except Exception:
        extents = None

    return CadDocument(
        texts=texts, inserts=inserts, polylines=polylines, extents=extents
    )


def parse_cad(path: str, **dwg_kwargs) -> CadDocument:
    """解析 CAD 文件：``.dxf`` 直接走 :func:`parse_dxf`；``.dwg`` 先转换再解析。

    :param dwg_kwargs: 透传给 :func:`app.cad.dwg.convert_dwg_to_dxf`，例如
        ``runner=...`` / ``converter=...``，便于测试注入。
    :raises ValueError: 不识别的扩展名。
    """

    ext = os.path.splitext(path)[1].lower()
    if ext == ".dxf":
        return parse_dxf(path)
    if ext == ".dwg":
        from .dwg import convert_dwg_to_dxf

        dxf_path = convert_dwg_to_dxf(path, **dwg_kwargs)
        return parse_dxf(dxf_path)
    raise ValueError(f"不支持的 CAD 文件扩展名：{ext!r}（仅支持 .dxf / .dwg）")


def filter_by_bboxes(
    document: CadDocument, bboxes: Iterable[BBox]
) -> List[Tuple[BBox, List[CadText], List[CadInsert]]]:
    """对每个 bbox 返回内部文本和块引用，便于按区域批处理。"""

    return [
        (bbox, document.texts_in(bbox), document.inserts_in(bbox))
        for bbox in bboxes
    ]
