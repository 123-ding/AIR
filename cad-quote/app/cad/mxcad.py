"""MxCAD Web drawing conversion helpers.

MxCAD renders the vendor-specific ``.mxweb`` format in the browser.  DWG/DXF
files must first be converted with the ``mxcadassembly`` tool from the MxDraw
CloudDraw package.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional


class MxCadConversionError(RuntimeError):
    """Raised when a CAD file cannot be converted to ``.mxweb``."""


Runner = Callable[..., subprocess.CompletedProcess]


def find_assembler() -> Optional[str]:
    """Locate the ``mxcadassembly`` executable."""

    configured = os.environ.get("MXCAD_ASSEMBLY")
    if configured:
        return configured
    return shutil.which("mxcadassembly") or shutil.which("mxcadassembly.exe")


def _decode_output(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="ignore")
    return str(value)


def convert_to_mxweb(
    src_path: str,
    out_dir: Optional[str] = None,
    out_name: Optional[str] = None,
    assembler: Optional[str] = None,
    runner: Runner = subprocess.run,
) -> str:
    """Convert a DWG/DXF file to ``.mxweb`` and return the output path."""

    src = Path(src_path)
    if not src.is_file():
        raise MxCadConversionError(f"源 CAD 文件不存在：{src_path}")
    if src.suffix.lower() == ".mxweb":
        return str(src)

    exe = assembler or find_assembler()
    if not exe:
        raise MxCadConversionError(
            "未找到 mxcadassembly。请安装 MxDraw CloudDraw 开发包，"
            "并将 mxcadassembly 加入 PATH，或设置 MXCAD_ASSEMBLY。"
        )

    output_dir = Path(out_dir or tempfile.mkdtemp(prefix="mxcad_mxweb_"))
    output_dir.mkdir(parents=True, exist_ok=True)
    name = out_name or src.stem
    name_without_suffix = name[:-6] if name.lower().endswith(".mxweb") else name

    payload = {
        "srcpath": str(src.resolve()),
        "outpath": str(output_dir.resolve()),
        "outname": name_without_suffix,
        "compression": 0,
    }
    result = runner(
        [exe, json.dumps(payload, ensure_ascii=False)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        detail = _decode_output(result.stderr) or _decode_output(result.stdout)
        raise MxCadConversionError(f"mxcadassembly 转换失败：{detail}".strip())

    candidates = [
        output_dir / f"{name_without_suffix}.mxweb",
        output_dir / name_without_suffix,
        src.with_suffix(".mxweb"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    output = _decode_output(result.stdout) + _decode_output(result.stderr)
    raise MxCadConversionError(f"mxcadassembly 未生成 mxweb 文件。{output}".strip())
