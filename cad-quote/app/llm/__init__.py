"""LLM 辅助参数补全（P2）。

* 抽象 :class:`LLMBackend`；
* :class:`StubLLMBackend`：基于关键词/正则的本地启发式，不联网；
* :class:`OpenAILLMBackend`：懒加载 ``openai`` SDK，按需联网（默认不启用）。
"""

from .backends import (
    LLMBackend,
    OpenAILLMBackend,
    StubLLMBackend,
    make_backend,
)
from .completer import complete_items

__all__ = [
    "LLMBackend",
    "OpenAILLMBackend",
    "StubLLMBackend",
    "make_backend",
    "complete_items",
]
