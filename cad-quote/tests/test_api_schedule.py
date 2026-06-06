import io
import json

import pytest

pytest.importorskip("fastapi")
ezdxf = pytest.importorskip("ezdxf")
from fastapi.testclient import TestClient  # noqa: E402

from app.api.main import app  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app)


def _schedule_dxf_bytes() -> bytes:
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_text("屋顶景观照明配电箱", dxfattribs={"height": 5, "insert": (10, 120)})
    msp.add_text("ALY", dxfattribs={"height": 3.5, "insert": (10, 112)})
    msp.add_text("Pe=20.0kW", dxfattribs={"height": 2.5, "insert": (10, 104)})
    msp.add_text("Kx=1", dxfattribs={"height": 2.5, "insert": (38, 104)})
    msp.add_text("Cosφ=0.85", dxfattribs={"height": 2.5, "insert": (56, 104)})
    msp.add_text("Ijs=35.76A", dxfattribs={"height": 2.5, "insert": (86, 104)})
    msp.add_text("CDB6i", dxfattribs={"height": 2.5, "insert": (10, 96)})
    msp.add_text("3P", dxfattribs={"height": 2.5, "insert": (26, 96)})
    msp.add_text("C型", dxfattribs={"height": 2.5, "insert": (34, 96)})
    msp.add_text("40A", dxfattribs={"height": 2.5, "insert": (42, 96)})
    msp.add_text("JZ7-44 380V", dxfattribs={"height": 2.5, "insert": (64, 96)})
    msp.add_text("600X600X150", dxfattribs={"height": 2.5, "insert": (74, 88)})
    msp.add_text("电井挂墙明装", dxfattribs={"height": 2.5, "insert": (110, 88)})
    msp.add_text("CDB6PLEi", dxfattribs={"height": 2.5, "insert": (10, 70)})
    msp.add_text("2P", dxfattribs={"height": 2.5, "insert": (29, 70)})
    msp.add_text("C型", dxfattribs={"height": 2.5, "insert": (36, 70)})
    msp.add_text("20A/0.03", dxfattribs={"height": 2.5, "insert": (44, 70)})
    msp.add_text("L1", dxfattribs={"height": 2.5, "insert": (66, 70)})
    msp.add_text("N1", dxfattribs={"height": 2.5, "insert": (76, 70)})
    msp.add_text("WDZ-BYJ-(3X4)", dxfattribs={"height": 2.5, "insert": (92, 70)})
    msp.add_text("SC20", dxfattribs={"height": 2.5, "insert": (118, 70)})
    msp.add_text("3KW", dxfattribs={"height": 2.5, "insert": (132, 70)})
    msp.add_text("预留投光灯回路", dxfattribs={"height": 2.5, "insert": (144, 70)})
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


def test_schedule_endpoint_returns_json(client):
    response = client.post(
        "/schedule",
        files={"file": ("panel.dxf", _schedule_dxf_bytes(), "application/dxf")},
        data={"request_json": json.dumps({"bbox": [0, 0, 200, 130]})},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["header"]["code"] == "ALY"
    assert payload["circuits"][0]["circuit"] == "N1"
    assert payload["circuits"][0]["load"] == "3KW"


def test_schedule_excel_endpoint_returns_file(client):
    response = client.post(
        "/schedule/excel",
        files={"file": ("panel.dxf", _schedule_dxf_bytes(), "application/dxf")},
        data={"request_json": "{}"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response.content[:2] == b"PK"
