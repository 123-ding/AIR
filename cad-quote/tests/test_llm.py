"""测试 LLM 参数补全。"""

import pytest

from app.catalog.catalog import Product, ProductCatalog
from app.llm import StubLLMBackend, complete_items, make_backend
from app.llm.backends import LLMSuggestion, OpenAILLMBackend
from app.ocr.extractor import EquipmentItem


def _items():
    return [
        EquipmentItem(model="LED-T8-18W", region="A", quantity=1, params={}),
        EquipmentItem(
            model="ABB-OT100",
            region="B",
            quantity=2,
            params={"voltage": "380V"},  # 已有部分参数
        ),
    ]


def test_stub_backend_extracts_power_and_voltage():
    backend = StubLLMBackend()
    out = backend.complete_params(
        model="LED-T8-18W 220V",
        known_params={},
    )
    assert "power" in out.params
    assert "18" in out.params["power"]
    assert out.params.get("voltage", "").startswith("220") or out.params["voltage"] == "220V"
    assert out.confidence > 0


def test_stub_backend_respects_schema():
    backend = StubLLMBackend()
    out = backend.complete_params(
        model="LED 18W 220V",
        schema=["power"],
    )
    assert "power" in out.params
    assert "voltage" not in out.params  # schema 限制


def test_stub_backend_skips_known_keys():
    backend = StubLLMBackend()
    out = backend.complete_params(
        model="LED 18W 220V",
        known_params={"power": "18W"},
    )
    # power 已知 → 不再返回
    assert "power" not in out.params


def test_stub_backend_explicit_mapping_takes_priority():
    backend = StubLLMBackend(mapping={"FOO-1": {"material": "stainless steel"}})
    out = backend.complete_params(model="FOO-1", known_params={})
    assert out.params["material"] == "stainless steel"


def test_complete_items_only_missing_skips_filled():
    backend = StubLLMBackend()
    items = _items()
    result = complete_items(items, backend, only_missing=True)
    # 第二项已有 voltage → only_missing 时不调用 → 返回原对象（可能是同一引用）
    assert result[1] is items[1]
    # 第一项有补全 → 新对象
    assert result[0] is not items[0]
    assert "power" in result[0].params
    assert "[LLM:" in result[0].note


def test_complete_items_uses_catalog_hint():
    catalog = ProductCatalog(
        [
            Product(
                model="ABC-1",
                base_price=100,
                params={"diameter": "DN50", "pressure": "1.6MPa"},
            )
        ]
    )

    captured_hints = []

    class _CapturingBackend(StubLLMBackend):
        def complete_params(self, model, known_params=None, hint_text="", schema=None):
            captured_hints.append(hint_text)
            return super().complete_params(model, known_params, hint_text, schema)

    items = [EquipmentItem(model="ABC-1", region="X", quantity=1, params={})]
    complete_items(items, _CapturingBackend(), catalog=catalog)
    assert "diameter=DN50" in captured_hints[0]


def test_complete_items_swallows_backend_errors():
    class _BoomBackend(StubLLMBackend):
        def complete_params(self, *a, **kw):
            raise RuntimeError("boom")

    items = [EquipmentItem(model="X", region="A", quantity=1, params={})]
    out = complete_items(items, _BoomBackend())
    assert out[0] is items[0]


def test_make_backend_factory():
    assert isinstance(make_backend("stub"), StubLLMBackend)
    assert isinstance(make_backend("openai"), OpenAILLMBackend)


def test_make_backend_unknown_raises():
    with pytest.raises(ValueError):
        make_backend("nope")


def test_openai_backend_uses_injected_client():
    """完整模拟 OpenAI client 的链式调用，避免依赖 openai 包。"""

    class _FakeMessage:
        content = '{"power": "1.5kW", "voltage": "380V"}'

    class _FakeChoice:
        message = _FakeMessage()

    class _FakeResp:
        choices = [_FakeChoice()]

    class _FakeChat:
        class completions:
            @staticmethod
            def create(**kwargs):
                return _FakeResp()

    class _FakeClient:
        chat = _FakeChat

    backend = OpenAILLMBackend(client=_FakeClient())
    out = backend.complete_params(model="X", known_params={"voltage": "380V"})
    assert out.params == {"power": "1.5kW"}  # voltage 已知，被剔除
    assert out.source == "openai"


def test_openai_backend_swallows_runtime_errors():
    class _ExplodingClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise RuntimeError("rate limit")

    backend = OpenAILLMBackend(client=_ExplodingClient())
    out = backend.complete_params(model="X")
    assert out.params == {}
    assert out.confidence == 0.0
    assert "openai-error" in out.source


def test_llm_suggestion_dataclass():
    s = LLMSuggestion(params={"a": "b"}, confidence=0.9, source="t")
    assert s.params == {"a": "b"}
    assert s.confidence == 0.9
