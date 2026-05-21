"""集成测试：FastAPI 管理后台 + 自动区域识别接口。"""

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from app.api import admin as admin_module  # noqa: E402
from app.api.main import app  # noqa: E402
from app.catalog.store import CatalogStore  # noqa: E402


@pytest.fixture
def client(tmp_path):
    # 注入临时目录的 CatalogStore，避免污染真实数据目录
    store = CatalogStore(data_dir=str(tmp_path))
    admin_module.set_store(store)
    yield TestClient(app)
    admin_module.set_store(CatalogStore(data_dir=str(tmp_path)))  # reset


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_admin_crud_full_cycle(client):
    # 开始为空
    assert client.get("/admin/catalog/products").json()["count"] == 0

    # 创建
    r = client.post(
        "/admin/catalog/products",
        json={
            "model": "M-1",
            "brand": "Acme",
            "unit": "台",
            "base_price": 100.0,
            "aliases": ["M1"],
            "params": {"k": "v"},
        },
    )
    assert r.status_code == 200
    assert client.get("/admin/catalog/products").json()["count"] == 1

    # 读单个
    r = client.get("/admin/catalog/products/M-1")
    assert r.status_code == 200
    assert r.json()["base_price"] == 100.0

    # 调价
    r = client.post(
        "/admin/catalog/products/M-1/price",
        json={"price": 150.0, "user": "alice", "note": "Q2 调整"},
    )
    assert r.status_code == 200
    assert r.json()["base_price"] == 150.0

    # 价格历史
    r = client.get("/admin/catalog/products/M-1/price-history")
    history = r.json()["history"]
    assert len(history) == 1
    assert history[0]["new_price"] == 150.0
    assert history[0]["user"] == "alice"

    # 全局历史
    assert len(client.get("/admin/catalog/price-history").json()["history"]) == 1

    # 删除
    r = client.delete("/admin/catalog/products/M-1")
    assert r.status_code == 200
    assert client.get("/admin/catalog/products/M-1").status_code == 404


def test_admin_invalid_model_returns_400(client):
    r = client.post(
        "/admin/catalog/products",
        json={"model": "", "base_price": 1.0},
    )
    assert r.status_code == 400


def test_admin_404_on_unknown_model(client):
    assert client.get("/admin/catalog/products/UNKNOWN").status_code == 404
    assert (
        client.post(
            "/admin/catalog/products/UNKNOWN/price", json={"price": 1.0}
        ).status_code
        == 404
    )
    assert client.delete("/admin/catalog/products/UNKNOWN").status_code == 404


def test_strategies_and_catalog_endpoints(client):
    assert "standard" in client.get("/strategies").json()["strategies"]
    # 当用户库为空时退化到内置默认库
    assert client.get("/catalog").json()["count"] >= 1
