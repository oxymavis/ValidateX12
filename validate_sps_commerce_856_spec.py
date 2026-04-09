#!/usr/bin/env python3
"""
Validate X12 856 against `powermax/SPS Commerce 856 X12 Specifications.pdf`.

Scope:
- Envelope rules for ISA/GS/GE/IEA/ST/SE
- SPS 856 loop structure: Shipment/Order/Tare-Pack/Item
- Core syntax rules called out in the guide for DTM/TD1/TD5/TD3/REF/PER/FOB/N1/N2/N3/N4/MAN/LIN/SN1/PO4/PID/CTT

This guide is a generic SPS Commerce profile, so partner-specific conditional business rules are emitted as
warnings only when the PDF marks a segment as Recommended/Used rather than Must use.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any, Dict, List, Sequence, Tuple

from edi856_common import add, elem, get_all, is_ccyymmdd, is_int, parse_edi, raw_elem, transaction_body

SPEC = "SPS Commerce 856 X12 Specifications.pdf v2.018"

ALLOWED_ISA12 = {"00401", "00403", "00501"}
ALLOWED_GS08 = {"004010", "004030", "005010"}
ALLOWED_HL = {"S", "O", "T", "P", "I"}
COMMON_TD101 = {"CTN", "PLT"}
COMMON_TD105 = {"G", "N"}
COMMON_TD107 = {"LB", "KG"}
COMMON_TD109 = {"CF"}
COMMON_TD504 = {"H", "M", "P", "T"}
COMMON_TD506 = {"CL", "PR"}
COMMON_TD301 = {"TL"}
COMMON_REF_SHIPMENT = {"2I", "19", "IA", "CO", "BM", "CN", "23", "VN"}
COMMON_REF_ITEM = {"SE", "LT"}
COMMON_PER01 = {"IC", "BD", "OC"}
COMMON_PER_COMM = {"AP", "EM", "TE", "FX"}
COMMON_FOB01 = {"CC", "PP", "DF"}
COMMON_FOB02 = {"OR", "DE"}
COMMON_N101 = {"ST", "SF", "VN", "BT", "Z7"}
COMMON_N103 = {"1", "9", "91", "92"}
COMMON_MAN01 = {"GM", "CP"}
COMMON_LIN_QUAL = {"BP", "VN", "UP", "UK", "MG", "CB", "ZBP", "ZVP"}
COMMON_SN103 = {"CA", "DZ", "EA", "UN"}
COMMON_SN108 = {"IA", "BP"}
COMMON_PO403 = {"CA", "EA"}
COMMON_PO404 = {"CTN", "PLT", "25", "94"}
COMMON_PID01 = {"F"}
COMMON_PID02 = {"08"}
COMMON_PID03 = {"VI"}
COMMON_DTM_HEADING = {"001", "002", "010", "011", "067"}
COMMON_DTM_ITEM = {"001", "002", "010", "011", "067", "405", "511"}


def is_x12_time(value: str) -> bool:
    return bool(re.fullmatch(r"\d{4}|\d{6}|\d{7}|\d{8}", value or ""))


def is_decimal(value: str) -> bool:
    return bool(re.fullmatch(r"-?\d+(?:\.\d+)?", value or ""))


def add_tx(out: List[Dict[str, Any]], code: str, segment: str, element: str, message: str, st02: str, severity: str = "Error") -> None:
    suffix = f" [ST02={st02}]" if st02 else ""
    add(out, SPEC, code, segment, element, f"{message}{suffix}", severity)


def _gs08_matches_isa12(isa12: str, gs08: str) -> bool:
    return {
        "00401": gs08 == "004010",
        "00403": gs08 == "004030",
        "00501": gs08 == "005010",
    }.get(isa12, False)


def _find_segments(text: Sequence[List[str]], tag: str) -> List[List[str]]:
    return [seg for seg in text if seg and seg[0] == tag]


def envelope_sps(segments: List[List[str]], out: List[Dict[str, Any]]) -> None:
    isa = get_all(segments, "ISA")
    gs = get_all(segments, "GS")
    ge = get_all(segments, "GE")
    iea = get_all(segments, "IEA")
    st = get_all(segments, "ST")
    se = get_all(segments, "SE")

    if not isa:
        add(out, SPEC, "ENV001", "ISA", "", "ISA missing")
        return
    i = isa[0]
    if elem(i, 1) != "00":
        add(out, SPEC, "ENV002", "ISA", "ISA01", "ISA01 must be 00", "Warning")
    if elem(i, 3) != "00":
        add(out, SPEC, "ENV003", "ISA", "ISA03", "ISA03 must be 00", "Warning")
    if len(raw_elem(i, 6)) != 15:
        add(out, SPEC, "ENV004", "ISA", "ISA06", "ISA06 must be 15 characters")
    if len(raw_elem(i, 8)) != 15:
        add(out, SPEC, "ENV005", "ISA", "ISA08", "ISA08 must be 15 characters")
    if not re.fullmatch(r"\d{6}", elem(i, 9)):
        add(out, SPEC, "ENV006", "ISA", "ISA09", "ISA09 must be YYMMDD")
    if not re.fullmatch(r"\d{4}", elem(i, 10)):
        add(out, SPEC, "ENV007", "ISA", "ISA10", "ISA10 must be HHMM")
    if elem(i, 12) not in ALLOWED_ISA12:
        add(out, SPEC, "ENV008", "ISA", "ISA12", "ISA12 must be one of 00401, 00403, 00501")
    if not re.fullmatch(r"\d{9}", elem(i, 13)):
        add(out, SPEC, "ENV009", "ISA", "ISA13", "ISA13 must be 9 digits")
    if elem(i, 15) not in {"P", "T"}:
        add(out, SPEC, "ENV010", "ISA", "ISA15", "ISA15 must be P or T")
    if len(raw_elem(i, 11)) != 1:
        add(out, SPEC, "ENV011", "ISA", "ISA11", "ISA11 repetition separator must be 1 character")
    if len(raw_elem(i, 16)) != 1:
        add(out, SPEC, "ENV012", "ISA", "ISA16", "ISA16 component separator must be 1 character")

    if not gs:
        add(out, SPEC, "ENV013", "GS", "", "GS missing")
    else:
        g = gs[0]
        if elem(g, 1) != "SH":
            add(out, SPEC, "ENV014", "GS", "GS01", f"GS01 must be SH (got {elem(g, 1)!r})")
        if not (2 <= len(elem(g, 2)) <= 15):
            add(out, SPEC, "ENV015", "GS", "GS02", "GS02 must be 2-15 characters")
        if not (2 <= len(elem(g, 3)) <= 15):
            add(out, SPEC, "ENV016", "GS", "GS03", "GS03 must be 2-15 characters")
        if not is_ccyymmdd(elem(g, 4)):
            add(out, SPEC, "ENV017", "GS", "GS04", "GS04 must be CCYYMMDD")
        if not is_x12_time(elem(g, 5)):
            add(out, SPEC, "ENV018", "GS", "GS05", "GS05 must be a valid X12 TM")
        if not re.fullmatch(r"\d{1,9}", elem(g, 6)):
            add(out, SPEC, "ENV019", "GS", "GS06", "GS06 must be 1-9 digits")
        if elem(g, 7) not in {"X", "T"}:
            add(out, SPEC, "ENV020", "GS", "GS07", "GS07 must be X or T")
        if elem(g, 8) not in ALLOWED_GS08:
            add(out, SPEC, "ENV021", "GS", "GS08", "GS08 must be one of 004010, 004030, 005010")
        elif elem(i, 12) in ALLOWED_ISA12 and not _gs08_matches_isa12(elem(i, 12), elem(g, 8)):
            add(out, SPEC, "ENV022", "GS", "GS08", f"GS08 {elem(g, 8)!r} should align with ISA12 {elem(i, 12)!r}", "Warning")

    if st and se:
        if len(st) != len(se):
            add(out, SPEC, "ENV023", "ST", "", "ST/SE count mismatch")
    if gs and ge:
        if not re.fullmatch(r"\d{1,6}", elem(ge[0], 1)):
            add(out, SPEC, "ENV024", "GE", "GE01", "GE01 must be 1-6 digits")
        elif int(elem(ge[0], 1)) != len(st):
            add(out, SPEC, "ENV025", "GE", "GE01", f"GE01 must equal ST count ({len(st)})")
        if elem(ge[0], 2) != elem(gs[0], 6):
            add(out, SPEC, "ENV026", "GE", "GE02", "GE02 must equal GS06")
    if isa and iea:
        if not re.fullmatch(r"\d{1,5}", elem(iea[0], 1)):
            add(out, SPEC, "ENV027", "IEA", "IEA01", "IEA01 must be 1-5 digits")
        elif int(elem(iea[0], 1)) != len(gs):
            add(out, SPEC, "ENV028", "IEA", "IEA01", f"IEA01 must equal GS count ({len(gs)})")
        if elem(iea[0], 2) != elem(isa[0], 13):
            add(out, SPEC, "ENV029", "IEA", "IEA02", "IEA02 must equal ISA13")

    st_indexes = [i for i, seg in enumerate(segments) if seg and seg[0] == "ST"]
    se_indexes = [i for i, seg in enumerate(segments) if seg and seg[0] == "SE"]
    for idx, st_pos in enumerate(st_indexes):
        if idx >= len(se_indexes):
            break
        se_pos = se_indexes[idx]
        st_seg = segments[st_pos]
        se_seg = segments[se_pos]
        if elem(st_seg, 1) != "856":
            add(out, SPEC, "ENV030", "ST", "ST01", "ST01 must be 856")
        if not (4 <= len(elem(st_seg, 2)) <= 9):
            add(out, SPEC, "ENV031", "ST", "ST02", "ST02 must be 4-9 characters")
        if elem(st_seg, 3) and len(elem(st_seg, 3)) > 35:
            add(out, SPEC, "ENV032", "ST", "ST03", "ST03 max length is 35")
        if elem(se_seg, 2) != elem(st_seg, 2):
            add(out, SPEC, "ENV033", "SE", "SE02", "SE02 must equal ST02")
        if is_int(elem(se_seg, 1)) and int(elem(se_seg, 1)) != se_pos - st_pos + 1:
            add(out, SPEC, "ENV034", "SE", "SE01", f"SE01 must equal segment count ST..SE inclusive ({se_pos - st_pos + 1})")


def _split_hl_ranges(body: List[List[str]]) -> List[Tuple[int, int]]:
    starts = [idx for idx, seg in enumerate(body) if seg and seg[0] == "HL"]
    ranges: List[Tuple[int, int]] = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(body)
        ranges.append((start, end))
    return ranges


def _syntax_pair(out: List[Dict[str, Any]], st02: str, seg: str, e1_ref: str, e1: str, e2_ref: str, e2: str, code: str, message: str) -> None:
    if bool(e1) ^ bool(e2):
        add_tx(out, code, seg, f"{e1_ref}/{e2_ref}", message, st02)


def _syntax_cond(out: List[Dict[str, Any]], st02: str, seg: str, trigger_ref: str, trigger: str, required_ref: str, required: str, code: str, message: str) -> None:
    if trigger and not required:
        add_tx(out, code, seg, required_ref, message, st02)


def _validate_dtm(seg: List[str], out: List[Dict[str, Any]], st02: str, code_prefix: str, allowed: set[str] | None = None) -> None:
    if not elem(seg, 1):
        add_tx(out, f"{code_prefix}01", "DTM", "DTM01", "DTM01 qualifier is required", st02)
    elif allowed is not None and elem(seg, 1) not in allowed:
        add_tx(out, f"{code_prefix}02", "DTM", "DTM01", f"DTM01 {elem(seg, 1)!r} is outside the SPS common qualifier list", st02, "Warning")
    if not (elem(seg, 2) or elem(seg, 3) or elem(seg, 5)):
        add_tx(out, f"{code_prefix}03", "DTM", "DTM02/DTM03/DTM05", "At least one of DTM02, DTM03 or DTM05 is required", st02)
    if elem(seg, 2) and not is_ccyymmdd(elem(seg, 2)):
        add_tx(out, f"{code_prefix}04", "DTM", "DTM02", "DTM02 must be CCYYMMDD", st02)
    if elem(seg, 3) and not is_x12_time(elem(seg, 3)):
        add_tx(out, f"{code_prefix}05", "DTM", "DTM03", "DTM03 must be a valid X12 TM", st02)


def _validate_td1(seg: List[str], out: List[Dict[str, Any]], st02: str, code_prefix: str) -> None:
    _syntax_cond(out, st02, "TD1", "TD101", elem(seg, 1), "TD102", elem(seg, 2), f"{code_prefix}01", "If TD101 is present then TD102 is required")
    _syntax_cond(out, st02, "TD1", "TD106", elem(seg, 6), "TD107", elem(seg, 7), f"{code_prefix}02", "If TD106 is present then TD107 is required")
    _syntax_pair(out, st02, "TD1", "TD107", elem(seg, 7), "TD108", elem(seg, 8), f"{code_prefix}03", "TD107 and TD108 must appear together")
    _syntax_pair(out, st02, "TD1", "TD109", elem(seg, 9), "TD110", elem(seg, 10), f"{code_prefix}04", "TD109 and TD110 must appear together")
    if elem(seg, 1) and elem(seg, 1) not in COMMON_TD101:
        add_tx(out, f"{code_prefix}05", "TD1", "TD101", f"TD101 {elem(seg, 1)!r} is outside the SPS common packaging codes", st02, "Warning")
    if elem(seg, 5) and elem(seg, 5) not in COMMON_TD105:
        add_tx(out, f"{code_prefix}06", "TD1", "TD105", f"TD105 {elem(seg, 5)!r} is outside the SPS common weight qualifiers", st02, "Warning")
    if elem(seg, 7) and elem(seg, 7) not in COMMON_TD107:
        add_tx(out, f"{code_prefix}07", "TD1", "TD107", f"TD107 {elem(seg, 7)!r} is outside the SPS common weight UOM list", st02, "Warning")
    if elem(seg, 9) and elem(seg, 9) not in COMMON_TD109:
        add_tx(out, f"{code_prefix}08", "TD1", "TD109", f"TD109 {elem(seg, 9)!r} is outside the SPS common volume UOM list", st02, "Warning")
    for ref in (2, 6, 8, 10):
        if elem(seg, ref) and not is_decimal(elem(seg, ref)):
            add_tx(out, f"{code_prefix}09", "TD1", f"TD1{ref:02d}", f"TD1{ref:02d} must be numeric", st02)


def _validate_td5(seg: List[str], out: List[Dict[str, Any]], st02: str, code_prefix: str) -> None:
    if not (elem(seg, 2) or elem(seg, 4) or elem(seg, 5) or elem(seg, 6) or elem(seg, 12)):
        add_tx(out, f"{code_prefix}01", "TD5", "TD502/TD504/TD505/TD506/TD512", "At least one of TD502, TD504, TD505, TD506 or TD512 is required", st02)
    _syntax_cond(out, st02, "TD5", "TD502", elem(seg, 2), "TD503", elem(seg, 3), f"{code_prefix}02", "If TD502 is present then TD503 is required")
    if elem(seg, 2) and elem(seg, 2) != "2":
        add_tx(out, f"{code_prefix}03", "TD5", "TD502", "TD502 is commonly 2 in the SPS guide", st02, "Warning")
    if elem(seg, 4) and elem(seg, 4) not in COMMON_TD504:
        add_tx(out, f"{code_prefix}04", "TD5", "TD504", f"TD504 {elem(seg, 4)!r} is outside the SPS common ID code qualifiers", st02, "Warning")
    if elem(seg, 6) and elem(seg, 6) not in COMMON_TD506:
        add_tx(out, f"{code_prefix}05", "TD5", "TD506", f"TD506 {elem(seg, 6)!r} is outside the SPS common routing sequence codes", st02, "Warning")


def _validate_td3(seg: List[str], out: List[Dict[str, Any]], st02: str, code_prefix: str) -> None:
    _syntax_pair(out, st02, "TD3", "TD302", elem(seg, 2), "TD303", elem(seg, 3), f"{code_prefix}01", "TD302 and TD303 must appear together")
    if elem(seg, 1) and elem(seg, 1) not in COMMON_TD301:
        add_tx(out, f"{code_prefix}02", "TD3", "TD301", f"TD301 {elem(seg, 1)!r} is outside the SPS common equipment descriptions", st02, "Warning")


def _validate_ref(seg: List[str], out: List[Dict[str, Any]], st02: str, code_prefix: str, allowed: set[str] | None = None) -> None:
    if not elem(seg, 1):
        add_tx(out, f"{code_prefix}01", "REF", "REF01", "REF01 qualifier is required", st02)
    if not (elem(seg, 2) or elem(seg, 3)):
        add_tx(out, f"{code_prefix}02", "REF", "REF02/REF03", "At least one of REF02 or REF03 is required", st02)
    if allowed is not None and elem(seg, 1) and elem(seg, 1) not in allowed:
        add_tx(out, f"{code_prefix}03", "REF", "REF01", f"REF01 {elem(seg, 1)!r} is outside the SPS common qualifier list", st02, "Warning")


def _validate_per(seg: List[str], out: List[Dict[str, Any]], st02: str, code_prefix: str) -> None:
    if not elem(seg, 1):
        add_tx(out, f"{code_prefix}01", "PER", "PER01", "PER01 contact function code is required", st02)
    elif elem(seg, 1) not in COMMON_PER01:
        add_tx(out, f"{code_prefix}02", "PER", "PER01", f"PER01 {elem(seg, 1)!r} is outside the SPS common qualifier list", st02, "Warning")
    _syntax_pair(out, st02, "PER", "PER03", elem(seg, 3), "PER04", elem(seg, 4), f"{code_prefix}03", "PER03 and PER04 must appear together")
    _syntax_pair(out, st02, "PER", "PER05", elem(seg, 5), "PER06", elem(seg, 6), f"{code_prefix}04", "PER05 and PER06 must appear together")
    _syntax_pair(out, st02, "PER", "PER07", elem(seg, 7), "PER08", elem(seg, 8), f"{code_prefix}05", "PER07 and PER08 must appear together")
    for ref in (3, 5, 7):
        if elem(seg, ref) and elem(seg, ref) not in COMMON_PER_COMM:
            add_tx(out, f"{code_prefix}06", "PER", f"PER{ref:02d}", f"PER{ref:02d} {elem(seg, ref)!r} is outside the SPS common communication qualifiers", st02, "Warning")


def _validate_fob(seg: List[str], out: List[Dict[str, Any]], st02: str, code_prefix: str) -> None:
    if elem(seg, 1) and elem(seg, 1) not in COMMON_FOB01:
        add_tx(out, f"{code_prefix}01", "FOB", "FOB01", f"FOB01 {elem(seg, 1)!r} is outside the SPS common code list", st02, "Warning")
    if elem(seg, 2) and elem(seg, 2) not in COMMON_FOB02:
        add_tx(out, f"{code_prefix}02", "FOB", "FOB02", f"FOB02 {elem(seg, 2)!r} is outside the SPS common location qualifier list", st02, "Warning")
    _syntax_cond(out, st02, "FOB", "FOB03", elem(seg, 3), "FOB02", elem(seg, 2), f"{code_prefix}03", "If FOB03 is present then FOB02 is required")
    _syntax_pair(out, st02, "FOB", "FOB04", elem(seg, 4), "FOB05", elem(seg, 5), f"{code_prefix}04", "FOB04 and FOB05 must appear together")


def _validate_n1(seg: List[str], out: List[Dict[str, Any]], st02: str, code_prefix: str) -> None:
    if not elem(seg, 1):
        add_tx(out, f"{code_prefix}01", "N1", "N101", "N101 entity ID code is required", st02)
    elif elem(seg, 1) not in COMMON_N101:
        add_tx(out, f"{code_prefix}02", "N1", "N101", f"N101 {elem(seg, 1)!r} is outside the SPS common code list", st02, "Warning")
    if not (elem(seg, 2) or elem(seg, 3)):
        add_tx(out, f"{code_prefix}03", "N1", "N102/N103", "At least one of N102 or N103 is required", st02)
    _syntax_pair(out, st02, "N1", "N103", elem(seg, 3), "N104", elem(seg, 4), f"{code_prefix}04", "N103 and N104 must appear together")
    if elem(seg, 3) and elem(seg, 3) not in COMMON_N103:
        add_tx(out, f"{code_prefix}05", "N1", "N103", f"N103 {elem(seg, 3)!r} is outside the SPS common qualifier list", st02, "Warning")


def _validate_n2(seg: List[str], out: List[Dict[str, Any]], st02: str, code_prefix: str) -> None:
    if not elem(seg, 1):
        add_tx(out, f"{code_prefix}01", "N2", "N201", "N201 is required when N2 is used", st02)


def _validate_n3(seg: List[str], out: List[Dict[str, Any]], st02: str, code_prefix: str) -> None:
    if not elem(seg, 1):
        add_tx(out, f"{code_prefix}01", "N3", "N301", "N301 is required when N3 is used", st02)


def _validate_n4(seg: List[str], out: List[Dict[str, Any]], st02: str, code_prefix: str) -> None:
    if elem(seg, 2) and elem(seg, 7):
        add_tx(out, f"{code_prefix}01", "N4", "N402/N407", "N402 and N407 are mutually exclusive", st02)
    _syntax_cond(out, st02, "N4", "N406", elem(seg, 6), "N405", elem(seg, 5), f"{code_prefix}02", "If N406 is present then N405 is required")
    _syntax_cond(out, st02, "N4", "N407", elem(seg, 7), "N404", elem(seg, 4), f"{code_prefix}03", "If N407 is present then N404 is required")


def _validate_man(seg: List[str], out: List[Dict[str, Any]], st02: str, code_prefix: str) -> None:
    if not elem(seg, 1):
        add_tx(out, f"{code_prefix}01", "MAN", "MAN01", "MAN01 marks and numbers qualifier is required", st02)
    elif elem(seg, 1) not in COMMON_MAN01:
        add_tx(out, f"{code_prefix}02", "MAN", "MAN01", f"MAN01 {elem(seg, 1)!r} is outside the SPS common qualifier list", st02, "Warning")
    if not elem(seg, 2):
        add_tx(out, f"{code_prefix}03", "MAN", "MAN02", "MAN02 marks and numbers is required", st02)
    _syntax_pair(out, st02, "MAN", "MAN04", elem(seg, 4), "MAN05", elem(seg, 5), f"{code_prefix}04", "MAN04 and MAN05 must appear together")
    _syntax_cond(out, st02, "MAN", "MAN06", elem(seg, 6), "MAN05", elem(seg, 5), f"{code_prefix}05", "If MAN06 is present then MAN05 is required")


def _validate_lin(seg: List[str], out: List[Dict[str, Any]], st02: str, code_prefix: str) -> None:
    if elem(seg, 1) and len(elem(seg, 1)) > 20:
        add_tx(out, f"{code_prefix}01", "LIN", "LIN01", "LIN01 max length is 20", st02)
    if not elem(seg, 2):
        add_tx(out, f"{code_prefix}02", "LIN", "LIN02", "LIN02 product/service ID qualifier is required", st02)
    if not elem(seg, 3):
        add_tx(out, f"{code_prefix}03", "LIN", "LIN03", "LIN03 product/service ID is required", st02)
    for idx in range(2, min(len(seg), 20), 2):
        qual = elem(seg, idx)
        val = elem(seg, idx + 1)
        if bool(qual) ^ bool(val):
            add_tx(out, f"{code_prefix}04", "LIN", f"LIN{idx:02d}/LIN{idx + 1:02d}", "If a qualifier is present then the paired item ID is required, and vice versa", st02)
        if qual and qual not in COMMON_LIN_QUAL:
            add_tx(out, f"{code_prefix}05", "LIN", f"LIN{idx:02d}", f"LIN{idx:02d} qualifier {qual!r} is outside the SPS common qualifier list", st02, "Warning")


def _validate_sn1(seg: List[str], out: List[Dict[str, Any]], st02: str, code_prefix: str) -> None:
    if not elem(seg, 2):
        add_tx(out, f"{code_prefix}01", "SN1", "SN102", "SN102 units shipped is required", st02)
    elif not is_decimal(elem(seg, 2)):
        add_tx(out, f"{code_prefix}02", "SN1", "SN102", "SN102 must be numeric", st02)
    if not elem(seg, 3):
        add_tx(out, f"{code_prefix}03", "SN1", "SN103", "SN103 unit of measure is required", st02)
    elif elem(seg, 3) not in COMMON_SN103:
        add_tx(out, f"{code_prefix}04", "SN1", "SN103", f"SN103 {elem(seg, 3)!r} is outside the SPS common UOM list", st02, "Warning")
    _syntax_pair(out, st02, "SN1", "SN105", elem(seg, 5), "SN106", elem(seg, 6), f"{code_prefix}05", "SN105 and SN106 must appear together")
    if elem(seg, 8) and elem(seg, 8) not in COMMON_SN108:
        add_tx(out, f"{code_prefix}06", "SN1", "SN108", f"SN108 {elem(seg, 8)!r} is outside the SPS common status list", st02, "Warning")


def _validate_po4(seg: List[str], out: List[Dict[str, Any]], st02: str, code_prefix: str) -> None:
    _syntax_pair(out, st02, "PO4", "PO402", elem(seg, 2), "PO403", elem(seg, 3), f"{code_prefix}01", "PO402 and PO403 must appear together")
    _syntax_cond(out, st02, "PO4", "PO405", elem(seg, 5), "PO406", elem(seg, 6), f"{code_prefix}02", "If PO405 is present then PO406 is required")
    _syntax_pair(out, st02, "PO4", "PO406", elem(seg, 6), "PO407", elem(seg, 7), f"{code_prefix}03", "PO406 and PO407 must appear together")
    _syntax_pair(out, st02, "PO4", "PO408", elem(seg, 8), "PO409", elem(seg, 9), f"{code_prefix}04", "PO408 and PO409 must appear together")
    _syntax_cond(out, st02, "PO4", "PO410", elem(seg, 10), "PO413", elem(seg, 13), f"{code_prefix}05", "If PO410 is present then PO413 is required")
    _syntax_cond(out, st02, "PO4", "PO411", elem(seg, 11), "PO413", elem(seg, 13), f"{code_prefix}06", "If PO411 is present then PO413 is required")
    _syntax_cond(out, st02, "PO4", "PO412", elem(seg, 12), "PO413", elem(seg, 13), f"{code_prefix}07", "If PO412 is present then PO413 is required")
    if elem(seg, 13) and not (elem(seg, 10) or elem(seg, 11) or elem(seg, 12)):
        add_tx(out, f"{code_prefix}08", "PO4", "PO410/PO411/PO412/PO413", "If PO413 is present then at least one of PO410, PO411 or PO412 is required", st02)
    if elem(seg, 3) and elem(seg, 3) not in COMMON_PO403:
        add_tx(out, f"{code_prefix}09", "PO4", "PO403", f"PO403 {elem(seg, 3)!r} is outside the SPS common UOM list", st02, "Warning")
    if elem(seg, 4) and elem(seg, 4) not in COMMON_PO404:
        add_tx(out, f"{code_prefix}10", "PO4", "PO404", f"PO404 {elem(seg, 4)!r} is outside the SPS common packaging code list", st02, "Warning")
    if elem(seg, 5) and elem(seg, 5) not in COMMON_TD105:
        add_tx(out, f"{code_prefix}11", "PO4", "PO405", f"PO405 {elem(seg, 5)!r} is outside the SPS common weight qualifiers", st02, "Warning")
    if elem(seg, 7) and elem(seg, 7) not in COMMON_TD107:
        add_tx(out, f"{code_prefix}12", "PO4", "PO407", f"PO407 {elem(seg, 7)!r} is outside the SPS common weight UOM list", st02, "Warning")
    if elem(seg, 9) and elem(seg, 9) not in COMMON_TD109:
        add_tx(out, f"{code_prefix}13", "PO4", "PO409", f"PO409 {elem(seg, 9)!r} is outside the SPS common volume UOM list", st02, "Warning")


def _validate_pid(seg: List[str], out: List[Dict[str, Any]], st02: str, code_prefix: str) -> None:
    if not elem(seg, 1):
        add_tx(out, f"{code_prefix}01", "PID", "PID01", "PID01 description type is required", st02)
    elif elem(seg, 1) not in COMMON_PID01:
        add_tx(out, f"{code_prefix}02", "PID", "PID01", f"PID01 {elem(seg, 1)!r} is outside the SPS common code list", st02, "Warning")
    if elem(seg, 2) and elem(seg, 2) not in COMMON_PID02:
        add_tx(out, f"{code_prefix}03", "PID", "PID02", f"PID02 {elem(seg, 2)!r} is outside the SPS common characteristic list", st02, "Warning")
    if elem(seg, 3) and elem(seg, 3) not in COMMON_PID03:
        add_tx(out, f"{code_prefix}04", "PID", "PID03", f"PID03 {elem(seg, 3)!r} is outside the SPS common agency list", st02, "Warning")
    _syntax_cond(out, st02, "PID", "PID04", elem(seg, 4), "PID03", elem(seg, 3), f"{code_prefix}05", "If PID04 is present then PID03 is required")
    if not (elem(seg, 4) or elem(seg, 5)):
        add_tx(out, f"{code_prefix}06", "PID", "PID04/PID05", "At least one of PID04 or PID05 is required", st02)
    if elem(seg, 1) == "F" and not elem(seg, 5):
        add_tx(out, f"{code_prefix}07", "PID", "PID05", "PID05 is expected when PID01=F", st02, "Warning")


def _validate_hl_structure(body: List[List[str]], out: List[Dict[str, Any]], st02: str) -> None:
    hls = [seg for seg in body if seg and seg[0] == "HL"]
    if not hls:
        add_tx(out, "HL000", "HL", "", "At least one HL segment is required", st02)
        return

    seen: set[str] = set()
    shipment_count = 0
    parent_codes: Dict[str, str] = {}
    order_seen = False

    for index, hl in enumerate(hls, start=1):
        h01 = elem(hl, 1)
        h02 = elem(hl, 2)
        h03 = elem(hl, 3)
        if not h01:
            add_tx(out, "HL001", "HL", "HL01", "HL01 hierarchical ID is required", st02)
            continue
        if h01 in seen:
            add_tx(out, "HL002", "HL", "HL01", f"Duplicate HL01 {h01!r}", st02)
        if h01.isdigit() and int(h01) != index:
            add_tx(out, "HL003", "HL", "HL01", f"HL01 should progress top-down/left-right; expected {index}, got {h01}", st02, "Warning")
        if h02 and h02 not in seen:
            add_tx(out, "HL004", "HL", "HL02", f"HL02 parent {h02!r} must reference a prior HL01", st02)
        if not h03:
            add_tx(out, "HL005", "HL", "HL03", "HL03 level code is required", st02)
        elif h03 not in ALLOWED_HL:
            add_tx(out, "HL006", "HL", "HL03", f"Unsupported HL03 level {h03!r}", st02)
        if h03 == "S":
            shipment_count += 1
            if h02:
                add_tx(out, "HL007", "HL", "HL02", "Shipment HL must not have a parent", st02)
            if index != 1:
                add_tx(out, "HL008", "HL", "HL03", "First HL must be Shipment (S)", st02)
        elif index == 1:
            add_tx(out, "HL009", "HL", "HL03", "First HL must be Shipment (S)", st02)
        if h03 == "O":
            order_seen = True
        if h03 in {"P", "T", "I"} and not order_seen:
            add_tx(out, "HL010", "HL", "HL03", f"{h03} level cannot appear before an Order HL", st02)
        if h02 and h02 in parent_codes and h03:
            pcode = parent_codes[h02]
            allowed = {
                "S": {"O"},
                "O": {"P", "T", "I"},
                "T": {"P", "I"},
                "P": {"I"},
                "I": set(),
            }
            if pcode in allowed and h03 not in allowed[pcode]:
                add_tx(out, "HL011", "HL", "HL02/HL03", f"{h03} HL cannot be child of {pcode} HL", st02)
        if h01:
            seen.add(h01)
            if h03:
                parent_codes[h01] = h03

    if shipment_count != 1:
        add_tx(out, "HL012", "HL", "HL03", f"Exactly one Shipment HL is expected; found {shipment_count}", st02)


def validate_sps_commerce_856(segments: List[List[str]], *, require_heading_dtm: bool = False) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    envelope_sps(segments, out)

    body = transaction_body(segments)
    st = get_all(segments, "ST")
    st02 = elem(st[0], 2) if st else ""
    if not body:
        add_tx(out, "TX000", "ST", "", "No complete ST/SE transaction found", st02)
        return out

    bsn = next((seg for seg in body if seg and seg[0] == "BSN"), None)
    first_hl_idx = next((idx for idx, seg in enumerate(body) if seg and seg[0] == "HL"), None)
    heading = body[:first_hl_idx] if first_hl_idx is not None else body

    if not bsn:
        add_tx(out, "BSN000", "BSN", "", "BSN is required", st02)
    else:
        if not elem(bsn, 1):
            add_tx(out, "BSN001", "BSN", "BSN01", "BSN01 purpose code is required", st02)
        if not elem(bsn, 2) or not (2 <= len(elem(bsn, 2)) <= 30):
            add_tx(out, "BSN002", "BSN", "BSN02", "BSN02 shipment ID must be 2-30 characters", st02)
        if not is_ccyymmdd(elem(bsn, 3)):
            add_tx(out, "BSN003", "BSN", "BSN03", "BSN03 must be CCYYMMDD", st02)
        if not is_x12_time(elem(bsn, 4)):
            add_tx(out, "BSN004", "BSN", "BSN04", "BSN04 must be a valid X12 TM", st02)
        if elem(bsn, 5) and elem(bsn, 5) != "0001":
            add_tx(out, "BSN005", "BSN", "BSN05", f"BSN05 {elem(bsn, 5)!r} is outside the SPS common structure code list", st02, "Warning")

    heading_dtms = [seg for seg in heading if seg and seg[0] == "DTM"]
    for seg in heading_dtms:
        _validate_dtm(seg, out, st02, "HDTM", COMMON_DTM_HEADING)
    if require_heading_dtm and not heading_dtms:
        add_tx(out, "HDTM00", "DTM", "", "Heading DTM is recommended but missing", st02, "Warning")

    _validate_hl_structure(body, out, st02)

    for start, end in _split_hl_ranges(body):
        chunk = body[start:end]
        hl = chunk[0]
        level = elem(hl, 3)

        if level == "S":
            if not any(seg and seg[0] == "TD1" for seg in chunk[1:]):
                add_tx(out, "SHP001", "TD1", "", "Shipment TD1 is recommended", st02, "Warning")
            if not any(seg and seg[0] == "TD5" for seg in chunk[1:]):
                add_tx(out, "SHP002", "TD5", "", "Shipment TD5 is recommended", st02, "Warning")
            if not any(seg and seg[0] == "REF" for seg in chunk[1:]):
                add_tx(out, "SHP003", "REF", "", "Shipment REF is recommended", st02, "Warning")
            if not any(seg and seg[0] == "N1" for seg in chunk[1:]):
                add_tx(out, "SHP004", "N1", "", "Shipment N1 loop is recommended", st02, "Warning")
        elif level == "O":
            prf = next((seg for seg in chunk if seg and seg[0] == "PRF"), None)
            if not prf:
                add_tx(out, "ORD001", "PRF", "", "PRF is required in Order HL", st02)
            else:
                if not elem(prf, 1):
                    add_tx(out, "ORD002", "PRF", "PRF01", "PRF01 purchase order number is required", st02)
                if elem(prf, 4) and not is_ccyymmdd(elem(prf, 4)):
                    add_tx(out, "ORD003", "PRF", "PRF04", "PRF04 must be CCYYMMDD", st02)
        elif level in {"P", "T"}:
            if not any(seg and seg[0] == "MAN" for seg in chunk[1:]):
                add_tx(out, "PKG001", "MAN", "", f"{'Tare' if level == 'T' else 'Pack'} MAN is used in the SPS profile", st02, "Warning")
        elif level == "I":
            lin = next((seg for seg in chunk if seg and seg[0] == "LIN"), None)
            sn1 = next((seg for seg in chunk if seg and seg[0] == "SN1"), None)
            if not lin:
                add_tx(out, "ITM001", "LIN", "", "LIN is required in Item HL", st02)
            if not sn1:
                add_tx(out, "ITM002", "SN1", "", "SN1 is required in Item HL", st02)

        for seg in chunk[1:]:
            tag = seg[0]
            if tag == "DTM":
                allowed = COMMON_DTM_ITEM if level == "I" else None
                prefix = "IDTM" if level == "I" else "DTM"
                _validate_dtm(seg, out, st02, prefix, allowed)
            elif tag == "TD1":
                _validate_td1(seg, out, st02, "TD1")
            elif tag == "TD5":
                _validate_td5(seg, out, st02, "TD5")
            elif tag == "TD3":
                _validate_td3(seg, out, st02, "TD3")
            elif tag == "REF":
                allowed = COMMON_REF_ITEM if level == "I" else COMMON_REF_SHIPMENT
                _validate_ref(seg, out, st02, "REF", allowed)
            elif tag == "PER":
                _validate_per(seg, out, st02, "PER")
            elif tag == "FOB":
                _validate_fob(seg, out, st02, "FOB")
            elif tag == "N1":
                _validate_n1(seg, out, st02, "N1")
            elif tag == "N2":
                _validate_n2(seg, out, st02, "N2")
            elif tag == "N3":
                _validate_n3(seg, out, st02, "N3")
            elif tag == "N4":
                _validate_n4(seg, out, st02, "N4")
            elif tag == "MAN":
                _validate_man(seg, out, st02, "MAN")
            elif tag == "LIN":
                _validate_lin(seg, out, st02, "LIN")
            elif tag == "SN1":
                _validate_sn1(seg, out, st02, "SN1")
            elif tag == "PO4":
                _validate_po4(seg, out, st02, "PO4")
            elif tag == "PID":
                _validate_pid(seg, out, st02, "PID")

    ctt = next((seg for seg in body if seg and seg[0] == "CTT"), None)
    hls = [seg for seg in body if seg and seg[0] == "HL"]
    sn1_sum = 0
    for seg in body:
        if seg and seg[0] == "SN1" and elem(seg, 2) and is_decimal(elem(seg, 2)):
            sn1_sum += int(float(elem(seg, 2)))
    if ctt:
        if not elem(ctt, 1):
            add_tx(out, "CTT001", "CTT", "CTT01", "CTT01 is required when CTT is used", st02)
        elif not is_int(elem(ctt, 1)):
            add_tx(out, "CTT002", "CTT", "CTT01", "CTT01 must be an integer", st02)
        elif int(elem(ctt, 1)) != len(hls):
            add_tx(out, "CTT003", "CTT", "CTT01", f"CTT01 must equal HL count ({len(hls)})", st02, "Warning")
        if elem(ctt, 2):
            if not is_decimal(elem(ctt, 2)):
                add_tx(out, "CTT004", "CTT", "CTT02", "CTT02 must be numeric", st02)
            elif int(float(elem(ctt, 2))) != sn1_sum:
                add_tx(out, "CTT005", "CTT", "CTT02", f"CTT02 must equal sum of SN102 ({sn1_sum})", st02, "Warning")

    return out


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Validate X12 856 against SPS Commerce 856 guide")
    parser.add_argument("--require-heading-dtm", action="store_true", help="Warn when heading-level DTM is absent")
    parser.add_argument("edi_file", nargs="?", help="Path to .edi; reads stdin when omitted")
    args = parser.parse_args()

    text = open(args.edi_file, encoding="utf-8", errors="replace").read() if args.edi_file else sys.stdin.read()
    result = validate_sps_commerce_856(parse_edi(text), require_heading_dtm=args.require_heading_dtm)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
