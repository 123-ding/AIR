import json

import pytest

from app.cad.parser import CadDocument, CadText, parse_cad
from app.cli import main
from app.schedule import (
    cluster_rows_by_y,
    extract_panel_schedule,
    extract_panel_schedule_from_texts,
    order_row_by_x,
    parse_circuit_fields,
)
from app.schedule.exporter import schedule_to_dataframe, to_csv, to_excel, to_json


def _text(text: str, x: float, y: float, height: float = 2.5) -> CadText:
    return CadText(text=text, x=x, y=y, height=height)


def _sample_panel_texts():
    texts = [
        _text("屋顶景观照明配电箱", 10, 120, 5.0),
        _text("ALY", 10, 112, 3.5),
        _text("Pe=20.0kW", 10, 104, 2.5),
        _text("Kx=1", 38, 104, 2.5),
        _text("Cosφ=0.85", 56, 104, 2.5),
        _text("Ijs=35.76A", 86, 104, 2.5),
        _text("CDB6i", 10, 96, 2.5),
        _text("3P", 26, 96, 2.5),
        _text("C型", 34, 96, 2.5),
        _text("40A", 42, 96, 2.5),
        _text("JZ7-44 380V", 64, 96, 2.5),
        _text("II级试验组合型SPD / Up≤1.5KV In≥5KA", 10, 88, 2.5),
        _text("600X600X150", 74, 88, 2.5),
        _text("电井挂墙明装", 110, 88, 2.5),
    ]

    phases = ["L1", "L2", "L3", "L1", "L2", "L3"]
    for idx, phase in enumerate(phases, start=1):
        y = 78 - idx * 8
        texts.extend(
            [
                _text("CDB6PLEi", 10, y),
                _text("2P", 29, y),
                _text("C型", 36, y),
                _text("20A/0.03", 44, y),
                _text(phase, 66, y),
                _text(f"N{idx}", 76, y),
                _text("WDZ-BYJ-", 92, y),
                _text("(3X4)", 103, y),
                _text("SC20", 118, y),
                _text("3KW", 132, y),
                _text("预留投光灯", 144, y),
                _text("回路", 156, y),
            ]
        )
    texts.append(_text("备注说明", 10, 6, 2.5))
    return texts


def test_extract_panel_schedule_from_synthetic_texts():
    schedule = extract_panel_schedule_from_texts(_sample_panel_texts())

    assert len(schedule.circuits) == 6
    assert [row.circuit for row in schedule.circuits] == ["N1", "N2", "N3", "N4", "N5", "N6"]
    assert [row.phase for row in schedule.circuits] == ["L1", "L2", "L3", "L1", "L2", "L3"]
    assert all(row.breaker == "CDB6PLEi" for row in schedule.circuits)
    assert all(row.cable == "WDZ-BYJ-(3X4)" for row in schedule.circuits)
    assert all(row.conduit == "SC20" for row in schedule.circuits)
    assert all(row.load == "3KW" for row in schedule.circuits)
    assert all(row.usage == "预留投光灯回路" for row in schedule.circuits)

    header = schedule.header
    assert header.name == "屋顶景观照明配电箱"
    assert header.code == "ALY"
    assert header.pe == "20.0kW"
    assert header.kx == "1"
    assert header.cos_phi == "0.85"
    assert header.ijs == "35.76A"
    assert header.main_breaker == "CDB6i 3P C型 40A"
    assert header.contactor == "JZ7-44 380V"
    assert header.size == "600X600X150"
    assert header.install == "电井挂墙明装"


def test_row_clustering_and_horizontal_merge_boundaries():
    texts = [
        _text("CDB6PLEi", 10, 20.0),
        _text("2P", 28, 19.3),
        _text("C型", 34, 20.1),
        _text("20A/0.03", 42, 19.8),
        _text("WDZ-BYJ-", 60, 20.0),
        _text("(3X4)", 71, 20.0),
        _text("SC20", 88, 20.0),
        _text("另一行", 10, 10.0),
    ]

    rows = cluster_rows_by_y(texts)
    assert len(rows) == 2
    ordered = order_row_by_x(rows[0])
    assert [item.text for item in ordered[:5]] == [
        "CDB6PLEi",
        "2P",
        "C型",
        "20A/0.03",
        "WDZ-BYJ-(3X4)",
    ]
    assert ordered[5].text == "SC20"


def test_parse_circuit_fields_filters_noise_rows():
    noise_row = order_row_by_x(
        [_text("回路编号", 10, 10), _text("相序", 40, 10), _text("用途", 70, 10)]
    )
    assert parse_circuit_fields(noise_row) is None


def test_schedule_exporters_and_cli(tmp_path, monkeypatch, capsys):
    schedule = extract_panel_schedule_from_texts(_sample_panel_texts())
    out_json = tmp_path / "schedule.json"
    out_csv = tmp_path / "schedule.csv"
    out_excel = tmp_path / "schedule.xlsx"

    to_json(schedule, str(out_json))
    to_csv(schedule, str(out_csv))
    to_excel(schedule, str(out_excel))

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["header"]["code"] == "ALY"
    assert "箱头字段" in out_csv.read_text(encoding="utf-8-sig")
    assert out_excel.exists()

    df = schedule_to_dataframe(schedule)
    assert list(df.columns) == ["回路", "断路器", "极数", "曲线", "整定", "相序", "电缆", "敷设", "负荷", "用途"]
    assert df.iloc[0]["回路"] == "N1"

    monkeypatch.setattr("app.cli.parse_cad", lambda path: CadDocument(texts=_sample_panel_texts()))
    rc = main(
        [
            "schedule",
            "--dxf",
            "sample.dxf",
            "--json",
            str(tmp_path / "cli.json"),
            "--csv",
            str(tmp_path / "cli.csv"),
        ]
    )
    assert rc == 0
    output = capsys.readouterr().out
    assert "ALY" in output
    assert "N1" in output


def test_extract_panel_schedule_from_real_dxf(tmp_path):
    ezdxf = pytest.importorskip("ezdxf")

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
    msp.add_text("电井挂墙明装", dxfattribs={"height": 2.5, "insert": (110, 88)})
    msp.add_text("600X600X150", dxfattribs={"height": 2.5, "insert": (74, 88)})
    msp.add_text("JZ7-44 380V", dxfattribs={"height": 2.5, "insert": (64, 96)})
    msp.add_text("II级试验组合型SPD", dxfattribs={"height": 2.5, "insert": (10, 88)})
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

    dxf_path = tmp_path / "panel.dxf"
    doc.saveas(str(dxf_path))

    schedule = extract_panel_schedule(parse_cad(str(dxf_path)))
    assert schedule.header.code == "ALY"
    assert len(schedule.circuits) == 1
    assert schedule.circuits[0].circuit == "N1"
