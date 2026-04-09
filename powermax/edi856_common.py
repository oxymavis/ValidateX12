"""
Shared helpers for partner-specific 856 validators.
Element positions follow X12: seg[0]=segment tag, seg[1]=element 01, ...
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

FindingDict = Dict[str, Any]


def parse_edi(content: str) -> List[List[str]]:
    content = content.strip().replace("~\r\n", "~").replace("~\n", "~").replace("\n", "~")
    if not content:
        return []
    return [s.split("*") for s in content.split("~") if s.strip()]


def elem(seg: List[str], i: int) -> str:
    if i <= 0 or i >= len(seg):
        return ""
    return (seg[i] or "").strip()


def raw_elem(seg: List[str], i: int) -> str:
    if i <= 0 or i >= len(seg):
        return ""
    return seg[i] or ""


def get_all(segs: List[List[str]], tag: str) -> List[List[str]]:
    return [s for s in segs if s and s[0] == tag]


def is_ccyymmdd(s: str) -> bool:
    if not re.fullmatch(r"\d{8}", s or ""):
        return False
    try:
        datetime.strptime(s, "%Y%m%d")
        return True
    except ValueError:
        return False


def is_time_x12(s: str) -> bool:
    """X12 TM: HHMM, HHMMSS, HHMMSSD, HHMMSSDD."""
    if not s:
        return False
    return bool(re.fullmatch(r"\d{4}|\d{6}|\d{7}|\d{8}", s))


def is_int(s: str) -> bool:
    return bool(re.fullmatch(r"-?\d+", s or ""))


def add(
    out: List[FindingDict],
    spec: str,
    code: str,
    seg_name: str,
    el_ref: str,
    msg: str,
    sev: str = "Error",
) -> None:
    out.append(
        {
            "spec": spec,
            "code": code,
            "segment": seg_name,
            "element": el_ref,
            "severity": sev,
            "message": msg,
        }
    )


def envelope_v5010_sh(
    segs: List[List[str]],
    spec: str,
    out: List[FindingDict],
    *,
    gs03_allowed: Optional[set] = None,
    isa12: str = "00501",
    gs08: str = "005010",
) -> None:
    """ISA/GS/GE/IEA/ST/SE for V5010 + GS01=SH."""
    isa = get_all(segs, "ISA")
    gs = get_all(segs, "GS")
    ge = get_all(segs, "GE")
    iea = get_all(segs, "IEA")
    st = get_all(segs, "ST")
    se = get_all(segs, "SE")

    if not isa:
        add(out, spec, "ENV001", "ISA", "", "ISA missing")
        return
    i = isa[0]
    if elem(i, 12) != isa12:
        add(out, spec, "ENV002", "ISA", "ISA12", f"ISA12 must be {isa12} (got {elem(i, 12)!r})")
    if len(raw_elem(i, 6)) != 15:
        add(out, spec, "ENV003", "ISA", "ISA06", "ISA06 must be 15 characters")
    if len(raw_elem(i, 8)) != 15:
        add(out, spec, "ENV004", "ISA", "ISA08", "ISA08 must be 15 characters")
    if elem(i, 1) != "00":
        add(out, spec, "ENV005", "ISA", "ISA01", "ISA01 must be 00", "Warning")
    if elem(i, 3) != "00":
        add(out, spec, "ENV006", "ISA", "ISA03", "ISA03 must be 00", "Warning")

    if gs:
        g = gs[0]
        if elem(g, 1) != "SH":
            add(out, spec, "ENV010", "GS", "GS01", f"Functional group for 856 must be SH (got {elem(g, 1)!r})")
        if elem(g, 8) != gs08:
            add(out, spec, "ENV011", "GS", "GS08", f"GS08 must be {gs08!r} (got {elem(g, 8)!r})")
        if elem(g, 7) != "X":
            add(out, spec, "ENV012", "GS", "GS07", "GS07 must be X")
        if gs03_allowed is not None and elem(g, 3) not in gs03_allowed:
            add(out, spec, "ENV013", "GS", "GS03", f"GS03 {elem(g, 3)!r} not in partner allow-list", "Warning")
    else:
        add(out, spec, "ENV014", "GS", "", "GS missing")

    if gs and ge and elem(ge[0], 2) != elem(gs[0], 6):
        add(out, spec, "ENV020", "GE", "GE02", "GE02 must equal GS06")
    if isa and iea and elem(iea[0], 2) != elem(isa[0], 13):
        add(out, spec, "ENV021", "IEA", "IEA02", "IEA02 must equal ISA13")

    st_i = next((x for x, s in enumerate(segs) if s and s[0] == "ST"), None)
    se_i = next((x for x, s in enumerate(segs) if s and s[0] == "SE"), None)
    if st and se and st_i is not None and se_i is not None:
        if elem(se[0], 2) != elem(st[0], 2):
            add(out, spec, "ENV030", "SE", "SE02", "SE02 must equal ST02")
        if is_int(elem(se[0], 1)):
            if int(elem(se[0], 1)) != se_i - st_i + 1:
                add(
                    out,
                    spec,
                    "ENV031",
                    "SE",
                    "SE01",
                    f"SE01 count: expected {se_i - st_i + 1}, got {elem(se[0], 1)}",
                )


def envelope_v4010_sh(
    segs: List[List[str]],
    spec: str,
    out: List[FindingDict],
    *,
    gs03_allowed: Optional[set] = None,
    isa12: str = "00401",
    gs08: str = "004010",
) -> None:
    envelope_v5010_sh(segs, spec, out, gs03_allowed=gs03_allowed, isa12=isa12, gs08=gs08)


def transaction_body(segs: List[List[str]]) -> List[List[str]]:
    st_i = next((i for i, s in enumerate(segs) if s and s[0] == "ST"), None)
    se_i = next((i for i, s in enumerate(segs) if s and s[0] == "SE"), None)
    if st_i is None or se_i is None or se_i <= st_i:
        return []
    return segs[st_i + 1 : se_i]


def hl_validate_chain(body: List[List[str]], spec: str, out: List[FindingDict], code_prefix: str) -> None:
    hls = [s for s in body if s and s[0] == "HL"]
    seen: set = set()
    for h in hls:
        h01, h02 = elem(h, 1), elem(h, 2)
        if not h01:
            add(out, spec, f"{code_prefix}HL01", "HL", "HL01", "HL01 hierarchical ID required")
            continue
        if h01 in seen:
            add(out, spec, f"{code_prefix}HL02", "HL", "HL01", f"Duplicate HL01 {h01!r}")
        if h02 and h02 not in seen:
            add(out, spec, f"{code_prefix}HL03", "HL", "HL02", f"HL02 parent {h02!r} must reference prior HL01")
        if h01 not in seen:
            seen.add(h01)
