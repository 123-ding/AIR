"""把若干 PNG 子图按网格拼接为一张总图。"""

from __future__ import annotations

import math
import os
from typing import Iterable, List, Optional, Sequence


def composite_grid(
    image_paths: Sequence[str],
    out_path: str,
    columns: Optional[int] = None,
    padding: int = 10,
    background: str = "white",
    labels: Optional[Sequence[str]] = None,
) -> str:
    """按网格把多张图片拼接为一张 PNG。

    :param image_paths: 子图路径列表（按显示顺序）。
    :param out_path: 输出 PNG 路径。
    :param columns: 列数；默认按 ``ceil(sqrt(n))`` 自动估算。
    :param padding: 子图之间的空白像素。
    :param background: 背景色。
    :param labels: 与 ``image_paths`` 一一对应的标签，会写在子图下方。
    """

    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ImportError("Pillow 未安装，请 `pip install Pillow`。") from exc

    if not image_paths:
        raise ValueError("image_paths 不能为空。")
    if labels is not None and len(labels) != len(image_paths):
        raise ValueError("labels 长度必须与 image_paths 相同。")

    n = len(image_paths)
    cols = columns or max(1, math.ceil(math.sqrt(n)))
    rows = math.ceil(n / cols)

    images = [Image.open(p).convert("RGB") for p in image_paths]
    cell_w = max(im.width for im in images)
    cell_h = max(im.height for im in images)
    label_h = 24 if labels else 0

    canvas_w = cols * cell_w + (cols + 1) * padding
    canvas_h = rows * (cell_h + label_h) + (rows + 1) * padding
    canvas = Image.new("RGB", (canvas_w, canvas_h), background)
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.load_default()
    except Exception:  # pragma: no cover
        font = None

    for idx, im in enumerate(images):
        r, c = divmod(idx, cols)
        x = padding + c * (cell_w + padding) + (cell_w - im.width) // 2
        y = padding + r * (cell_h + label_h + padding)
        canvas.paste(im, (x, y))
        if labels and font is not None:
            label = labels[idx]
            text_y = y + cell_h + 4
            draw.text((x, text_y), label, fill="black", font=font)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    canvas.save(out_path, format="PNG")
    return out_path
