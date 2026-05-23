"""把 DXF 的指定矩形区域渲染为 PNG。

使用 ``ezdxf.addons.drawing`` 的 matplotlib 后端进行渲染。``ezdxf`` 与
``matplotlib`` 均为可选依赖；未安装时会抛出明确的 :class:`ImportError`。
"""

from __future__ import annotations

import os
from typing import Iterable, List, Tuple

BBox = Tuple[float, float, float, float]


def render_regions(
    dxf_path: str,
    bboxes: Iterable[BBox],
    out_dir: str,
    dpi: int = 150,
) -> List[str]:
    """渲染每个 bbox 区域为单独的 PNG，返回生成的图片路径列表。"""

    try:
        import ezdxf  # type: ignore
        from ezdxf.addons.drawing import RenderContext, Frontend  # type: ignore
        from ezdxf.addons.drawing.matplotlib import MatplotlibBackend  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "ezdxf 未安装；请运行 `pip install ezdxf matplotlib` 后再渲染。"
        ) from exc
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "matplotlib 未安装；请运行 `pip install matplotlib` 后再渲染。"
        ) from exc

    os.makedirs(out_dir, exist_ok=True)
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    ctx = RenderContext(doc)

    paths: List[str] = []
    for idx, (xmin, ymin, xmax, ymax) in enumerate(bboxes):
        fig, ax = plt.subplots(figsize=(8, 8))
        backend = MatplotlibBackend(ax)
        Frontend(ctx, backend).draw_layout(msp, finalize=True)
        ax.set_xlim(xmin, xmax)
        ax.set_ylim(ymin, ymax)
        ax.set_aspect("equal")
        ax.axis("off")
        out_path = os.path.join(out_dir, f"region_{idx:03d}.png")
        fig.savefig(out_path, dpi=dpi, bbox_inches="tight", pad_inches=0.05)
        plt.close(fig)
        paths.append(out_path)
    return paths
