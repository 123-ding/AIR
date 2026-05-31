"""SVG 预览接口集成测试。"""

import io

import pytest

pytest.importorskip("fastapi")
ezdxf = pytest.importorskip("ezdxf")
from fastapi.testclient import TestClient  # noqa: E402

from app.api.main import app  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app)


def _sample_dxf_bytes() -> bytes:
    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (100, 0), (100, 50), (0, 50)], close=True)
    msp.add_text("AL1", dxfattribs={"height": 5, "insert": (10, 10)})
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


def test_preview_returns_svg(client):
    data = _sample_dxf_bytes()
    r = client.post(
        "/preview",
        files={"file": ("drawing.dxf", data, "application/dxf")},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert r.text.lstrip().startswith("<?xml")
    assert "<svg" in r.text
    # 由实体推断的 extents 应为合法范围
    extents = r.headers.get("x-cad-extents")
    assert extents is not None
    xmin, ymin, xmax, ymax = (float(v) for v in extents.split(","))
    assert xmin < xmax and ymin < ymax


def test_preview_rejects_unknown_extension(client):
    r = client.post(
        "/preview",
        files={"file": ("a.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400
