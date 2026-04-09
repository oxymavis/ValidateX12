#!/usr/bin/env python3
"""
Fleet Farm 856 validator based on Fleet Farm_856.xls and the sample ASN.

The spreadsheet is a legacy .xls binary workbook that cannot be fully parsed in this
environment, but the visible workbook strings plus the provided sample ASN establish a
clear profile:
  - V4010 envelope with GS01=SH, GS08=004010
  - SOPI hierarchy: Shipment -> Order -> Pack -> Item
  - Shipment: TD1, TD5, REF, PER, DTM*011, N1*ST, N1*SF
  - Order: PRF and REF*IA
  - Pack: MAN*GM and optional N1*Z7
  - Item: LIN with UPC/Vendor item, SN1 integer qty + EA, PID*F
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
    envelope_v4010_sh,
    get_all,
    is_ccyymmdd,
    is_int,
    is_time_x12,
    parse_edi,
)

SPEC = "Fleet Farm_856.xls v4010"
GS03_ALLOW = {"4147318121"}
SHIP_REF_QUALIFIERS = {"BM", "MA", "CF", "CN", "2I"}
CONTACT_COMM_QUALIFIERS = {"EM", "TE"}
LIN_PRIMARY_QUALIFIERS = {"UP", "VN"}
LIN_EXTRA_QUALIFIERS = {"UP", "VN"}


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


def loop_body(loop: HLLoop, body: List[List[str]]) -> List[List[str]]:
    return body[loop.body_index + 1 : loop.end_index]


def validate_lin(seg: List[str], st02: str, out: List[Dict[str, Any]]) -> None:
    pairs: List[Tuple[int, str, str]] = []
    for pos in range(2, len(seg), 2):
        qualifier = elem(seg, pos)
        value = elem(seg, pos + 1)
        if qualifier or value:
            pairs.append((pos, qualifier, value))

    if not pairs:
        add_tx(out, st02, "LIN00", "LIN", "LIN02/LIN03", "LIN must contain qualifier/value pairs")
        return

    seen_primary: Set[str] = set()
    for pos, qualifier, value in pairs:
        if not qualifier:
            add_tx(out, st02, f"LIN{pos:02d}", "LIN", f"LIN{pos:02d}", "LIN qualifier is required when a value is present")
            continue
        if qualifier not in LIN_PRIMARY_QUALIFIERS and qualifier not in LIN_EXTRA_QUALIFIERS:
            add_tx(out, st02, f"LIN{pos:02d}", "LIN", f"LIN{pos:02d}", f"Unexpected LIN qualifier {qualifier!r}", "Warning")
        if not value:
            add_tx(out, st02, f"LIN{pos + 1:02d}", "LIN", f"LIN{pos + 1:02d}", f"LIN{pos + 1:02d} is required when LIN{pos:02d} is used")
        if qualifier in LIN_PRIMARY_QUALIFIERS:
            seen_primary.add(qualifier)

    if "UP" not in seen_primary and "VN" not in seen_primary:
        add_tx(out, st02, "LIN01", "LIN", "LIN02", "Fleet Farm item LIN should include UP and/or VN")


def validate_shipment_n1(chunk: List[List[str]], st02: str, out: List[Dict[str, Any]]) -> None:
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

    found_st = False
    found_sf = False
    for n1, tail in loops:
        code = elem(n1, 1)
        if code == "ST":
            found_st = True
            if elem(n1, 3) != "92":
                add_tx(out, st02, "N1ST03", "N1", "N103", "Shipment N1*ST requires N103=92")
            if not elem(n1, 4):
                add_tx(out, st02, "N1ST04", "N1", "N104", "Shipment N1*ST requires 3-5 digit store/DC identifier")
            elif not re.fullmatch(r"\d{3,5}", elem(n1, 4)):
                add_tx(out, st02, "N1ST05", "N1", "N104", "Shipment N1*ST N104 should be 3-5 digits", "Warning")
        elif code == "SF":
            found_sf = True
            n3 = next((seg for seg in tail if seg and seg[0] == "N3"), None)
            n4 = next((seg for seg in tail if seg and seg[0] == "N4"), None)
            if not n3:
                add_tx(out, st02, "N1SFN3", "N3", "", "Shipment N1*SF usually includes N3 per mapping", "Warning")
            if not n4:
                add_tx(out, st02, "N1SFN4", "N4", "", "Shipment N1*SF usually includes N4 per mapping", "Warning")
            elif elem(n4, 4) == "USA":
                add_tx(out, st02, "N404", "N4", "N404", "Use US instead of USA", "Warning")

    if not found_st:
        add_tx(out, st02, "N1REQST", "N1", "N101", "Shipment level requires N1*ST")
    if not found_sf:
        add_tx(out, st02, "N1REQSF", "N1", "N101", "Shipment level requires N1*SF")


def validate_transaction(tx_segments: List[List[str]], st02: str, out: List[Dict[str, Any]]) -> None:
    st = tx_segments[0]
    se = tx_segments[-1]
    body = tx_segments[1:-1]

    if elem(st, 1) != "856":
        add_tx(out, st02, "ST01", "ST", "ST01", "ST01 must be 856")
    if not elem(st, 2) or not (4 <= len(elem(st, 2)) <= 9):
        add_tx(out, st02, "ST02", "ST", "ST02", "ST02 control number length must be 4-9")
    if not is_int(elem(se, 1)):
        add_tx(out, st02, "SE01", "SE", "SE01", "SE01 must be numeric")
    elif int(elem(se, 1)) != len(tx_segments):
        add_tx(out, st02, "SE01C", "SE", "SE01", f"SE01 should equal segment count {len(tx_segments)}")
    if elem(se, 2) != elem(st, 2):
        add_tx(out, st02, "SE02", "SE", "SE02", "SE02 must equal ST02")

    bsn = next((s for s in body if s and s[0] == "BSN"), None)
    if not bsn:
        add_tx(out, st02, "BSN00", "BSN", "", "BSN is required")
    else:
        if elem(bsn, 1) != "00":
            add_tx(out, st02, "BSN01", "BSN", "BSN01", "BSN01 is expected to be 00", "Warning")
        if not elem(bsn, 2):
            add_tx(out, st02, "BSN02", "BSN", "BSN02", "BSN02 ASN number is required")
        if not is_ccyymmdd(elem(bsn, 3)):
            add_tx(out, st02, "BSN03", "BSN", "BSN03", "BSN03 must be CCYYMMDD")
        if not elem(bsn, 4) or not is_time_x12(elem(bsn, 4)):
            add_tx(out, st02, "BSN04", "BSN", "BSN04", "BSN04 must be a valid X12 TM")

    loops = build_hl_loops(body)
    if not loops:
        add_tx(out, st02, "HL00", "HL", "", "At least one HL loop is required")
        return

    loops_by_id: Dict[str, HLLoop] = {}
    prev_num: Optional[int] = None
    shipment_count = 0
    pack_count = 0
    item_count = 0
    for loop in loops:
        if not loop.hl_id:
            add_tx(out, st02, "HL01", "HL", "HL01", "HL01 is required")
            continue
        if loop.hl_id in loops_by_id:
            add_tx(out, st02, "HL01D", "HL", "HL01", f"Duplicate HL01 {loop.hl_id!r}")
        loops_by_id[loop.hl_id] = loop
        if not is_int(loop.hl_id):
            add_tx(out, st02, "HL01N", "HL", "HL01", "HL01 should be numeric", "Warning")
        else:
            num = int(loop.hl_id)
            if prev_num is None and num != 1:
                add_tx(out, st02, "HL01S", "HL", "HL01", "First HL01 should be 1")
            if prev_num is not None and num != prev_num + 1:
                add_tx(out, st02, "HL01SEQ", "HL", "HL01", "HL01 should increment by 1", "Warning")
            prev_num = num

        if loop.level == "S":
            shipment_count += 1
        elif loop.level == "P":
            pack_count += 1
        elif loop.level == "I":
            item_count += 1

    if loops[0].level != "S":
        add_tx(out, st02, "HLS", "HL", "HL03", "First HL must be Shipment (S)")
    if loops[0].parent_id:
        add_tx(out, st02, "HLSP", "HL", "HL02", "Shipment HL must not have a parent")
    if shipment_count != 1:
        add_tx(out, st02, "HLS1", "HL", "HL03", "Exactly one Shipment HL is allowed")
    if pack_count == 0:
        add_tx(out, st02, "HLP", "HL", "HL03", "At least one Pack HL is required")
    if item_count == 0:
        add_tx(out, st02, "HLI", "HL", "HL03", "At least one Item HL is required")

    for loop in loops:
        parent = loops_by_id.get(loop.parent_id)
        chunk = loop_body(loop, body)
        if loop.level == "S":
            td1s = [s for s in chunk if s and s[0] == "TD1"]
            td5s = [s for s in chunk if s and s[0] == "TD5"]
            refs = [s for s in chunk if s and s[0] == "REF"]
            pers = [s for s in chunk if s and s[0] == "PER"]
            dtms = [s for s in chunk if s and s[0] == "DTM"]

            if not td1s:
                add_tx(out, st02, "TD1", "TD1", "", "Shipment TD1 is required")
            for idx, seg in enumerate(td1s, start=1):
                if not elem(seg, 1):
                    add_tx(out, st02, f"TD1{idx:02d}01", "TD1", "TD101", "Shipment TD101 is required")
                if elem(seg, 1) and not re.fullmatch(r"[A-Z0-9]{3,5}", elem(seg, 1)):
                    add_tx(out, st02, f"TD1{idx:02d}01F", "TD1", "TD101", "Shipment TD101 should be a valid packaging code", "Warning")
                if elem(seg, 2) and not is_int(elem(seg, 2)):
                    add_tx(out, st02, f"TD1{idx:02d}02", "TD1", "TD102", "Shipment TD102 must be integer when used")
                if elem(seg, 6) and elem(seg, 6) != "G":
                    add_tx(out, st02, f"TD1{idx:02d}06", "TD1", "TD106", "Shipment TD106 should be G", "Warning")
                if elem(seg, 7) and not re.fullmatch(r"\d+(?:\.\d+)?", elem(seg, 7)):
                    add_tx(out, st02, f"TD1{idx:02d}07", "TD1", "TD107", "Shipment TD107 must be numeric")
                if elem(seg, 7) and elem(seg, 8) not in {"LB", "KG"}:
                    add_tx(out, st02, f"TD1{idx:02d}08", "TD1", "TD108", "Shipment TD108 must be LB or KG")

            if not td5s:
                add_tx(out, st02, "TD5", "TD5", "", "Shipment TD5 is required")
            for idx, seg in enumerate(td5s, start=1):
                if elem(seg, 2) != "2":
                    add_tx(out, st02, f"TD5{idx:02d}02", "TD5", "TD502", "TD502 must be 2 (SCAC)")
                if not elem(seg, 3):
                    add_tx(out, st02, f"TD5{idx:02d}03", "TD5", "TD503", "TD503 SCAC is required")

            if not refs:
                add_tx(out, st02, "REF", "REF", "", "Shipment REF is required")
            elif not any(elem(seg, 1) in SHIP_REF_QUALIFIERS for seg in refs):
                add_tx(out, st02, "REF01", "REF", "REF01", "One of REF BM/MA/CF/CN/2I is mandatory")

            if not pers:
                add_tx(out, st02, "PER", "PER", "", "PER*CE supplier contact is mandatory")
            else:
                per = pers[0]
                if elem(per, 1) != "CE":
                    add_tx(out, st02, "PER01", "PER", "PER01", "PER01 must be CE")
                if not elem(per, 2):
                    add_tx(out, st02, "PER02", "PER", "PER02", "Supplier contact name is required")
                if elem(per, 3) not in CONTACT_COMM_QUALIFIERS:
                    add_tx(out, st02, "PER03", "PER", "PER03", "PER03 must be EM or TE")
                if not elem(per, 4):
                    add_tx(out, st02, "PER04", "PER", "PER04", "Supplier contact email or phone is required")

            if not any(elem(seg, 1) == "011" for seg in dtms):
                add_tx(out, st02, "DTM011", "DTM", "DTM01", "DTM*011 ship date is mandatory")
            for idx, seg in enumerate(dtms, start=1):
                if elem(seg, 1) == "011" and not is_ccyymmdd(elem(seg, 2)):
                    add_tx(out, st02, f"DTM{idx:02d}02", "DTM", "DTM02", "DTM*011 date must be CCYYMMDD")

            validate_shipment_n1(chunk, st02, out)

        elif loop.level == "O":
            if not parent or parent.level != "S":
                add_tx(out, st02, "HLOP", "HL", "HL02", "Order HL parent must be Shipment HL")
            prf = next((s for s in chunk if s and s[0] == "PRF"), None)
            if not prf:
                add_tx(out, st02, "PRF", "PRF", "", "Order PRF is required")
            else:
                if not elem(prf, 1):
                    add_tx(out, st02, "PRF01", "PRF", "PRF01", "PRF01 purchase order number is required")
                if not elem(prf, 4):
                    add_tx(out, st02, "PRF04", "PRF", "PRF04", "PRF04 PO date is expected per mapping", "Warning")
            if not any(s and s[0] == "REF" and elem(s, 1) == "IA" and elem(s, 2) for s in chunk):
                add_tx(out, st02, "REFIA", "REF", "REF01", "Order REF*IA* vendor site number is mandatory")

        elif loop.level == "P":
            if not parent or parent.level != "O":
                add_tx(out, st02, "HLPP", "HL", "HL02", "Pack HL parent must be Order HL")
            mans = [s for s in chunk if s and s[0] == "MAN"]
            if not mans:
                add_tx(out, st02, "MAN", "MAN", "", "Pack MAN is required")
            else:
                gm = [s for s in mans if elem(s, 1) == "GM"]
                if not gm:
                    add_tx(out, st02, "MANGM", "MAN", "MAN01", "Pack MAN*GM is required")
                elif not elem(gm[0], 2):
                    add_tx(out, st02, "MAN02", "MAN", "MAN02", "Pack MAN02 GS1-128 label number is required")
            z7 = [s for s in chunk if s and s[0] == "N1" and elem(s, 1) == "Z7"]
            for seg in z7:
                if elem(seg, 3) != "92":
                    add_tx(out, st02, "N1Z703", "N1", "N103", "Pack N1*Z7 requires N103=92")
                if not elem(seg, 4):
                    add_tx(out, st02, "N1Z704", "N1", "N104", "Pack N1*Z7 requires mark-for location ID")

        elif loop.level == "I":
            if not parent or parent.level != "P":
                add_tx(out, st02, "HLIP", "HL", "HL02", "Item HL parent must be Pack HL")
            lin = next((s for s in chunk if s and s[0] == "LIN"), None)
            sn1 = next((s for s in chunk if s and s[0] == "SN1"), None)
            pid = next((s for s in chunk if s and s[0] == "PID"), None)
            if not lin:
                add_tx(out, st02, "LIN", "LIN", "", "Item LIN is required")
            else:
                validate_lin(lin, st02, out)
            if not sn1:
                add_tx(out, st02, "SN1", "SN1", "", "Item SN1 is required")
            else:
                if elem(sn1, 1) and lin and elem(lin, 1) and elem(sn1, 1) != elem(lin, 1):
                    add_tx(out, st02, "SN101", "SN1", "SN101", "SN101 should match LIN01", "Warning")
                if not is_int(elem(sn1, 2)):
                    add_tx(out, st02, "SN102", "SN1", "SN102", "Item SN102 must be an integer")
                if elem(sn1, 3) != "EA":
                    add_tx(out, st02, "SN103", "SN1", "SN103", "Item SN103 must be EA")
            if not pid:
                add_tx(out, st02, "PID", "PID", "", "PID*F item description is expected", "Warning")
            elif elem(pid, 1) != "F":
                add_tx(out, st02, "PID01", "PID", "PID01", "PID01 should be F", "Warning")

        else:
            add_tx(out, st02, "HL03", "HL", "HL03", f"Unsupported HL03 level {loop.level!r}")

    ctts = [s for s in body if s and s[0] == "CTT"]
    if not ctts:
        add_tx(out, st02, "CTT", "CTT", "", "CTT summary is expected", "Warning")
    else:
        ctt = ctts[0]
        if not is_int(elem(ctt, 1)):
            add_tx(out, st02, "CTT01", "CTT", "CTT01", "CTT01 must be numeric")
        else:
            expected = len(loops)
            if int(elem(ctt, 1)) != expected:
                add_tx(out, st02, "CTT01C", "CTT", "CTT01", f"CTT01 should equal HL count ({expected})", "Warning")


def validate_fleet_farm_856(segments: List[List[str]], gs03_allow: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if gs03_allow is None:
        gs03_allow = set(GS03_ALLOW)

    if not segments:
        add(out, SPEC, "FILE", "FILE", "", "Empty EDI input")
        return out

    envelope_v4010_sh(segments, SPEC, out, gs03_allowed=gs03_allow, isa12="00401", gs08="004010")

    txs = iter_transactions(segments)
    if not txs:
        add(out, SPEC, "TX000", "ST/SE", "", "No complete ST/SE transaction found")
        return out

    for start, end in txs:
        tx_segments = segments[start : end + 1]
        st02 = elem(tx_segments[0], 2)
        validate_transaction(tx_segments, st02, out)

    return out


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else None
    text = open(path, encoding="utf-8", errors="replace").read() if path else sys.stdin.read()
    print(json.dumps(validate_fleet_farm_856(parse_edi(text)), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
