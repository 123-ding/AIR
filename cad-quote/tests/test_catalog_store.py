"""测试可写 CatalogStore + 价格历史。"""

import os

import pytest

from app.catalog.store import CatalogStore


@pytest.fixture
def store(tmp_path):
    return CatalogStore(data_dir=str(tmp_path))


def test_upsert_and_list(store):
    store.upsert_product(
        {
            "model": "ABC-100",
            "brand": "ACME",
            "unit": "台",
            "base_price": 1000.0,
            "aliases": ["ABC100"],
            "params": {"power": "1.5kW"},
        },
        user="alice",
    )
    products = store.list_products()
    assert len(products) == 1
    assert products[0]["model"] == "ABC-100"
    assert products[0]["aliases"] == ["ABC100"]
    # 别名归一化
    assert store.get_product("ABC100").base_price == 1000.0


def test_upsert_persists_to_yaml(store, tmp_path):
    store.upsert_product({"model": "X-1", "base_price": 9.9})
    yaml_path = os.path.join(str(tmp_path), "user_catalog.yaml")
    assert os.path.exists(yaml_path)
    # 重新加载一个 store 应该看到同样的型号
    store2 = CatalogStore(data_dir=str(tmp_path))
    assert store2.get_product("X-1").base_price == 9.9


def test_update_price_writes_history(store):
    store.upsert_product({"model": "M-1", "base_price": 100.0})
    store.update_price("M-1", 120.0, user="alice", note="季度调价")
    history = store.price_history("M-1")
    assert len(history) == 1
    assert history[0]["old_price"] == 100.0
    assert history[0]["new_price"] == 120.0
    assert history[0]["user"] == "alice"
    assert history[0]["note"] == "季度调价"


def test_upsert_changing_price_records_history(store):
    store.upsert_product({"model": "M-1", "base_price": 100.0})
    store.upsert_product({"model": "M-1", "base_price": 110.0}, user="bob")
    history = store.price_history("M-1")
    assert len(history) == 1
    assert history[0]["new_price"] == 110.0


def test_upsert_same_price_does_not_record(store):
    store.upsert_product({"model": "M-1", "base_price": 100.0})
    store.upsert_product({"model": "M-1", "base_price": 100.0})
    assert store.price_history("M-1") == []


def test_update_price_unknown_model_raises(store):
    with pytest.raises(KeyError):
        store.update_price("NOT-EXISTS", 1.0)


def test_delete_product(store):
    store.upsert_product({"model": "M-1", "base_price": 1.0})
    assert store.delete_product("M-1") is True
    assert store.get_product("M-1") is None
    # 再次删除返回 False
    assert store.delete_product("M-1") is False


def test_delete_via_alias(store):
    store.upsert_product(
        {"model": "ABC-100", "base_price": 1.0, "aliases": ["ABC100"]}
    )
    assert store.delete_product("ABC100") is True
    assert store.get_product("ABC-100") is None


def test_price_history_filters_by_model(store):
    store.upsert_product({"model": "A", "base_price": 1.0})
    store.upsert_product({"model": "B", "base_price": 1.0})
    store.update_price("A", 2.0)
    store.update_price("B", 3.0)
    assert len(store.price_history()) == 2
    assert len(store.price_history("A")) == 1
    assert store.price_history("A")[0]["new_price"] == 2.0


def test_empty_model_rejected(store):
    with pytest.raises(ValueError):
        store.upsert_product({"model": "", "base_price": 1.0})
