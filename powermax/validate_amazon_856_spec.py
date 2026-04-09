#!/usr/bin/env python3
"""
Amazon Retail X12 856 V5010 validator based on Amazon_856.pdf.

This validator covers the explicit structural and field rules stated in the PDF.
Rules that the PDF marks as business-conditional are emitted as warnings where the
condition cannot be derived from the EDI alone.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from edi856_common import (
    add,
    elem,
    get_all,
    is_ccyymmdd,
    is_time_x12,
    parse_edi,
    raw_elem,
)

SPEC = "Amazon_856.pdf Retail V5010"
AMAZON_IDS = {"AMAZON", "AMAZONCA", "AMAZONMX", "AMAZONBR", "AMAZONSG", "AMAZONAU"}
SF_QUALIFIERS = {"1", "15", "92", "UL", "ZZ"}
ST_QUALIFIERS = {"15", "92", "UL"}
LIN_QUALIFIERS = {"BP", "EN", "IB", "UA", "UK", "UP", "VN"}
SN1_UOMS = {"CA", "EA"}
SHIP_DTM_QUALIFIERS = {"011", "017"}
V1_DTM_QUALIFIERS = {"AAA", "DFS"}
ITEM_DTM_QUALIFIERS = {"036", "094"}


@dataclass
class HLLoop:
    body_index: int
    end_index: int
    seg: List[str]

    @property
    def hl_id(self) -> str:
        return elem(self.seg, 1)

    @property
    def parent_id(self) -> str:
        return elem(self.seg, 2)

    @property
    def level(self) -> str:
        return elem(self.seg, 3)


def is_int(value: str) -> bool:
    return bool(re.fullmatch(r"\d+", value or ""))


def is_number(value: str) -> bool:
    return bool(re.fullmatch(r"-?\d+(?:\.\d+)?", value or ""))


def add_tx(
    out: List[Dict[str, Any]],
    st02: str,
    code: str,
    segment: str,
    element: str,
    message: str,
    severity: str = "Error",
) -> None:
    suffix = f" [ST02={st02}]" if st02 else ""
    add(out, SPEC, code, segment, element, f"{message}{suffix}", severity)


def iter_transactions(segments: List[List[str]]) -> List[Tuple[int, int]]:
    txs: List[Tuple[int, int]] = []
    st_idx: Optional[int] = None
    for i, seg in enumerate(segments):
        if not seg:
            continue
        if seg[0] == "ST":
            st_idx = i
        elif seg[0] == "SE" and st_idx is not None:
            txs.append((st_idx, i))
            st_idx = None
    return txs


def build_hl_loops(body: List[List[str]]) -> List[HLLoop]:
    starts = [i for i, seg in enumerate(body) if seg and seg[0] == "HL"]
    loops: List[HLLoop] = []
    for pos, start in enumerate(starts):
        end = starts[pos + 1] if pos + 1 < len(starts) else len(body)
        loops.append(HLLoop(body_index=start, end_index=end, seg=body[start]))
    return loops


def slice_after(loop: HLLoop, body: List[List[str]]) -> List[List[str]]:
    return body[loop.body_index + 1 : loop.end_index]


def validate_envelope(segments: List[List[str]], out: List[Dict[str, Any]], gs03_allow: Set[str]) -> None:
    isa_list = get_all(segments, "ISA")
    gs_list = get_all(segments, "GS")
    ge_list = get_all(segments, "GE")
    iea_list = get_all(segments, "IEA")
    txs = iter_transactions(segments)

    if not isa_list:
        add(out, SPEC, "ENV001", "ISA", "", "ISA missing")
        return

    isa = isa_list[0]
    if elem(isa, 1) != "00":
        add(out, SPEC, "ENV002", "ISA", "ISA01", "ISA01 must be 00", "Warning")
    if elem(isa, 3) != "00":
        add(out, SPEC, "ENV003", "ISA", "ISA03", "ISA03 must be 00", "Warning")
    if elem(isa, 5) not in {"01", "02", "03", "04", "07", "08", "09", "11", "12", "14", "16", "ZZ"}:
        add(out, SPEC, "ENV004", "ISA", "ISA05", "ISA05 must be a valid interchange qualifier", "Warning")
    if len(raw_elem(isa, 6)) != 15:
        add(out, SPEC, "ENV005", "ISA", "ISA06", "ISA06 must be exactly 15 characters")
    if elem(isa, 7) != "ZZ":
        add(out, SPEC, "ENV006", "ISA", "ISA07", "ISA07 must be ZZ")
    if len(raw_elem(isa, 8)) != 15:
        add(out, SPEC, "ENV007", "ISA", "ISA08", "ISA08 must be exactly 15 characters")
    if elem(isa, 8).strip() not in gs03_allow:
        add(out, SPEC, "ENV008", "ISA", "ISA08", f"ISA08 {elem(isa, 8)!r} not in Amazon receiver ID allow-list", "Warning")
    if not re.fullmatch(r"\d{6}", elem(isa, 9) or ""):
        add(out, SPEC, "ENV009", "ISA", "ISA09", "ISA09 must be YYMMDD")
    if not re.fullmatch(r"\d{4}", elem(isa, 10) or ""):
        add(out, SPEC, "ENV010", "ISA", "ISA10", "ISA10 must be HHMM")
    if not elem(isa, 11):
        add(out, SPEC, "ENV011", "ISA", "ISA11", "ISA11 repetition separator required")
    elif elem(isa, 11) != "^":
        add(out, SPEC, "ENV012", "ISA", "ISA11", "ISA11 should be ^ per Amazon examples", "Warning")
    if elem(isa, 12) != "00501":
        add(out, SPEC, "ENV013", "ISA", "ISA12", "ISA12 must be 00501")
    if not re.fullmatch(r"\d{9}", elem(isa, 13) or ""):
        add(out, SPEC, "ENV014", "ISA", "ISA13", "ISA13 must be a 9-digit control number")
    if elem(isa, 14) != "0":
        add(out, SPEC, "ENV015", "ISA", "ISA14", "ISA14 should be 0 per Amazon spec", "Warning")
    if elem(isa, 15) not in {"P", "T"}:
        add(out, SPEC, "ENV016", "ISA", "ISA15", "ISA15 must be P or T")
    if len(elem(isa, 16)) != 1:
        add(out, SPEC, "ENV017", "ISA", "ISA16", "ISA16 component separator must be one character")

    if not gs_list:
        add(out, SPEC, "ENV018", "GS", "", "GS missing")
    else:
        gs = gs_list[0]
        if elem(gs, 1) != "SH":
            add(out, SPEC, "ENV019", "GS", "GS01", "GS01 must be SH")
        if not elem(gs, 2) or not (2 <= len(elem(gs, 2)) <= 15):
            add(out, SPEC, "ENV020", "GS", "GS02", "GS02 sender code length must be 2-15")
        if elem(gs, 3) not in gs03_allow:
            add(out, SPEC, "ENV021", "GS", "GS03", f"GS03 {elem(gs, 3)!r} not in Amazon receiver ID allow-list", "Warning")
        if not is_ccyymmdd(elem(gs, 4)):
            add(out, SPEC, "ENV022", "GS", "GS04", "GS04 must be CCYYMMDD")
        if not is_time_x12(elem(gs, 5)):
            add(out, SPEC, "ENV023", "GS", "GS05", "GS05 must be a valid X12 TM")
        if not re.fullmatch(r"\d{1,9}", elem(gs, 6) or ""):
            add(out, SPEC, "ENV024", "GS", "GS06", "GS06 must be a numeric control number 1-9 digits")
        if elem(gs, 7) != "X":
            add(out, SPEC, "ENV025", "GS", "GS07", "GS07 must be X")
        if elem(gs, 8) != "005010":
            add(out, SPEC, "ENV026", "GS", "GS08", "GS08 must be 005010")

    if ge_list and gs_list:
        ge = ge_list[0]
        gs = gs_list[0]
        if not re.fullmatch(r"\d{1,6}", elem(ge, 1) or ""):
            add(out, SPEC, "ENV027", "GE", "GE01", "GE01 must be numeric 1-6 digits")
        elif int(elem(ge, 1)) != len(txs):
            add(out, SPEC, "ENV028", "GE", "GE01", f"GE01 should equal transaction count ({len(txs)})")
        if elem(ge, 2) != elem(gs, 6):
            add(out, SPEC, "ENV029", "GE", "GE02", "GE02 must equal GS06")

    if iea_list:
        iea = iea_list[0]
        if not re.fullmatch(r"\d{1,5}", elem(iea, 1) or ""):
            add(out, SPEC, "ENV030", "IEA", "IEA01", "IEA01 must be numeric 1-5 digits")
        elif int(elem(iea, 1)) != len(gs_list):
            add(out, SPEC, "ENV031", "IEA", "IEA01", f"IEA01 should equal functional group count ({len(gs_list)})")
        if elem(iea, 2) != elem(isa, 13):
            add(out, SPEC, "ENV032", "IEA", "IEA02", "IEA02 must equal ISA13")


def validate_n1_loops(chunk: List[List[str]], st02: str, out: List[Dict[str, Any]]) -> None:
    loops: List[Tuple[List[str], List[List[str]]]] = []
    current_n1: Optional[List[str]] = None
    current_tail: List[List[str]] = []

    for seg in chunk:
        if not seg:
            continue
        if seg[0] == "N1":
            if current_n1 is not None:
                loops.append((current_n1, current_tail))
            current_n1 = seg
            current_tail = []
        elif current_n1 is not None:
            current_tail.append(seg)
    if current_n1 is not None:
        loops.append((current_n1, current_tail))

    sf_found = False
    st_found = False

    for n1, tail in loops:
        code = elem(n1, 1)
        if code == "SF":
            sf_found = True
            if elem(n1, 2):
                add_tx(out, st02, "N1SF02", "N1", "N102", "Ship From N102 is not used", "Warning")
            if elem(n1, 3) not in SF_QUALIFIERS:
                add_tx(out, st02, "N1SF03", "N1", "N103", "Ship From N103 must be one of 1, 15, 92, UL, ZZ")
            if not elem(n1, 4):
                add_tx(out, st02, "N1SF04", "N1", "N104", "Ship From N104 is required")

            n4 = next((seg for seg in tail if seg and seg[0] == "N4"), None)
            if not n4:
                add_tx(out, st02, "N4SF00", "N4", "", "Ship From N4 is required")
            else:
                if not elem(n4, 1):
                    add_tx(out, st02, "N4SF01", "N4", "N401", "Ship From city is required")
                if not elem(n4, 3):
                    add_tx(out, st02, "N4SF03", "N4", "N403", "Ship From postal code is required")
                if not elem(n4, 4):
                    add_tx(out, st02, "N4SF04", "N4", "N404", "Ship From country code is required")
                elif len(elem(n4, 4)) != 2:
                    add_tx(out, st02, "N4SF05", "N4", "N404", "Ship From country code must be ISO alpha-2")
                elif elem(n4, 4) == "USA":
                    add_tx(out, st02, "N4SF06", "N4", "N404", "Use US instead of USA", "Warning")

        elif code == "ST":
            st_found = True
            if elem(n1, 2):
                add_tx(out, st02, "N1ST02", "N1", "N102", "Ship To N102 is not used", "Warning")
            if elem(n1, 3) not in ST_QUALIFIERS:
                add_tx(out, st02, "N1ST03", "N1", "N103", "Ship To N103 must be one of 15, 92, UL")
            if not elem(n1, 4):
                add_tx(out, st02, "N1ST04", "N1", "N104", "Ship To N104 is required")

    if not sf_found:
        add_tx(out, st02, "N1SF00", "N1", "N101", "N1*SF Ship From loop is required")
    if not st_found:
        add_tx(out, st02, "N1ST00", "N1", "N101", "N1*ST Ship To loop is required")


def validate_shipment_td1(td1: List[str], st02: str, out: List[Dict[str, Any]], index: int) -> None:
    if elem(td1, 1) not in {"CTN", "PLT"}:
        add_tx(out, st02, f"TD1S{index:02d}01", "TD1", "TD101", "Shipment TD101 must be CTN or PLT")
    if not is_int(elem(td1, 2)):
        add_tx(out, st02, f"TD1S{index:02d}02", "TD1", "TD102", "Shipment TD102 must be an integer count")
    if elem(td1, 5) and elem(td1, 5) not in {"FLR", "PLT"}:
        add_tx(out, st02, f"TD1S{index:02d}05", "TD1", "TD105", "Shipment TD105, if used, should be FLR or PLT", "Warning")
    if elem(td1, 6) and elem(td1, 6) != "G":
        add_tx(out, st02, f"TD1S{index:02d}06", "TD1", "TD106", "Shipment TD106 should be G", "Warning")
    if elem(td1, 7) and not is_number(elem(td1, 7)):
        add_tx(out, st02, f"TD1S{index:02d}07", "TD1", "TD107", "Shipment TD107 must be numeric")
    if elem(td1, 7) and elem(td1, 8) not in {"GR", "KG", "LB", "OZ"}:
        add_tx(out, st02, f"TD1S{index:02d}08", "TD1", "TD108", "Shipment TD108 must be GR, KG, LB, or OZ when TD107 is used")
    if elem(td1, 9) and not is_number(elem(td1, 9)):
        add_tx(out, st02, f"TD1S{index:02d}09", "TD1", "TD109", "Shipment TD109 must be numeric")
    if elem(td1, 9) and elem(td1, 10) not in {"CF", "CI", "CR", "CY"}:
        add_tx(out, st02, f"TD1S{index:02d}10", "TD1", "TD110", "Shipment TD110 must be CF, CI, CR, or CY when TD109 is used")


def validate_shipment_chunk(chunk: List[List[str]], st02: str, out: List[Dict[str, Any]]) -> None:
    td1s = [seg for seg in chunk if seg and seg[0] == "TD1"]
    if not td1s:
        add_tx(out, st02, "SHIPTD100", "TD1", "", "Shipment TD1 is required")
    else:
        for idx, td1 in enumerate(td1s, start=1):
            validate_shipment_td1(td1, st02, out, idx)

    td5s = [seg for seg in chunk if seg and seg[0] == "TD5"]
    if not td5s:
        add_tx(out, st02, "SHIPTD500", "TD5", "", "Shipment TD5 is required")
    for idx, td5 in enumerate(td5s, start=1):
        if elem(td5, 2) != "2":
            add_tx(out, st02, f"SHIPTD5{idx:02d}2", "TD5", "TD502", "TD502 must be 2 (SCAC)")
        if not elem(td5, 3):
            add_tx(out, st02, f"SHIPTD5{idx:02d}3", "TD5", "TD503", "TD503 SCAC is required")

    td3s = [seg for seg in chunk if seg and seg[0] == "TD3"]
    for idx, td3 in enumerate(td3s, start=1):
        add_tx(out, st02, f"SHIPTD3{idx:02d}", "TD3", "", "TD3 is import-only and should be omitted for domestic ASNs", "Warning")
        if elem(td3, 4) and elem(td3, 4) != "B":
            add_tx(out, st02, f"SHIPTD3{idx:02d}4", "TD3", "TD304", "TD304 should be B when TD3 is used")
        if elem(td3, 5) and not is_number(elem(td3, 5)):
            add_tx(out, st02, f"SHIPTD3{idx:02d}5", "TD3", "TD305", "TD305 must be numeric when used")

    refs = [seg for seg in chunk if seg and seg[0] == "REF"]
    cn_refs = [seg for seg in refs if elem(seg, 1) == "CN"]
    if not cn_refs:
        add_tx(out, st02, "SHIPREFCN", "REF", "REF01", "Shipment REF*CN is required")
    for idx, ref in enumerate(refs, start=1):
        q = elem(ref, 1)
        if q in {"BM", "CN", "SN", "BX"} and not elem(ref, 2):
            add_tx(out, st02, f"SHIPREF{idx:02d}2", "REF", "REF02", f"REF02 is required when REF01={q}")
        if q == "BM":
            add_tx(out, st02, f"SHIPREF{idx:02d}BM", "REF", "REF01", "REF*BM is required for TL/LTL only", "Warning")

    dtms = [seg for seg in chunk if seg and seg[0] == "DTM"]
    qualifiers = {elem(seg, 1) for seg in dtms}
    for q in SHIP_DTM_QUALIFIERS:
        if q not in qualifiers:
            add_tx(out, st02, f"SHIPDTM{q}", "DTM", "DTM01", f"Shipment DTM*{q} is required")

    time_codes: Set[str] = set()
    for idx, dtm in enumerate(dtms, start=1):
        q = elem(dtm, 1)
        if q not in SHIP_DTM_QUALIFIERS:
            add_tx(out, st02, f"SHIPDTM{idx:02d}Q", "DTM", "DTM01", f"Unexpected shipment DTM qualifier {q!r}", "Warning")
        if not is_ccyymmdd(elem(dtm, 2)):
            add_tx(out, st02, f"SHIPDTM{idx:02d}2", "DTM", "DTM02", "Shipment DTM02 must be CCYYMMDD")
        has_time = bool(elem(dtm, 3))
        has_code = bool(elem(dtm, 4))
        if has_time != has_code:
            add_tx(out, st02, f"SHIPDTM{idx:02d}34", "DTM", "DTM03/DTM04", "DTM03 and DTM04 must appear together")
        if has_time and not is_time_x12(elem(dtm, 3)):
            add_tx(out, st02, f"SHIPDTM{idx:02d}3", "DTM", "DTM03", "Shipment DTM03 must be a valid X12 TM")
        if has_code:
            if elem(dtm, 4) not in {"GM", "UT"}:
                add_tx(out, st02, f"SHIPDTM{idx:02d}4", "DTM", "DTM04", "Shipment DTM04 must be GM or UT")
            time_codes.add(elem(dtm, 4))
    if len(time_codes) > 1:
        add_tx(out, st02, "SHIPDTMTC", "DTM", "DTM04", "All shipment DTM04 time codes must match")

    fobs = [seg for seg in chunk if seg and seg[0] == "FOB"]
    if len(fobs) > 1:
        add_tx(out, st02, "SHIPFOB00", "FOB", "", "Only one FOB is allowed")
    for fob in fobs:
        if not elem(fob, 1):
            add_tx(out, st02, "SHIPFOB01", "FOB", "FOB01", "FOB01 is required when FOB is used")

    validate_n1_loops(chunk, st02, out)

    v1_seen = False
    current_v1: Optional[List[str]] = None
    current_tail: List[List[str]] = []
    v1_loops: List[Tuple[List[str], List[List[str]]]] = []
    for seg in chunk:
        if not seg:
            continue
        if seg[0] == "V1":
            if current_v1 is not None:
                v1_loops.append((current_v1, current_tail))
            current_v1 = seg
            current_tail = []
            v1_seen = True
        elif current_v1 is not None:
            current_tail.append(seg)
    if current_v1 is not None:
        v1_loops.append((current_v1, current_tail))

    if v1_seen:
        add_tx(out, st02, "SHIPV100", "V1", "", "V1/R4/DTM import loop is import-only", "Warning")
    for idx, (_, tail) in enumerate(v1_loops, start=1):
        for seg in tail:
            if seg[0] == "R4":
                if elem(seg, 1) not in {"D", "F", "L"}:
                    add_tx(out, st02, f"SHIPR4{idx:02d}1", "R4", "R401", "R401 must be D, F, or L")
                if elem(seg, 2) and elem(seg, 2) != "UN":
                    add_tx(out, st02, f"SHIPR4{idx:02d}2", "R4", "R402", "R402 should be UN when used")
                if elem(seg, 2) and not elem(seg, 3):
                    add_tx(out, st02, f"SHIPR4{idx:02d}3", "R4", "R403", "R403 required when R402 is used")
            elif seg[0] == "DTM":
                if elem(seg, 1) not in V1_DTM_QUALIFIERS:
                    add_tx(out, st02, f"SHIPV1DTM{idx:02d}1", "DTM", "DTM01", "V1 DTM01 must be AAA or DFS")
                if elem(seg, 2) and not is_ccyymmdd(elem(seg, 2)):
                    add_tx(out, st02, f"SHIPV1DTM{idx:02d}2", "DTM", "DTM02", "V1 DTM02 must be CCYYMMDD")
                if elem(seg, 3) and not is_time_x12(elem(seg, 3)):
                    add_tx(out, st02, f"SHIPV1DTM{idx:02d}3", "DTM", "DTM03", "V1 DTM03 must be a valid X12 TM")


def validate_order_chunk(loop: HLLoop, body: List[List[str]], loops_by_id: Dict[str, HLLoop], st02: str, out: List[Dict[str, Any]]) -> None:
    chunk = slice_after(loop, body)
    prfs = [seg for seg in chunk if seg and seg[0] == "PRF"]
    if not prfs:
        add_tx(out, st02, "ORDPRF00", "PRF", "", "Order PRF is required")
    elif not elem(prfs[0], 1):
        add_tx(out, st02, "ORDPRF01", "PRF", "PRF01", "Order PRF01 purchase order number is required")

    parent = loops_by_id.get(loop.parent_id)
    if not parent or parent.level != "S":
        add_tx(out, st02, "ORDHLPAR", "HL", "HL02", "Order HL parent must be the Shipment HL")


def validate_tare_chunk(loop: HLLoop, body: List[List[str]], loops_by_id: Dict[str, HLLoop], st02: str, out: List[Dict[str, Any]]) -> None:
    chunk = slice_after(loop, body)
    parent = loops_by_id.get(loop.parent_id)
    if not parent or parent.level != "O":
        add_tx(out, st02, "TARHLPAR", "HL", "HL02", "Tare HL parent must be an Order HL")

    td1s = [seg for seg in chunk if seg and seg[0] == "TD1"]
    for idx, td1 in enumerate(td1s, start=1):
        if elem(td1, 1) != "CTN":
            add_tx(out, st02, f"TARTD1{idx:02d}1", "TD1", "TD101", "Tare TD101 must be CTN when TD1 is used")
        if not is_int(elem(td1, 2)):
            add_tx(out, st02, f"TARTD1{idx:02d}2", "TD1", "TD102", "Tare TD102 must be an integer carton count")
        if elem(td1, 7) and not is_number(elem(td1, 7)):
            add_tx(out, st02, f"TARTD1{idx:02d}7", "TD1", "TD107", "Tare TD107 must be numeric")

    mans = [seg for seg in chunk if seg and seg[0] == "MAN"]
    if not mans:
        add_tx(out, st02, "TARMAN00", "MAN", "", "Tare MAN is required")
    for idx, man in enumerate(mans, start=1):
        if elem(man, 1) != "GM":
            add_tx(out, st02, f"TARMAN{idx:02d}1", "MAN", "MAN01", "Tare MAN01 must be GM")
        if not elem(man, 2):
            add_tx(out, st02, f"TARMAN{idx:02d}2", "MAN", "MAN02", "Tare MAN02 SSCC is required")


def validate_package_chunk(loop: HLLoop, body: List[List[str]], loops_by_id: Dict[str, HLLoop], st02: str, out: List[Dict[str, Any]]) -> None:
    chunk = slice_after(loop, body)
    parent = loops_by_id.get(loop.parent_id)
    if not parent or parent.level not in {"O", "T"}:
        add_tx(out, st02, "PKGHLPAR", "HL", "HL02", "Package HL parent must be an Order HL or Tare HL")

    td1s = [seg for seg in chunk if seg and seg[0] == "TD1"]
    for idx, td1 in enumerate(td1s, start=1):
        if elem(td1, 1) != "CTN":
            add_tx(out, st02, f"PKGTD1{idx:02d}1", "TD1", "TD101", "Package TD101 must be CTN when TD1 is used")
        if elem(td1, 2) and not is_int(elem(td1, 2)):
            add_tx(out, st02, f"PKGTD1{idx:02d}2", "TD1", "TD102", "Package TD102 must be an integer when used")
        if elem(td1, 6) and elem(td1, 6) != "G":
            add_tx(out, st02, f"PKGTD1{idx:02d}6", "TD1", "TD106", "Package TD106 must be G when used")
        if elem(td1, 7) and not is_number(elem(td1, 7)):
            add_tx(out, st02, f"PKGTD1{idx:02d}7", "TD1", "TD107", "Package TD107 must be numeric")
        if elem(td1, 7) and elem(td1, 8) not in {"GR", "KG", "LB", "OZ"}:
            add_tx(out, st02, f"PKGTD1{idx:02d}8", "TD1", "TD108", "Package TD108 must be GR, KG, LB, or OZ when TD107 is used")

    refs = [seg for seg in chunk if seg and seg[0] == "REF"]
    cn_refs = [seg for seg in refs if elem(seg, 1) == "CN"]
    if not cn_refs:
        add_tx(out, st02, "PKGREF00", "REF", "", "Package REF*CN is required when Package HL is used")
    for idx, ref in enumerate(refs, start=1):
        if elem(ref, 1) != "CN":
            add_tx(out, st02, f"PKGREF{idx:02d}1", "REF", "REF01", "Package REF01 must be CN", "Warning")
        if not elem(ref, 2):
            add_tx(out, st02, f"PKGREF{idx:02d}2", "REF", "REF02", "Package REF02 tracking number is required")

    mans = [seg for seg in chunk if seg and seg[0] == "MAN"]
    for idx, man in enumerate(mans, start=1):
        if elem(man, 1) not in {"GM", "UC"}:
            add_tx(out, st02, f"PKGMAN{idx:02d}1", "MAN", "MAN01", "Package MAN01 must be GM or UC")
        if not elem(man, 2):
            add_tx(out, st02, f"PKGMAN{idx:02d}2", "MAN", "MAN02", "Package MAN02 is required")


def validate_item_chunk(loop: HLLoop, body: List[List[str]], loops_by_id: Dict[str, HLLoop], st02: str, out: List[Dict[str, Any]]) -> None:
    chunk = slice_after(loop, body)
    parent = loops_by_id.get(loop.parent_id)
    if not parent or parent.level not in {"P", "T"}:
        add_tx(out, st02, "ITEMHLPAR", "HL", "HL02", "Item HL parent must be a Package HL or Tare HL")

    lin = next((seg for seg in chunk if seg and seg[0] == "LIN"), None)
    sn1 = next((seg for seg in chunk if seg and seg[0] == "SN1"), None)
    if not lin:
        add_tx(out, st02, "ITEMLIN00", "LIN", "", "Item LIN is required")
    if not sn1:
        add_tx(out, st02, "ITEMSN100", "SN1", "", "Item SN1 is required")
    if not lin or not sn1:
        return

    if not elem(lin, 1) or not (1 <= len(elem(lin, 1)) <= 20):
        add_tx(out, st02, "ITEMLIN01", "LIN", "LIN01", "LIN01 assigned identification is required and must be 1-20 chars")
    pairs: List[Tuple[int, str, str]] = []
    for pos in range(2, len(lin), 2):
        qualifier = elem(lin, pos)
        value = elem(lin, pos + 1)
        if qualifier or value:
            pairs.append((pos, qualifier, value))

    if not pairs:
        add_tx(out, st02, "ITEMLIN02", "LIN", "LIN02/LIN03", "LIN must contain at least one qualifier/value pair")
    else:
        first_pos, first_qualifier, first_value = pairs[0]
        if first_pos != 2 or first_qualifier not in LIN_QUALIFIERS:
            add_tx(out, st02, "ITEMLIN02", "LIN", "LIN02", "LIN02 must be one of BP, EN, IB, UA, UK, UP, VN")
        if not first_value:
            add_tx(out, st02, "ITEMLIN03", "LIN", "LIN03", "LIN03 item ID is required")

        for pair_pos, qualifier, value in pairs[1:]:
            if not qualifier:
                add_tx(out, st02, f"ITEMLIN{pair_pos:02d}Q", "LIN", f"LIN{pair_pos:02d}", "LIN qualifier is required when a later LIN value is present")
            elif qualifier == "LT":
                if not value:
                    add_tx(out, st02, f"ITEMLIN{pair_pos + 1:02d}", "LIN", f"LIN{pair_pos + 1:02d}", "Lot number value is required when qualifier LT is used")
            else:
                add_tx(out, st02, f"ITEMLIN{pair_pos:02d}", "LIN", f"LIN{pair_pos:02d}", f"Unexpected additional LIN qualifier {qualifier!r}; PDF only defines LT as the optional second pair", "Warning")

    if elem(sn1, 1) and elem(sn1, 1) != elem(lin, 1):
        add_tx(out, st02, "ITEMSN101", "SN1", "SN101", "SN101 must match LIN01")
    if not is_number(elem(sn1, 2)):
        add_tx(out, st02, "ITEMSN102", "SN1", "SN102", "SN102 number of units shipped is required and must be numeric")
    if elem(sn1, 3) not in SN1_UOMS:
        add_tx(out, st02, "ITEMSN103", "SN1", "SN103", "SN103 must be CA or EA")

    meas = [seg for seg in chunk if seg and seg[0] == "MEA"]
    for idx, mea in enumerate(meas, start=1):
        if elem(mea, 1) and elem(mea, 1) != "SF":
            add_tx(out, st02, f"ITEMMEA{idx:02d}1", "MEA", "MEA01", "MEA01 must be SF when used")
        if elem(mea, 2) and elem(mea, 2) != "SHA":
            add_tx(out, st02, f"ITEMMEA{idx:02d}2", "MEA", "MEA02", "MEA02 must be SHA when used")
        if elem(mea, 3) and not is_number(elem(mea, 3)):
            add_tx(out, st02, f"ITEMMEA{idx:02d}3", "MEA", "MEA03", "MEA03 must be numeric")
        if elem(mea, 4) and elem(mea, 4) not in {"DA", "MO"}:
            add_tx(out, st02, f"ITEMMEA{idx:02d}4", "MEA", "MEA04-01", "MEA04 unit must be DA or MO")

    dtms = [seg for seg in chunk if seg and seg[0] == "DTM"]
    for idx, dtm in enumerate(dtms, start=1):
        if elem(dtm, 1) not in ITEM_DTM_QUALIFIERS:
            add_tx(out, st02, f"ITEMDTM{idx:02d}1", "DTM", "DTM01", "Item DTM01 must be 036 or 094")
        if elem(dtm, 2) and not is_ccyymmdd(elem(dtm, 2)):
            add_tx(out, st02, f"ITEMDTM{idx:02d}2", "DTM", "DTM02", "Item DTM02 must be CCYYMMDD")


def validate_transaction(
    tx_segments: List[List[str]],
    st02: str,
    out: List[Dict[str, Any]],
) -> None:
    st = tx_segments[0]
    se = tx_segments[-1]
    body = tx_segments[1:-1]

    if elem(st, 1) != "856":
        add_tx(out, st02, "ST001", "ST", "ST01", "ST01 must be 856")
    if not elem(st, 2) or not (4 <= len(elem(st, 2)) <= 9):
        add_tx(out, st02, "ST002", "ST", "ST02", "ST02 control number length must be 4-9")

    if not is_int(elem(se, 1)):
        add_tx(out, st02, "SE001", "SE", "SE01", "SE01 must be numeric")
    else:
        actual_count = len(tx_segments)
        if int(elem(se, 1)) != actual_count:
            add_tx(out, st02, "SE002", "SE", "SE01", f"SE01 should equal segment count {actual_count}")
    if elem(se, 2) != elem(st, 2):
        add_tx(out, st02, "SE003", "SE", "SE02", "SE02 must equal ST02")

    bsn = next((seg for seg in body if seg and seg[0] == "BSN"), None)
    if not bsn:
        add_tx(out, st02, "BSN000", "BSN", "", "BSN is required")
    else:
        if elem(bsn, 1) not in {"00", "05"}:
            add_tx(out, st02, "BSN001", "BSN", "BSN01", "BSN01 must be 00 or 05")
        if not elem(bsn, 2) or not (2 <= len(elem(bsn, 2)) <= 30):
            add_tx(out, st02, "BSN002", "BSN", "BSN02", "BSN02 shipment ID is required and must be 2-30 chars")
        if not is_ccyymmdd(elem(bsn, 3)):
            add_tx(out, st02, "BSN003", "BSN", "BSN03", "BSN03 must be CCYYMMDD")
        if not re.fullmatch(r"\d{6}", elem(bsn, 4) or ""):
            add_tx(out, st02, "BSN004", "BSN", "BSN04", "BSN04 must be HHMMSS")
        if elem(bsn, 5) and elem(bsn, 5) != "0001":
            add_tx(out, st02, "BSN005", "BSN", "BSN05", "BSN05 must be 0001 when used")

    loops = build_hl_loops(body)
    if not loops:
        add_tx(out, st02, "HL0000", "HL", "", "At least one HL loop is required")
        return

    loops_by_id: Dict[str, HLLoop] = {}
    shipment_loops = 0
    seen_ids: Set[str] = set()
    for loop in loops:
        if not loop.hl_id:
            add_tx(out, st02, "HL0001", "HL", "HL01", "HL01 is required")
            continue
        if loop.hl_id in seen_ids:
            add_tx(out, st02, "HL0002", "HL", "HL01", f"Duplicate HL01 {loop.hl_id!r}")
        seen_ids.add(loop.hl_id)
        loops_by_id[loop.hl_id] = loop

    first = loops[0]
    if first.level != "S":
        add_tx(out, st02, "HL0003", "HL", "HL03", "First HL must be Shipment (S)")
    if first.parent_id:
        add_tx(out, st02, "HL0004", "HL", "HL02", "Shipment HL must not have a parent")

    for loop in loops:
        if loop.level == "S":
            shipment_loops += 1
        if loop.level != "S" and loop.parent_id and loop.parent_id not in loops_by_id:
            add_tx(out, st02, "HL0005", "HL", "HL02", f"HL02 parent {loop.parent_id!r} must reference a prior HL01")
        if loop.level not in {"S", "O", "T", "P", "I"}:
            add_tx(out, st02, "HL0006", "HL", "HL03", f"Unsupported HL03 level {loop.level!r}")

    if shipment_loops != 1:
        add_tx(out, st02, "HL0007", "HL", "HL03", "Exactly one Shipment HL is allowed")

    for loop in loops:
        if loop.level == "S":
            validate_shipment_chunk(slice_after(loop, body), st02, out)
        elif loop.level == "O":
            validate_order_chunk(loop, body, loops_by_id, st02, out)
        elif loop.level == "T":
            validate_tare_chunk(loop, body, loops_by_id, st02, out)
        elif loop.level == "P":
            validate_package_chunk(loop, body, loops_by_id, st02, out)
        elif loop.level == "I":
            validate_item_chunk(loop, body, loops_by_id, st02, out)

    order_loops = [loop for loop in loops if loop.level == "O"]
    item_loops = [loop for loop in loops if loop.level == "I"]
    if not order_loops:
        add_tx(out, st02, "HLORD00", "HL", "HL03", "At least one Order HL is required")
    if not item_loops:
        add_tx(out, st02, "HLITEM00", "HL", "HL03", "At least one Item HL is required")

    ctts = [seg for seg in body if seg and seg[0] == "CTT"]
    if len(ctts) > 1:
        add_tx(out, st02, "CTT000", "CTT", "", "Only one CTT is allowed", "Warning")
    if ctts:
        ctt = ctts[0]
        if not is_int(elem(ctt, 1)):
            add_tx(out, st02, "CTT001", "CTT", "CTT01", "CTT01 is required and must be numeric")
        else:
            hl_count = len(loops)
            if int(elem(ctt, 1)) != hl_count:
                add_tx(out, st02, "CTT002", "CTT", "CTT01", f"CTT01 should equal HL count ({hl_count})", "Warning")

        sn_total = 0.0
        numeric_sum = True
        for seg in body:
            if seg and seg[0] == "SN1":
                if not is_number(elem(seg, 2)):
                    numeric_sum = False
                    break
                sn_total += float(elem(seg, 2))
        if not is_number(elem(ctt, 2)):
            add_tx(out, st02, "CTT003", "CTT", "CTT02", "CTT02 is required and must be numeric")
        elif numeric_sum and float(elem(ctt, 2)) != sn_total:
            add_tx(out, st02, "CTT004", "CTT", "CTT02", f"CTT02 should equal sum of SN102 ({sn_total:g})", "Warning")


def validate_amazon_856(segments: List[List[str]], gs03_allow: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if gs03_allow is None:
        gs03_allow = set(AMAZON_IDS)

    if not segments:
        add(out, SPEC, "FILE000", "FILE", "", "Empty EDI input")
        return out

    validate_envelope(segments, out, gs03_allow)

    txs = iter_transactions(segments)
    if not txs:
        add(out, SPEC, "TX0000", "ST/SE", "", "No complete ST/SE transaction set found")
        return out

    for start, end in txs:
        tx_segments = segments[start : end + 1]
        st02 = elem(tx_segments[0], 2)
        validate_transaction(tx_segments, st02, out)

    return out


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else None
    text = open(path, encoding="utf-8", errors="replace").read() if path else sys.stdin.read()
    result = validate_amazon_856(parse_edi(text))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
