"""测试 mxcad mxweb 转换封装。"""

import json
import os
import shutil

import pytest

from app.cad.mxcad import MxCadConversionError, convert_to_mxweb, find_assembler


class _FakeResult:
    def __init__(self, returncode=0, stderr=b"", stdout=b""):
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout


def test_find_assembler_prefers_env(monkeypatch):
    monkeypatch.setenv("MXCAD_ASSEMBLY", "/opt/mx/mxcadassembly")
    assert find_assembler() == "/opt/mx/mxcadassembly"


def test_find_assembler_from_path(monkeypatch):
    monkeypatch.delenv("MXCAD_ASSEMBLY", raising=False)

    def fake_which(name):
        return f"/usr/bin/{name}" if name == "mxcadassembly" else None

    monkeypatch.setattr(shutil, "which", fake_which)
    assert find_assembler() == "/usr/bin/mxcadassembly"


def test_convert_to_mxweb_returns_existing_mxweb(tmp_path):
    src = tmp_path / "drawing.mxweb"
    src.write_bytes(b"mxweb")
    assert convert_to_mxweb(str(src)) == str(src)


def test_convert_to_mxweb_runs_assembler(tmp_path):
    src = tmp_path / "drawing.dxf"
    src.write_bytes(b"dxf")
    out_dir = tmp_path / "out"
    captured = {}

    def fake_runner(cmd, **kwargs):
        captured["cmd"] = cmd
        payload = json.loads(cmd[1])
        assert payload["srcpath"] == str(src.resolve())
        os.makedirs(payload["outpath"], exist_ok=True)
        with open(os.path.join(payload["outpath"], payload["outname"] + ".mxweb"), "wb") as f:
            f.write(b"mxweb")
        return _FakeResult()

    out = convert_to_mxweb(
        str(src),
        out_dir=str(out_dir),
        out_name="converted",
        assembler="/usr/bin/mxcadassembly",
        runner=fake_runner,
    )
    assert out == str(out_dir / "converted.mxweb")
    assert captured["cmd"][0] == "/usr/bin/mxcadassembly"


def test_convert_to_mxweb_raises_without_assembler(tmp_path, monkeypatch):
    monkeypatch.delenv("MXCAD_ASSEMBLY", raising=False)
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    src = tmp_path / "drawing.dxf"
    src.write_bytes(b"dxf")
    with pytest.raises(MxCadConversionError):
        convert_to_mxweb(str(src))


def test_convert_to_mxweb_raises_on_failure(tmp_path):
    src = tmp_path / "drawing.dxf"
    src.write_bytes(b"dxf")

    def fake_runner(cmd, **kwargs):
        return _FakeResult(returncode=1, stderr=b"bad cad")

    with pytest.raises(MxCadConversionError) as exc:
        convert_to_mxweb(
            str(src), assembler="/usr/bin/mxcadassembly", runner=fake_runner
        )
    assert "bad cad" in str(exc.value)
