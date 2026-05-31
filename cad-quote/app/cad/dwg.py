"""DWG → DXF 自动转换。

P2 目标：让 ``parse_cad(path)`` 能直接接收 ``.dwg``，在解析前先调用本机已安装的
转换器把它转成 ``.dxf``。

支持的转换器（按优先级探测）：

1. **ODA File Converter** (``ODAFileConverter`` / ``ODAFileConverter.exe``)：批量目录转换。
2. **LibreDWG ``dwg2dxf``**：单文件命令行转换。

两者都不可用时抛出 :class:`DWGConversionError`，错误信息中给出官方下载页面。

为方便测试，本模块暴露了：

* :func:`find_converter` — 探测转换器，返回 ``("oda" | "libredwg", executable_path)`` 或 ``None``。
* :func:`convert_dwg_to_dxf(src, out_dir, *, converter=None, runner=None)` — 实际转换。
  ``runner`` 是可注入的 ``subprocess.run`` 替代品，便于单测 mock。
* :func:`resolve_to_dxf(path, *, use_cache=True, **convert_kwargs)` — 归一为 DXF 路径，
  DWG 按文件指纹缓存「只转换一次」，解析与 SVG 预览复用同一份 DXF。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Callable, Dict, Optional, Tuple

# 可注入的 subprocess 调用：(cmd: list[str]) -> CompletedProcess
SubprocessRunner = Callable[..., "subprocess.CompletedProcess"]


class DWGConversionError(RuntimeError):
    """DWG → DXF 转换失败。"""


# 进程内「转换一次」缓存：key = (abspath, mtime_ns, size) → 已生成的 DXF 路径。
# 同一份 DWG 在解析与 SVG 预览之间只需调用一次 ODA/LibreDWG，后续全程走 ezdxf。
_CONVERSION_CACHE: Dict[Tuple[str, int, int], str] = {}


def _cache_key(path: str) -> Tuple[str, int, int]:
    st = os.stat(path)
    return (os.path.abspath(path), st.st_mtime_ns, st.st_size)


def clear_conversion_cache() -> None:
    """清空 DWG→DXF 转换缓存（主要用于测试）。"""

    _CONVERSION_CACHE.clear()


_ODA_CANDIDATES = (
    "ODAFileConverter",
    "ODAFileConverter.exe",
    "oda_file_converter",
)

_LIBREDWG_CANDIDATES = (
    "dwg2dxf",
    "dwg2dxf.exe",
)


def find_converter() -> Optional[Tuple[str, str]]:
    """探测可用的 DWG 转换器。

    :return: ``("oda", path)`` / ``("libredwg", path)`` / ``None``。
    """

    for name in _ODA_CANDIDATES:
        path = shutil.which(name)
        if path:
            return ("oda", path)
    for name in _LIBREDWG_CANDIDATES:
        path = shutil.which(name)
        if path:
            return ("libredwg", path)
    return None


def _default_runner(cmd, **kwargs):  # pragma: no cover - 仅在真实环境调用
    return subprocess.run(cmd, **kwargs)


def convert_dwg_to_dxf(
    src: str,
    out_dir: Optional[str] = None,
    *,
    converter: Optional[Tuple[str, str]] = None,
    runner: Optional[SubprocessRunner] = None,
    timeout: int = 120,
) -> str:
    """把 DWG 转换为同名 DXF，返回 DXF 文件绝对路径。

    :param src: ``.dwg`` 文件路径。
    :param out_dir: 输出目录；缺省使用临时目录。
    :param converter: 显式指定 ``(kind, exe_path)``；缺省自动探测。
    :param runner: 自定义 ``subprocess.run`` 风格 runner，便于注入测试桩。
    :param timeout: 子进程超时秒数。
    :raises DWGConversionError: 找不到转换器、子进程失败、或输出文件未生成。
    """

    if not os.path.isfile(src):
        raise DWGConversionError(f"源文件不存在：{src}")
    chosen = converter or find_converter()
    if chosen is None:
        raise DWGConversionError(
            "未找到可用的 DWG 转换器。请安装 ODA File Converter "
            "(https://www.opendesign.com/guestfiles/oda_file_converter) 或 "
            "LibreDWG (https://www.gnu.org/software/libredwg/) 后重试。"
        )
    kind, exe = chosen
    runner = runner or _default_runner

    if out_dir is None:
        out_dir = tempfile.mkdtemp(prefix="dwg2dxf_")
    os.makedirs(out_dir, exist_ok=True)

    base = os.path.splitext(os.path.basename(src))[0]
    out_path = os.path.join(out_dir, base + ".dxf")

    if kind == "libredwg":
        cmd = [exe, "-o", out_path, src]
    elif kind == "oda":
        # ODA File Converter 命令行接口：
        #   ODAFileConverter <inDir> <outDir> <outVer> <outFmt> <recurse> <audit> [filter]
        # 我们用单文件子目录避免污染：
        in_dir = tempfile.mkdtemp(prefix="dwg_in_")
        try:
            staged = os.path.join(in_dir, os.path.basename(src))
            shutil.copy2(src, staged)
            cmd = [
                exe,
                in_dir,
                out_dir,
                "ACAD2018",
                "DXF",
                "0",  # 不递归
                "1",  # 审核
                os.path.basename(src),
            ]
            try:
                _run_converter(runner, cmd, timeout)
            finally:
                shutil.rmtree(in_dir, ignore_errors=True)
            if not os.path.isfile(out_path):
                raise DWGConversionError(
                    f"ODA File Converter 未生成预期文件：{out_path}"
                )
            return out_path
        except DWGConversionError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise DWGConversionError(f"ODA 转换失败：{exc}") from exc
    else:  # pragma: no cover - 防御
        raise DWGConversionError(f"不支持的转换器类型：{kind!r}")

    # libredwg 路径
    _run_converter(runner, cmd, timeout)
    if not os.path.isfile(out_path):
        raise DWGConversionError(
            f"libredwg 未生成预期文件：{out_path}（命令：{' '.join(cmd)}）"
        )
    return out_path


def _run_converter(runner: SubprocessRunner, cmd, timeout: int) -> None:
    try:
        result = runner(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise DWGConversionError(f"DWG 转换超时（>{timeout}s）。") from exc
    except FileNotFoundError as exc:
        raise DWGConversionError(f"无法执行转换器：{exc}") from exc
    if getattr(result, "returncode", 0) != 0:
        stderr = getattr(result, "stderr", b"") or b""
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        raise DWGConversionError(
            f"DWG 转换失败（returncode={result.returncode}）：{stderr.strip()}"
        )


def resolve_to_dxf(
    path: str,
    *,
    use_cache: bool = True,
    **convert_kwargs,
) -> str:
    """把任意 CAD 输入归一为 DXF 路径，DWG 只转换一次。

    * ``.dxf`` 直接返回原路径（无需转换）。
    * ``.dwg`` 调用 :func:`convert_dwg_to_dxf` 转换；结果按文件指纹缓存，
      同一份 DWG 在一个进程内（解析 + SVG 预览等）只转换一次，后续全程走 ezdxf。

    :param use_cache: 是否启用进程内转换缓存（测试可关闭）。
    :param convert_kwargs: 透传给 :func:`convert_dwg_to_dxf`（如 ``converter`` / ``runner``）。
    :raises ValueError: 不支持的扩展名。
    """

    ext = os.path.splitext(path)[1].lower()
    if ext == ".dxf":
        return path
    if ext != ".dwg":
        raise ValueError(f"不支持的 CAD 文件扩展名：{ext!r}（仅支持 .dxf / .dwg）")

    if not use_cache:
        return convert_dwg_to_dxf(path, **convert_kwargs)

    try:
        key = _cache_key(path)
    except OSError:
        return convert_dwg_to_dxf(path, **convert_kwargs)

    cached = _CONVERSION_CACHE.get(key)
    if cached and os.path.isfile(cached):
        return cached

    dxf_path = convert_dwg_to_dxf(path, **convert_kwargs)
    _CONVERSION_CACHE[key] = dxf_path
    return dxf_path
