"""可插拔 LLM 后端，用于参数补全。

每个后端只需实现 :meth:`LLMBackend.complete_params`，输入：

* ``model``: 当前型号字符串
* ``known_params``: 已知规格 ``{key: value}``
* ``hint_text``: 可选的图纸文本上下文
* ``schema``: 期望补全的字段（None 时由后端自行决定）

输出：``{key: value}`` 形式的补全字典（**仅包含新增或更精确的字段**，不应覆盖已有值）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class LLMSuggestion:
    params: Dict[str, str]
    confidence: float = 1.0
    source: str = ""


class LLMBackend:
    name: str = "base"

    def complete_params(
        self,
        model: str,
        known_params: Optional[Dict[str, str]] = None,
        hint_text: str = "",
        schema: Optional[List[str]] = None,
    ) -> LLMSuggestion:  # pragma: no cover - 抽象
        raise NotImplementedError


# ---------- 启发式 Stub ----------
_PATTERNS = (
    # (字段名, 多个候选正则；命中第一个即为 value)
    (
        "power",
        [
            re.compile(r"(\d+(?:\.\d+)?)\s*(kW|KW|千瓦)", re.IGNORECASE),
            re.compile(r"(\d+(?:\.\d+)?)\s*W\b", re.IGNORECASE),
        ],
    ),
    (
        "voltage",
        [
            re.compile(r"\b(\d{2,4})\s*V\b", re.IGNORECASE),
            re.compile(r"\b(110|220|380|440|480)\b"),
        ],
    ),
    (
        "current",
        [re.compile(r"(\d+(?:\.\d+)?)\s*A\b")],
    ),
    (
        "ip",
        [re.compile(r"\b(IP\d{2})\b", re.IGNORECASE)],
    ),
    (
        "diameter",
        [re.compile(r"\b(DN\d+)\b", re.IGNORECASE)],
    ),
    (
        "pressure",
        [re.compile(r"(\d+(?:\.\d+)?)\s*MPa", re.IGNORECASE)],
    ),
    (
        "length",
        [re.compile(r"(\d{3,4})\s*mm", re.IGNORECASE)],
    ),
    (
        "color_temp",
        [re.compile(r"(\d{4})\s*K\b")],
    ),
)


class StubLLMBackend(LLMBackend):
    """启发式后端：从型号字符串 + 提示文本里提取常见规格字段。

    专为离线 / 测试设计，确定性、零依赖。
    """

    name = "stub"

    def __init__(self, mapping: Optional[Dict[str, Dict[str, str]]] = None) -> None:
        # 允许使用方按型号注入"标准答案"，覆盖启发式
        self._mapping = {k.upper(): dict(v) for k, v in (mapping or {}).items()}

    def complete_params(
        self,
        model: str,
        known_params: Optional[Dict[str, str]] = None,
        hint_text: str = "",
        schema: Optional[List[str]] = None,
    ) -> LLMSuggestion:
        known = {k.lower(): v for k, v in (known_params or {}).items()}
        text = " ".join(filter(None, [model or "", hint_text or ""]))

        out: Dict[str, str] = {}
        # 1) mapping 优先
        for key, val in self._mapping.get((model or "").upper(), {}).items():
            if key.lower() not in known:
                out[key] = str(val)

        # 2) 正则扫描
        for key, patterns in _PATTERNS:
            if schema is not None and key not in schema:
                continue
            if key in known or key in out:
                continue
            for pat in patterns:
                m = pat.search(text)
                if m:
                    val = m.group(0).strip()
                    # 把 "1.5kW" 统一成 "1.5kW"（保留原写法即可）
                    out[key] = val
                    break
        return LLMSuggestion(params=out, confidence=0.6 if out else 0.0, source="stub")


# ---------- OpenAI 兼容后端（懒加载） ----------
class OpenAILLMBackend(LLMBackend):
    """通过 OpenAI 兼容 API 做参数补全。

    懒加载 ``openai``；离线/未安装时调用会抛 :class:`ImportError`。
    """

    name = "openai"

    DEFAULT_PROMPT = (
        "你是一名机电/给排水/电气工程师。我会给你一个 CAD 图上识别出的设备型号、"
        "已知规格和图纸上下文。请基于行业常识，输出 JSON 形式的规格补全（只填确定字段，"
        "未知留空）。字段使用英文 key（power/voltage/current/ip/diameter/pressure/length/"
        "color_temp/material 等）。"
    )

    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        prompt: Optional[str] = None,
        client: Any = None,
    ) -> None:
        self.model_name = model_name
        self.api_key = api_key
        self.base_url = base_url
        self.prompt = prompt or self.DEFAULT_PROMPT
        self._client = client  # 允许测试注入

    def _ensure_client(self):  # pragma: no cover - 仅在用户安装 openai 时执行
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "openai 未安装；请 `pip install openai` 后再启用 LLM 补全。"
            ) from exc
        kwargs: Dict[str, Any] = {}
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.base_url:
            kwargs["base_url"] = self.base_url
        self._client = OpenAI(**kwargs)
        return self._client

    def complete_params(
        self,
        model: str,
        known_params: Optional[Dict[str, str]] = None,
        hint_text: str = "",
        schema: Optional[List[str]] = None,
    ) -> LLMSuggestion:
        import json

        client = self._ensure_client()
        user_prompt = (
            f"型号：{model}\n"
            f"已知规格：{json.dumps(known_params or {}, ensure_ascii=False)}\n"
            f"图纸上下文：{hint_text or '(无)'}\n"
            f"期望补全字段：{json.dumps(schema, ensure_ascii=False) if schema else '(自动决定)'}\n"
            "请只回复一个 JSON 对象。"
        )
        try:  # pragma: no cover - 真实网络调用
            resp = client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self.prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            content = resp.choices[0].message.content or "{}"
            data = json.loads(content)
        except Exception as exc:  # noqa: BLE001
            return LLMSuggestion(params={}, confidence=0.0, source=f"openai-error:{exc}")

        known = {k.lower() for k in (known_params or {})}
        out = {
            str(k): str(v)
            for k, v in dict(data).items()
            if v not in (None, "") and str(k).lower() not in known
        }
        return LLMSuggestion(params=out, confidence=0.8 if out else 0.0, source="openai")


def make_backend(name: str, **kwargs) -> LLMBackend:
    n = (name or "").lower()
    if n in {"stub", "test", "mock", "rule", "heuristic"}:
        return StubLLMBackend(**kwargs)
    if n in {"openai", "gpt"}:
        return OpenAILLMBackend(**kwargs)
    raise ValueError(f"未知的 LLM 后端：{name!r}")


def iter_backends() -> Iterable[str]:
    return ("stub", "openai")
