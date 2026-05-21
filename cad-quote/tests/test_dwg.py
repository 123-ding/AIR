"""测试 DWG → DXF 转换。

由于 ODA / LibreDWG 在 CI 环境通常未安装，所有测试通过注入 ``runner`` 桩来 mock
子进程调用。
"""

import os
import shutil

import pytest

from app.cad import dwg as dwg_mod
from app.cad.dwg import DWGConversionError, convert_dwg_to_dxf, find_converter
from app.cad.parser import parse_cad


class _FakeResult:
    def __init__(self, returncode=0, stderr=b""):
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = b""


def test_find_converter_prefers_oda(monkeypatch):
    def fake_which(name):
        return f"/usr/bin/{name}" if name == "ODAFileConverter" else None

    monkeypatch.setattr(shutil, "which", fake_which)
    found = find_converter()
    assert found == ("oda", "/usr/bin/ODAFileConverter")


def test_find_converter_falls_back_to_libredwg(monkeypatch):
    def fake_which(name):
        return f"/usr/bin/{name}" if name == "dwg2dxf" else None

    monkeypatch.setattr(shutil, "which", fake_which)
    assert find_converter() == ("libredwg", "/usr/bin/dwg2dxf")


def test_find_converter_returns_none(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    assert find_converter() is None


def test_convert_raises_when_no_converter_found(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    src = tmp_path / "a.dwg"
    src.write_bytes(b"dummy")
    with pytest.raises(DWGConversionError) as exc:
        convert_dwg_to_dxf(str(src))
    assert "ODA File Converter" in str(exc.value)


def test_convert_raises_when_source_missing():
    with pytest.raises(DWGConversionError):
        convert_dwg_to_dxf("/nonexistent/file.dwg")


def test_libredwg_path_runs_command(tmp_path):
    src = tmp_path / "drawing.dwg"
    src.write_bytes(b"dwg")

    captured = {}

    def fake_runner(cmd, **kwargs):
        captured["cmd"] = cmd
        # 模拟 libredwg 实际生成 dxf 文件
        out_path = cmd[cmd.index("-o") + 1]
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("0\nSECTION\n")
        return _FakeResult(returncode=0)

    out = convert_dwg_to_dxf(
        str(src),
        out_dir=str(tmp_path / "out"),
        converter=("libredwg", "/usr/bin/dwg2dxf"),
        runner=fake_runner,
    )
    assert os.path.isfile(out)
    assert captured["cmd"][0] == "/usr/bin/dwg2dxf"
    assert "-o" in captured["cmd"]


def test_oda_path_runs_command(tmp_path):
    src = tmp_path / "drawing.dwg"
    src.write_bytes(b"dwg")

    out_dir = tmp_path / "out"

    def fake_runner(cmd, **kwargs):
        # ODA 是把 outDir 作为第三参数；我们模拟它写文件
        out_dir_arg = cmd[2]
        os.makedirs(out_dir_arg, exist_ok=True)
        with open(os.path.join(out_dir_arg, "drawing.dxf"), "w") as f:
            f.write("0\nSECTION\n")
        return _FakeResult(returncode=0)

    out = convert_dwg_to_dxf(
        str(src),
        out_dir=str(out_dir),
        converter=("oda", "/usr/bin/ODAFileConverter"),
        runner=fake_runner,
    )
    assert os.path.isfile(out)
    assert out.endswith("drawing.dxf")


def test_libredwg_failure_raises(tmp_path):
    src = tmp_path / "drawing.dwg"
    src.write_bytes(b"dwg")

    def fake_runner(cmd, **kwargs):
        return _FakeResult(returncode=2, stderr=b"corrupt file")

    with pytest.raises(DWGConversionError) as exc:
        convert_dwg_to_dxf(
            str(src),
            out_dir=str(tmp_path / "out"),
            converter=("libredwg", "/usr/bin/dwg2dxf"),
            runner=fake_runner,
        )
    assert "corrupt file" in str(exc.value)


def test_libredwg_success_but_no_output_raises(tmp_path):
    src = tmp_path / "drawing.dwg"
    src.write_bytes(b"dwg")

    def fake_runner(cmd, **kwargs):
        return _FakeResult(returncode=0)  # 不写文件

    with pytest.raises(DWGConversionError):
        convert_dwg_to_dxf(
            str(src),
            out_dir=str(tmp_path / "out"),
            converter=("libredwg", "/usr/bin/dwg2dxf"),
            runner=fake_runner,
        )


def test_parse_cad_rejects_unknown_extension(tmp_path):
    src = tmp_path / "x.png"
    src.write_bytes(b"png")
    with pytest.raises(ValueError):
        parse_cad(str(src))
