"""P2 API 集成测试：客户档案 + PDF + DWG 拒绝/接受。"""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("ezdxf")
from fastapi.testclient import TestClient  # noqa: E402

from app.api.main import app  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app)


def test_list_customers(client):
    r = client.get("/customers")
    assert r.status_code == 200
    levels = [c["level"] for c in r.json()["customers"]]
    assert "default" in levels
    assert "gold" in levels


def test_quote_rejects_unknown_extension(client):
    r = client.post(
        "/quote",
        files={"file": ("a.txt", b"hello", "text/plain")},
        data={"request_json": '{"regions":[{"name":"r","bbox":[0,0,1,1]}]}'},
    )
    assert r.status_code == 400


def test_quote_rejects_empty_regions(client):
    r = client.post(
        "/quote",
        files={"file": ("a.dxf", b"x", "application/dxf")},
        data={"request_json": '{"regions":[]}'},
    )
    assert r.status_code == 400


def test_quote_rejects_unknown_customer(tmp_path, client):
    """构造一个最小可解析的 DXF，再用未知客户等级请求 → 400。"""
    import ezdxf

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_text("LED-T8-18W", dxfattribs={"insert": (5, 5)})
    dxf_path = tmp_path / "min.dxf"
    doc.saveas(str(dxf_path))

    body = {
        "regions": [{"name": "r", "bbox": [0, 0, 10, 10]}],
        "customer_level": "no-such-level",
    }
    with open(dxf_path, "rb") as f:
        r = client.post(
            "/quote",
            files={"file": ("min.dxf", f.read(), "application/dxf")},
            data={"request_json": __import__("json").dumps(body)},
        )
    assert r.status_code == 400
    assert "客户" in r.json()["detail"]


def test_quote_with_gold_customer_returns_currency(tmp_path, client):
    import ezdxf
    import json as _json

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_text("LED-T8-18W", dxfattribs={"insert": (5, 5)})
    dxf_path = tmp_path / "min.dxf"
    doc.saveas(str(dxf_path))

    body = {
        "regions": [{"name": "r", "bbox": [0, 0, 10, 10]}],
        "customer_level": "gold",
    }
    with open(dxf_path, "rb") as f:
        r = client.post(
            "/quote",
            files={"file": ("min.dxf", f.read(), "application/dxf")},
            data={"request_json": _json.dumps(body)},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["customer_level"] == "gold"
    assert data["currency"] == "CNY"


def test_quote_pdf_endpoint(tmp_path, client):
    pytest.importorskip("reportlab")
    import ezdxf
    import json as _json

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_text("LED-T8-18W", dxfattribs={"insert": (5, 5)})
    dxf_path = tmp_path / "min.dxf"
    doc.saveas(str(dxf_path))

    body = {"regions": [{"name": "r", "bbox": [0, 0, 10, 10]}]}
    with open(dxf_path, "rb") as f:
        r = client.post(
            "/quote/pdf",
            files={"file": ("min.dxf", f.read(), "application/dxf")},
            data={"request_json": _json.dumps(body), "customer_name": "Acme"},
        )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content[:4] == b"%PDF"


def test_quote_with_llm_backend(tmp_path, client):
    import ezdxf
    import json as _json

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    # 文本里嵌入功率/电压，stub LLM 应当能补出参数
    msp.add_text("LED-T8-18W 220V", dxfattribs={"insert": (5, 5)})
    dxf_path = tmp_path / "min.dxf"
    doc.saveas(str(dxf_path))

    body = {
        "regions": [{"name": "r", "bbox": [0, 0, 10, 10]}],
        "llm_backend": "stub",
    }
    with open(dxf_path, "rb") as f:
        r = client.post(
            "/quote",
            files={"file": ("min.dxf", f.read(), "application/dxf")},
            data={"request_json": _json.dumps(body)},
        )
    assert r.status_code == 200, r.text
