"""配电箱系统图的结构化回路提取。"""

from __future__ import annotations

import re
import unicodedata
from statistics import median
from typing import Iterable, List, Optional, Sequence

from ..cad.parser import BBox, CadDocument, CadText
from .models import CircuitRow, PanelHeader, PanelSchedule

_BREAKER_RE = re.compile(
    r"(?P<breaker>[A-Za-z]{2,}[A-Za-z0-9-]*)\s*"
    r"(?P<poles>\d+P)\s*"
    r"(?P<curve>[A-D]型)\s*"
    r"(?P<rating>\d+(?:\.\d+)?A(?:/\d+(?:\.\d+)?)?)",
    re.IGNORECASE,
)
_CIRCUIT_RE = re.compile(r"\bN\d+\b", re.IGNORECASE)
_PHASE_RE = re.compile(r"\bL\d\b", re.IGNORECASE)
_LOAD_RE = re.compile(r"\d+(?:\.\d+)?\s*[Kk][Ww]")
_CONDUIT_RE = re.compile(r"^(?:SC|RC|JDG|KBG|CT|PC|FC)\d+$", re.IGNORECASE)
_CABLE_RE = re.compile(
    r"(?P<cable>[A-Z][A-Z0-9-]*\(?\d+\s*[Xx]\s*\d+\)?(?:\+\d+\s*[Xx]\s*\d+)?)"
    r"(?P<conduit>(?:SC|RC|JDG|KBG|CT|PC|FC)\d+)?",
    re.IGNORECASE,
)
_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")


def _normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").strip()


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", _normalize_text(text))


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", "", _normalize_text(text))


def _field_text(text: str) -> str:
    return _compact_text(text).replace("×", "X").replace("x", "X")


def _median_height(texts: Sequence[CadText]) -> float:
    heights = [float(t.height) for t in texts if float(t.height or 0) > 0]
    if heights:
        return float(median(heights))
    ys = sorted({round(float(t.y), 3) for t in texts}, reverse=True)
    diffs = [abs(a - b) for a, b in zip(ys, ys[1:]) if abs(a - b) > 0]
    if diffs:
        return max(2.0, float(median(diffs)))
    return 4.0


def cluster_rows_by_y(
    texts: Sequence[CadText], y_tol: Optional[float] = None
) -> List[List[CadText]]:
    if not texts:
        return []
    tol = float(y_tol) if y_tol is not None else max(1.0, _median_height(texts) / 2.0)
    rows: List[List[CadText]] = []
    row_ys: List[float] = []
    for text in sorted(texts, key=lambda item: (-float(item.y), float(item.x))):
        if not rows:
            rows.append([text])
            row_ys.append(float(text.y))
            continue
        if abs(float(text.y) - row_ys[-1]) <= tol:
            rows[-1].append(text)
            row_ys[-1] = sum(t.y for t in rows[-1]) / len(rows[-1])
        else:
            rows.append([text])
            row_ys.append(float(text.y))
    return [sorted(row, key=lambda item: float(item.x)) for row in rows]


def _estimated_right(text: CadText) -> float:
    height = float(text.height or 0) or 2.5
    width = max(height * 0.8, len(_normalize_text(text.text)) * height * 0.65)
    return float(text.x) + width


def order_row_by_x(row: Sequence[CadText], join_x_tol: Optional[float] = None) -> List[CadText]:
    if not row:
        return []
    ordered = sorted(row, key=lambda item: float(item.x))
    tol = (
        float(join_x_tol)
        if join_x_tol is not None
        else max(1.0, _median_height(ordered) * 0.6)
    )
    merged: List[CadText] = []
    for text in ordered:
        cleaned = _clean_text(text.text)
        if not cleaned:
            continue
        current = CadText(
            text=cleaned,
            x=float(text.x),
            y=float(text.y),
            layer=text.layer,
            height=float(text.height or 0),
        )
        if not merged:
            merged.append(current)
            continue
        prev = merged[-1]
        gap = float(current.x) - _estimated_right(prev)
        if gap <= tol:
            prev.text = f"{prev.text}{current.text}"
            prev.height = max(float(prev.height or 0), float(current.height or 0))
            prev.y = (float(prev.y) + float(current.y)) / 2.0
        else:
            merged.append(current)
    return merged


def _standard_breaker_match(match: re.Match[str]) -> dict:
    return {
        "breaker": match.group("breaker"),
        "poles": match.group("poles").upper(),
        "curve": match.group("curve").upper().replace("型", "型"),
        "rating": match.group("rating").upper(),
    }


def _extract_cable_and_conduit(tokens: Sequence[str]) -> tuple[str, str]:
    cable = ""
    conduit = ""
    for token in tokens:
        compact = _field_text(token)
        if not compact:
            continue
        if not conduit and _CONDUIT_RE.match(compact):
            conduit = compact.upper()
            continue
        if "X" not in compact:
            continue
        match = _CABLE_RE.search(compact)
        if match and not cable:
            cable = (match.group("cable") or "").upper()
            conduit = conduit or (match.group("conduit") or "").upper()
    return cable, conduit


def _find_token_match(tokens: Sequence[str], pattern: re.Pattern[str]) -> Optional[re.Match[str]]:
    for token in tokens:
        match = pattern.search(_field_text(token))
        if match:
            return match
    return None


def parse_circuit_fields(ordered_row: Sequence[CadText]) -> Optional[CircuitRow]:
    if not ordered_row:
        return None
    raw_texts = [_clean_text(item.text) for item in ordered_row if _clean_text(item.text)]
    if not raw_texts:
        return None
    row_text = " ".join(raw_texts)
    compact = _field_text(row_text)
    breaker_match = _BREAKER_RE.search(compact)
    circuit_match = _find_token_match(raw_texts, _CIRCUIT_RE) or _CIRCUIT_RE.search(row_text)
    phase_match = _find_token_match(raw_texts, _PHASE_RE) or _PHASE_RE.search(row_text)
    load_match = _find_token_match(raw_texts, _LOAD_RE) or _LOAD_RE.search(row_text)
    cable, conduit = _extract_cable_and_conduit(raw_texts)

    has_usage = False
    usage_parts: List[str] = []
    load_token_index = -1
    for idx, token in enumerate(raw_texts):
        if _LOAD_RE.search(_field_text(token)):
            load_token_index = idx
            stripped = _LOAD_RE.sub("", _normalize_text(token))
            stripped = stripped.strip(" ,，;；/")
            if stripped:
                usage_parts.append(stripped)
            break
    if load_token_index >= 0:
        for token in raw_texts[load_token_index + 1 :]:
            normalized = _normalize_text(token).strip(" ,，;；/")
            if normalized:
                usage_parts.append(normalized)
    usage = "".join(usage_parts).strip()
    has_usage = bool(usage and _CHINESE_RE.search(usage))

    if not (
        breaker_match or circuit_match
    ) or not (phase_match or cable or load_match or has_usage):
        return None

    breaker_fields = _standard_breaker_match(breaker_match) if breaker_match else {}
    y_values = [float(item.y) for item in ordered_row]
    return CircuitRow(
        circuit=(circuit_match.group(0).upper() if circuit_match else ""),
        breaker=breaker_fields.get("breaker", ""),
        poles=breaker_fields.get("poles", ""),
        curve=breaker_fields.get("curve", ""),
        rating=breaker_fields.get("rating", ""),
        phase=(phase_match.group(0).upper() if phase_match else ""),
        cable=cable,
        conduit=conduit,
        load=(load_match.group(0).upper().replace(" ", "") if load_match else ""),
        usage=usage,
        y=float(median(y_values)) if y_values else 0.0,
        raw_texts=raw_texts,
    )


def parse_header_fields(texts: Sequence[CadText]) -> PanelHeader:
    if not texts:
        return PanelHeader()
    rows = [order_row_by_x(row) for row in cluster_rows_by_y(texts)]
    lines = [" ".join(_clean_text(t.text) for t in row if _clean_text(t.text)) for row in rows]
    nonempty_lines = [line for line in lines if line]
    all_text = "\n".join(nonempty_lines)
    header = PanelHeader()

    def search_value(pattern: str, flags: int = re.IGNORECASE) -> str:
        match = re.search(pattern, all_text, flags)
        return _normalize_text(match.group(1)) if match else ""

    header.pe = search_value(r"Pe\s*=\s*([\d.]+\s*[kK][wW])")
    header.kx = search_value(r"Kx\s*=\s*([^\s,，;；]+)")
    header.cos_phi = search_value(r"Cos\s*[øØΦφ]?\s*=\s*([\d.]+)")
    header.ijs = search_value(r"Ijs\s*=\s*([\d.]+\s*A)")
    header.size = search_value(r"(\d+\s*[Xx×]\s*\d+\s*[Xx×]\s*\d+)")

    for line in nonempty_lines:
        breaker_match = _BREAKER_RE.search(_field_text(line))
        if breaker_match:
            breaker = _standard_breaker_match(breaker_match)
            header.main_breaker = " ".join(
                [breaker["breaker"], breaker["poles"], breaker["curve"], breaker["rating"]]
            )
            break

    for line in nonempty_lines:
        normalized = _normalize_text(line)
        compact = _field_text(line)
        if not header.contactor:
            match = re.search(r"\b([A-Z]{1,5}\d+(?:-\d+)+\s*\d+\s*V)\b", normalized, re.IGNORECASE)
            if match:
                header.contactor = _clean_text(match.group(1))
        if not header.spd and ("SPD" in compact.upper() or "级试验" in normalized):
            header.spd = normalized
        if not header.install:
            install_matches = re.findall(
                r"([^\s,，;；/]*?(?:挂墙|明装|暗装|距地|落地|安装)[^\s,，;；/]*)",
                normalized,
            )
            if install_matches:
                header.install = install_matches[-1]

    line_infos = []
    for row in rows:
        line = " ".join(_clean_text(t.text) for t in row if _clean_text(t.text))
        if not line:
            continue
        line_infos.append(
            {
                "line": _normalize_text(line),
                "y": max(float(t.y) for t in row),
                "height": max(float(t.height or 0) for t in row),
            }
        )

    name_candidates = [
        item
        for item in line_infos
        if _CHINESE_RE.search(item["line"])
        and "=" not in item["line"]
        and "SPD" not in item["line"].upper()
        and not re.search(r"(挂墙|明装|暗装|距地|Pe|Kx|Cos|Ijs)", item["line"], re.IGNORECASE)
    ]
    if name_candidates:
        chosen = sorted(
            name_candidates,
            key=lambda item: (item["height"], item["y"], len(item["line"])),
            reverse=True,
        )[0]
        header.name = chosen["line"]

    tokens = []
    for row in rows:
        for item in row:
            token = _field_text(item.text)
            if token:
                tokens.append((token, float(item.y), float(item.x)))
    code_candidates = [
        item
        for item in tokens
        if re.fullmatch(r"[A-Z]{2,6}", item[0])
        and item[0] not in {"SPD", "PE", "KX", "IJS"}
    ]
    if code_candidates:
        header.code = sorted(code_candidates, key=lambda item: (-item[1], item[2]))[0][0]

    return header


def extract_panel_schedule_from_texts(texts: Sequence[CadText]) -> PanelSchedule:
    circuits: List[CircuitRow] = []
    header_texts: List[CadText] = []
    for row in cluster_rows_by_y(list(texts)):
        ordered = order_row_by_x(row)
        circuit = parse_circuit_fields(ordered)
        if circuit is not None:
            circuits.append(circuit)
        else:
            header_texts.extend(ordered)
    circuits.sort(key=lambda item: -float(item.y))
    return PanelSchedule(
        header=parse_header_fields(header_texts or list(texts)),
        circuits=circuits,
    )


def extract_panel_schedule(
    document: CadDocument, bbox: Optional[BBox] = None
) -> PanelSchedule:
    texts = document.texts_in(bbox) if bbox is not None else document.texts
    return extract_panel_schedule_from_texts(texts)
