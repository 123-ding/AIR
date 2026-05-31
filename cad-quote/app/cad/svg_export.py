"""DXF/DWG → SVG 矢量预览。

设计要点：**数据提取与渲染预览完全分离**。

* 报价所需的设备数据（Block 名称、属性、文字）由 :mod:`app.cad.parser` 直接从矢量
  实体读取，**不需要**任何图片渲染。
* 图纸预览使用 **SVG 矢量导出**：清晰（可无限缩放、保留线宽/图层色）且快（无需栅格化），
  解决原 matplotlib PNG 方案「不清晰 + 慢」的问题。
* DWG 经 :func:`app.cad.dwg.resolve_to_dxf` **只转换一次**，之后全程走 ezdxf。

``ezdxf`` 为可选依赖；未安装时抛出明确的 :class:`ImportError`。
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

BBox = Tuple[float, float, float, float]  # (xmin, ymin, xmax, ymax)


def render_svg(
    path: str,
    out_path: Optional[str] = None,
    *,
    bbox: Optional[BBox] = None,
    **dwg_kwargs,
) -> str:
    """把 DXF/DWG 渲染为 SVG 字符串（矢量、无需栅格化）。

    :param path: ``.dxf`` 或 ``.dwg`` 文件路径；``.dwg`` 会先（缓存地）转成 DXF。
    :param out_path: 可选，若提供则把 SVG 写入该文件。
    :param bbox: 可选裁剪窗口 ``(xmin, ymin, xmax, ymax)``；仅渲染该范围。缺省渲染整张图。
    :param dwg_kwargs: 透传给 :func:`app.cad.dwg.resolve_to_dxf`（如 ``converter`` / ``runner``）。
    :return: SVG 文本内容。
    :raises ImportError: 未安装 ``ezdxf``。
    """

    try:
        import ezdxf  # type: ignore
        from ezdxf.addons.drawing import RenderContext, Frontend, layout  # type: ignore
        from ezdxf.addons.drawing.svg import SVGBackend  # type: ignore
    except ImportError as exc:  # pragma: no cover - 依赖说明
        raise ImportError(
            "ezdxf 未安装；请运行 `pip install ezdxf` 后再导出 SVG 预览。"
        ) from exc

    from .dwg import resolve_to_dxf

    dxf_path = resolve_to_dxf(path, **dwg_kwargs)
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    ctx = RenderContext(doc)
    backend = SVGBackend()
    frontend = Frontend(ctx, backend)
    frontend.draw_layout(msp)

    page = layout.Page(0, 0, layout.Units.mm, margins=layout.Margins.all(0))
    if bbox is not None and bbox[0] < bbox[2] and bbox[1] < bbox[3]:
        xmin, ymin, xmax, ymax = bbox
        # render_box 以 DXF 坐标限定输出范围（裁剪到该窗口）。
        render_box = layout.BoundingBox2d([(xmin, ymin), (xmax, ymax)])
        svg = backend.get_string(page, render_box=render_box)
    else:
        # bbox 缺失或非法（如未初始化的 EXTMIN/EXTMAX 哨兵值）时渲染整张图。
        svg = backend.get_string(page)

    if out_path:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(svg)
    return svg
