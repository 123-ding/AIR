"""SVG 矢量预览 + DWG「转换一次」缓存测试。"""

import os

import pytest

ezdxf = pytest.importorskip("ezdxf")

from app.cad import dwg as dwg_mod  # noqa: E402
from app.cad.svg_export import render_svg  # noqa: E402


def _make_sample_dxf(path: str) -> None:
    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (100, 0), (100, 50), (0, 50)], close=True)
    msp.add_text("AL1", dxfattribs={"height": 5, "insert": (10, 10)})
    doc.saveas(path)


def test_render_svg_returns_svg_string(tmp_path):
    dxf = tmp_path / "a.dxf"
    _make_sample_dxf(str(dxf))
    svg = render_svg(str(dxf))
    assert svg.lstrip().startswith("<?xml")
    assert "<svg" in svg


def test_render_svg_writes_file(tmp_path):
    dxf = tmp_path / "a.dxf"
    _make_sample_dxf(str(dxf))
    out = tmp_path / "out" / "preview.svg"
    returned = render_svg(str(dxf), str(out))
    assert os.path.isfile(out)
    assert out.read_text(encoding="utf-8") == returned


def test_render_svg_with_bbox(tmp_path):
    dxf = tmp_path / "a.dxf"
    _make_sample_dxf(str(dxf))
    svg = render_svg(str(dxf), bbox=(0, 0, 50, 50))
    assert "<svg" in svg


def test_resolve_to_dxf_passes_through_dxf(tmp_path):
    dxf = tmp_path / "a.dxf"
    _make_sample_dxf(str(dxf))
    assert dwg_mod.resolve_to_dxf(str(dxf)) == str(dxf)


def test_resolve_to_dxf_converts_dwg_only_once(tmp_path):
    """DWG 多次解析只触发一次实际转换（缓存命中）。"""

    dwg_mod.clear_conversion_cache()
    src = tmp_path / "drawing.dwg"
    src.write_bytes(b"dwg")

    calls = {"n": 0}

    def fake_runner(cmd, **kwargs):
        calls["n"] += 1
        out_path = cmd[cmd.index("-o") + 1]
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("0\nSECTION\n")

        class _R:
            returncode = 0
            stderr = b""
            stdout = b""

        return _R()

    converter = ("libredwg", "/usr/bin/dwg2dxf")
    first = dwg_mod.resolve_to_dxf(
        str(src), converter=converter, runner=fake_runner
    )
    second = dwg_mod.resolve_to_dxf(
        str(src), converter=converter, runner=fake_runner
    )
    assert first == second
    assert calls["n"] == 1  # 第二次命中缓存，未再调用转换器
    dwg_mod.clear_conversion_cache()


def test_resolve_to_dxf_no_cache_converts_each_time(tmp_path):
    dwg_mod.clear_conversion_cache()
    src = tmp_path / "drawing.dwg"
    src.write_bytes(b"dwg")
    calls = {"n": 0}

    def fake_runner(cmd, **kwargs):
        calls["n"] += 1
        out_path = cmd[cmd.index("-o") + 1]
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("0\nSECTION\n")

        class _R:
            returncode = 0
            stderr = b""
            stdout = b""

        return _R()

    converter = ("libredwg", "/usr/bin/dwg2dxf")
    dwg_mod.resolve_to_dxf(
        str(src), use_cache=False, converter=converter, runner=fake_runner
    )
    dwg_mod.resolve_to_dxf(
        str(src), use_cache=False, converter=converter, runner=fake_runner
    )
    assert calls["n"] == 2


def test_resolve_to_dxf_rejects_unknown_extension(tmp_path):
    bad = tmp_path / "x.png"
    bad.write_bytes(b"png")
    with pytest.raises(ValueError):
        dwg_mod.resolve_to_dxf(str(bad))
