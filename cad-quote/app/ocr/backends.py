"""可插拔 OCR 后端。

P1 目标：当 DXF 区域内**没有可读文本实体**（例如模型号被画成爆炸字、图块、栅格图）
时，能够调用一个 OCR 后端识别已渲染的区域 PNG，从识别文本中提取型号。

接口故意做得很薄：

* :class:`OCRBackend` 是抽象基类，``recognize(image_path)`` 返回一组识别行（``OCRLine``）。
* :class:`StubOCRBackend` 用于测试 / 演示，按文件名或预设映射返回固定文本。
* :class:`PaddleOCRBackend` 在运行时**懒加载** ``paddleocr``，仅在用户实际启用时才需要安装。

这样保证默认依赖不增加，离线/CI 环境仍可运行所有测试。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence


@dataclass
class OCRLine:
    """一行 OCR 识别结果。"""

    text: str
    confidence: float = 1.0


class OCRBackend:
    """OCR 后端抽象基类。"""

    name: str = "base"

    def recognize(self, image_path: str) -> List[OCRLine]:  # pragma: no cover - 抽象
        raise NotImplementedError


class StubOCRBackend(OCRBackend):
    """测试用桩。

    用法 1：构造时传入 ``mapping = {image_path_or_basename: [text, ...]}``，
    匹配（精确或 basename）后返回对应文本。

    用法 2：构造时传入 ``default_lines``，对所有图片返回相同内容。
    """

    name = "stub"

    def __init__(
        self,
        mapping: Optional[Dict[str, Sequence[str]]] = None,
        default_lines: Optional[Sequence[str]] = None,
    ) -> None:
        self._mapping = {k: list(v) for k, v in (mapping or {}).items()}
        self._default = list(default_lines or [])

    def recognize(self, image_path: str) -> List[OCRLine]:
        if image_path in self._mapping:
            lines = self._mapping[image_path]
        else:
            base = os.path.basename(image_path)
            lines = self._mapping.get(base, self._default)
        return [OCRLine(text=t, confidence=1.0) for t in lines]


class PaddleOCRBackend(OCRBackend):
    """基于 ``paddleocr`` 的真实 OCR 后端。

    懒加载：只有第一次调用 :meth:`recognize` 时才 ``import paddleocr``。
    若未安装会抛出 :class:`ImportError`，提示用户 ``pip install paddleocr``。
    """

    name = "paddleocr"

    def __init__(
        self,
        lang: str = "ch",
        use_angle_cls: bool = True,
        min_confidence: float = 0.5,
        **kwargs,
    ) -> None:
        self.lang = lang
        self.use_angle_cls = use_angle_cls
        self.min_confidence = min_confidence
        self._extra = kwargs
        self._impl = None

    def _ensure(self):
        if self._impl is not None:
            return
        try:  # pragma: no cover - 仅在用户安装 paddleocr 时执行
            from paddleocr import PaddleOCR  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "paddleocr 未安装；请 `pip install paddleocr` 后再启用 OCR 兜底。"
            ) from exc
        self._impl = PaddleOCR(  # pragma: no cover
            use_angle_cls=self.use_angle_cls, lang=self.lang, **self._extra
        )

    def recognize(self, image_path: str) -> List[OCRLine]:  # pragma: no cover - 需 paddleocr
        self._ensure()
        result = self._impl.ocr(image_path, cls=self.use_angle_cls)  # type: ignore[union-attr]
        lines: List[OCRLine] = []
        # PaddleOCR 不同版本返回结构略有差异，统一兼容
        if not result:
            return lines
        first = result[0] if isinstance(result, list) else result
        items = first if isinstance(first, list) else result
        for item in items or []:
            try:
                _box, (text, conf) = item[0], item[1]
            except Exception:
                continue
            try:
                conf_f = float(conf)
            except (TypeError, ValueError):
                conf_f = 0.0
            if conf_f < self.min_confidence:
                continue
            lines.append(OCRLine(text=str(text), confidence=conf_f))
        return lines


def make_backend(name: str, **kwargs) -> OCRBackend:
    """工厂：按名字构造 OCR 后端。

    :param name: ``"stub"`` 或 ``"paddleocr"``。
    """

    n = (name or "").lower()
    if n in {"stub", "test", "mock"}:
        return StubOCRBackend(**kwargs)
    if n in {"paddle", "paddleocr"}:
        return PaddleOCRBackend(**kwargs)
    raise ValueError(f"未知的 OCR 后端：{name!r}")
