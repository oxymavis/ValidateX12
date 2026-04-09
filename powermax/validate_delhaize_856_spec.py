#!/usr/bin/env python3
"""
Delhaize America 856 DSD V5010 validator.

The PDF is image-heavy and not machine-readable in this environment, so this validator
implements the Delhaize DSD profile visible from the available sample ASN and the
extractable metadata:
  - V5010 envelope with GS01=SH, GS08=005010
  - Delhaize GS03 receiver code allow-list
  - SOPI hierarchy: Shipment -> Order -> Pack -> Item
  - Shipment-level PO4/TD1/TD5/REF/DTM/N1 loops used in Delhaize DSD
  - Pack-level LIN/SN1(/DTM 036)
  - Item-level LIN/SN1/PID
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
    envelope_v5010_sh,
    get_all,
    is_ccyymmdd,
    is_int,
    is_time_x12,
    parse_edi,
)

SPEC = "Delhaize_America_856_v5010_DSD.pdf (V5010 DSD profile)"
DELHAIZE_GS03: Set[str] = {"540011000"}
SHIP_DTM_QUALIFIERS = {"011", "067"}
PACK_DTM_QUALIFIERS = {"036"}
N103_ALLOWED = {"9", "91", "92", "93", "94", "UL"}
REF_ALLOWED = {"BM", "CN", "IA", "VN", "23"}
LIN_ALLOWED = {"UA", "UP", "UK", "EN", "VN"}


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


def loop_body(loop: HLLoop, body: List[List[str]]) -> List[List[str]]:
    return body[loop.body_index + 1 : loop.end_index]


def validate_lin(seg: List[str], st02: str, out: List[Dict[str, Any]], prefix: str) -> None:
    if elem(seg, 1) and len(elem(seg, 1)) > 20:
        add_tx(out, st02, f"{prefix}01", "LIN", "LIN01", "LIN01 length must be 1-20")
    if elem(seg, 2) not in LIN_ALLOWED:
        add_tx(out, st02, f"{prefix}02", "LIN", "LIN02", "LIN02 must be one of UA, UP, UK, EN, VN")
    if not elem(seg, 3):
        add_tx(out, st02, f"{prefix}03", "LIN", "LIN03", "LIN03 item identifier is required")


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

    found_sf = False
    found_st = False
    for n1, tail in loops:
        code = elem(n1, 1)
        n103 = elem(n1, 3)
        n104 = elem(n1, 4)
        if code == "SF":
            found_sf = True
            if n103 and n103 not in N103_ALLOWED:
                add_tx(out, st02, "N1SF03", "N1", "N103", "Ship From N103 must be one of 9, 91, 92, 93, 94, UL")
            if bool(n103) != bool(n104):
                add_tx(out, st02, "N1SF34", "N1", "N103/N104", "Ship From N103 and N104 must appear together")
            n3 = next((x for x in tail if x and x[0] == "N3"), None)
            n4 = next((x for x in tail if x and x[0] == "N4"), None)
            if not n3:
                add_tx(out, st02, "N1SFN3", "N3", "", "Ship From N3 is required")
            elif not elem(n3, 1):
                add_tx(out, st02, "N1SFN301", "N3", "N301", "Ship From N301 is required")
            if not n4:
                add_tx(out, st02, "N1SFN4", "N4", "", "Ship From N4 is required")
            else:
                if not elem(n4, 1):
                    add_tx(out, st02, "N1SFN401", "N4", "N401", "Ship From city is required")
                if not elem(n4, 2):
                    add_tx(out, st02, "N1SFN402", "N4", "N402", "Ship From state is required")
                if not elem(n4, 3):
                    add_tx(out, st02, "N1SFN403", "N4", "N403", "Ship From postal code is required")
        elif code == "ST":
            found_st = True
            if n103 and n103 not in N103_ALLOWED:
                add_tx(out, st02, "N1ST03", "N1", "N103", "Ship To N103 must be one of 9, 91, 92, 93, 94, UL")
            if bool(n103) != bool(n104):
                add_tx(out, st02, "N1ST34", "N1", "N103/N104", "Ship To N103 and N104 must appear together")
            n3 = next((x for x in tail if x and x[0] == "N3"), None)
            n4 = next((x for x in tail if x and x[0] == "N4"), None)
            if not n3:
                add_tx(out, st02, "N1STN3", "N3", "", "Ship To N3 is required")
            if not n4:
                add_tx(out, st02, "N1STN4", "N4", "", "Ship To N4 is required")
            elif elem(n4, 4) == "USA":
                add_tx(out, st02, "N404", "N4", "N404", "Use US instead of USA", "Warning")

    if not found_sf:
        add_tx(out, st02, "N1REQSF", "N1", "N101", "Shipment level requires N1*SF")
    if not found_st:
        add_tx(out, st02, "N1REQST", "N1", "N101", "Shipment level requires N1*ST")


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
        if elem(bsn, 1) not in {"00", "05"}:
            add_tx(out, st02, "BSN01", "BSN", "BSN01", "BSN01 must be 00 or 05")
        if not elem(bsn, 2) or not (2 <= len(elem(bsn, 2)) <= 30):
            add_tx(out, st02, "BSN02", "BSN", "BSN02", "BSN02 shipment ID is required and must be 2-30 chars")
        if not is_ccyymmdd(elem(bsn, 3)):
            add_tx(out, st02, "BSN03", "BSN", "BSN03", "BSN03 must be CCYYMMDD")
        if not elem(bsn, 4) or not is_time_x12(elem(bsn, 4)):
            add_tx(out, st02, "BSN04", "BSN", "BSN04", "BSN04 must be a valid X12 TM")
        if elem(bsn, 5) and elem(bsn, 5) != "0001":
            add_tx(out, st02, "BSN05", "BSN", "BSN05", "DSD profile expects BSN05=0001 (SOPI)", "Warning")

    loops = build_hl_loops(body)
    if not loops:
        add_tx(out, st02, "HL00", "HL", "", "At least one HL loop is required")
        return

    loops_by_id: Dict[str, HLLoop] = {}
    shipment_count = 0
    prev_num: Optional[int] = None
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

    first = loops[0]
    if first.level != "S":
        add_tx(out, st02, "HLS", "HL", "HL03", "First HL must be Shipment (S)")
    if first.parent_id:
        add_tx(out, st02, "HLSP", "HL", "HL02", "Shipment HL must not have a parent")
    if shipment_count != 1:
        add_tx(out, st02, "HLS1", "HL", "HL03", "Exactly one Shipment HL is allowed")

    shipment_loops = [loop for loop in loops if loop.level == "S"]
    order_loops = [loop for loop in loops if loop.level == "O"]
    pack_loops = [loop for loop in loops if loop.level == "P"]
    item_loops = [loop for loop in loops if loop.level == "I"]
    tare_loops = [loop for loop in loops if loop.level == "T"]
    if tare_loops:
        add_tx(out, st02, "HLT", "HL", "HL03", "Delhaize DSD sample/profile does not use Tare HL", "Warning")
    if not order_loops:
        add_tx(out, st02, "HLO", "HL", "HL03", "At least one Order HL is required")
    if not pack_loops:
        add_tx(out, st02, "HLP", "HL", "HL03", "At least one Pack HL is required")
    if not item_loops:
        add_tx(out, st02, "HLI", "HL", "HL03", "At least one Item HL is required")

    for loop in loops:
        parent = loops_by_id.get(loop.parent_id)
        chunk = loop_body(loop, body)
        if loop.level == "S":
            po4s = [s for s in chunk if s and s[0] == "PO4"]
            td1s = [s for s in chunk if s and s[0] == "TD1"]
            td5s = [s for s in chunk if s and s[0] == "TD5"]
            refs = [s for s in chunk if s and s[0] == "REF"]
            dtms = [s for s in chunk if s and s[0] == "DTM"]

            if po4s:
                for idx, seg in enumerate(po4s, start=1):
                    if elem(seg, 9) and elem(seg, 9) not in {"CF"}:
                        add_tx(out, st02, f"PO4{idx:02d}09", "PO4", "PO409", "Shipment PO4 unit of measure is typically CF", "Warning")
                if any(elem(seg, 9) == "CF" and elem(seg, 8) and not is_number(elem(seg, 8)) for seg in po4s):
                    add_tx(out, st02, "PO408", "PO4", "PO408", "PO408 must be numeric when PO409 is used")
            else:
                add_tx(out, st02, "PO4", "PO4", "", "Shipment PO4 is expected in Delhaize DSD sample/profile", "Warning")

            if not td1s:
                add_tx(out, st02, "TD1", "TD1", "", "Shipment TD1 is required")
            for idx, seg in enumerate(td1s, start=1):
                if elem(seg, 1) not in {"CAS", "PLT", "CTN"}:
                    add_tx(out, st02, f"TD1{idx:02d}01", "TD1", "TD101", "Shipment TD101 should be CAS, PLT, or CTN", "Warning")
                if not is_int(elem(seg, 2)):
                    add_tx(out, st02, f"TD1{idx:02d}02", "TD1", "TD102", "Shipment TD102 must be an integer")
                if elem(seg, 6) and elem(seg, 6) != "G":
                    add_tx(out, st02, f"TD1{idx:02d}06", "TD1", "TD106", "Shipment TD106 should be G")
                if elem(seg, 7) and not is_number(elem(seg, 7)):
                    add_tx(out, st02, f"TD1{idx:02d}07", "TD1", "TD107", "Shipment TD107 must be numeric")
                if elem(seg, 7) and elem(seg, 8) not in {"LB", "KG"}:
                    add_tx(out, st02, f"TD1{idx:02d}08", "TD1", "TD108", "Shipment TD108 must be LB or KG")

            if not td5s:
                add_tx(out, st02, "TD5", "TD5", "", "Shipment TD5 is required")
            for idx, seg in enumerate(td5s, start=1):
                if elem(seg, 1) and elem(seg, 1) not in {"Z"}:
                    add_tx(out, st02, f"TD5{idx:02d}01", "TD5", "TD501", "Shipment TD501 is typically Z in the sample profile", "Warning")
                if elem(seg, 2) and elem(seg, 2) != "9":
                    add_tx(out, st02, f"TD5{idx:02d}02", "TD5", "TD502", "Shipment TD502 is typically 9 in the sample profile", "Warning")
                if not elem(seg, 3):
                    add_tx(out, st02, f"TD5{idx:02d}03", "TD5", "TD503", "Shipment TD503 carrier code is required")
                if elem(seg, 4) and elem(seg, 4) not in {"M"}:
                    add_tx(out, st02, f"TD5{idx:02d}04", "TD5", "TD504", "Shipment TD504 is typically M in the sample profile", "Warning")

            if not refs:
                add_tx(out, st02, "REF", "REF", "", "Shipment REF is expected")
            elif not any(elem(seg, 1) == "BM" for seg in refs):
                add_tx(out, st02, "REFBM", "REF", "REF01", "Shipment REF*BM is required")
            for idx, seg in enumerate(refs, start=1):
                if elem(seg, 1) not in REF_ALLOWED:
                    add_tx(out, st02, f"REF{idx:02d}01", "REF", "REF01", f"Unexpected REF01 qualifier {elem(seg, 1)!r}", "Warning")
                if not elem(seg, 2):
                    add_tx(out, st02, f"REF{idx:02d}02", "REF", "REF02", "Shipment REF02 is required")

            if not dtms:
                add_tx(out, st02, "DTM", "DTM", "", "Shipment DTM is required")
            elif not any(elem(seg, 1) in SHIP_DTM_QUALIFIERS for seg in dtms):
                add_tx(out, st02, "DTM01", "DTM", "DTM01", "Shipment DTM should include qualifier 011 or 067")
            for idx, seg in enumerate(dtms, start=1):
                if elem(seg, 1) not in SHIP_DTM_QUALIFIERS:
                    add_tx(out, st02, f"DTM{idx:02d}01", "DTM", "DTM01", f"Unexpected shipment DTM01 qualifier {elem(seg, 1)!r}", "Warning")
                if not is_ccyymmdd(elem(seg, 2)):
                    add_tx(out, st02, f"DTM{idx:02d}02", "DTM", "DTM02", "Shipment DTM02 must be CCYYMMDD")

            validate_shipment_n1(chunk, st02, out)

        elif loop.level == "O":
            if not parent or parent.level != "S":
                add_tx(out, st02, "HLOP", "HL", "HL02", "Order HL parent must be Shipment HL")
            prf = next((s for s in chunk if s and s[0] == "PRF"), None)
            if not prf:
                add_tx(out, st02, "PRF", "PRF", "", "Order PRF is required")
            elif not elem(prf, 1):
                add_tx(out, st02, "PRF01", "PRF", "PRF01", "PRF01 purchase order number is required")

        elif loop.level == "P":
            if not parent or parent.level != "O":
                add_tx(out, st02, "HLPP", "HL", "HL02", "Pack HL parent must be Order HL")
            lin = next((s for s in chunk if s and s[0] == "LIN"), None)
            sn1 = next((s for s in chunk if s and s[0] == "SN1"), None)
            if not lin:
                add_tx(out, st02, "PLIN", "LIN", "", "Pack level LIN is required")
            else:
                validate_lin(lin, st02, out, "PLIN")
            if not sn1:
                add_tx(out, st02, "PSN1", "SN1", "", "Pack level SN1 is required")
            else:
                if elem(sn1, 1) and lin and elem(lin, 1) and elem(sn1, 1) != elem(lin, 1):
                    add_tx(out, st02, "PSN101", "SN1", "SN101", "Pack SN101 should match LIN01", "Warning")
                if not is_int(elem(sn1, 2)):
                    add_tx(out, st02, "PSN102", "SN1", "SN102", "Pack SN102 must be an integer")
                if elem(sn1, 3) not in {"CA"}:
                    add_tx(out, st02, "PSN103", "SN1", "SN103", "Pack SN103 must be CA")
            for idx, seg in enumerate([s for s in chunk if s and s[0] == "DTM"], start=1):
                if elem(seg, 1) not in PACK_DTM_QUALIFIERS:
                    add_tx(out, st02, f"PDTM{idx:02d}01", "DTM", "DTM01", "Pack DTM01 should be 036", "Warning")
                if not is_ccyymmdd(elem(seg, 2)):
                    add_tx(out, st02, f"PDTM{idx:02d}02", "DTM", "DTM02", "Pack DTM02 must be CCYYMMDD")

        elif loop.level == "I":
            if not parent or parent.level != "P":
                add_tx(out, st02, "HLIP", "HL", "HL02", "Item HL parent must be Pack HL")
            lin = next((s for s in chunk if s and s[0] == "LIN"), None)
            sn1 = next((s for s in chunk if s and s[0] == "SN1"), None)
            pid = next((s for s in chunk if s and s[0] == "PID"), None)
            if not lin:
                add_tx(out, st02, "ILIN", "LIN", "", "Item level LIN is required")
            else:
                validate_lin(lin, st02, out, "ILIN")
            if not sn1:
                add_tx(out, st02, "ISN1", "SN1", "", "Item level SN1 is required")
            else:
                if elem(sn1, 1) and lin and elem(lin, 1) and elem(sn1, 1) != elem(lin, 1):
                    add_tx(out, st02, "ISN101", "SN1", "SN101", "Item SN101 should match LIN01", "Warning")
                if not is_int(elem(sn1, 2)):
                    add_tx(out, st02, "ISN102", "SN1", "SN102", "Item SN102 must be an integer")
                if elem(sn1, 3) not in {"EA"}:
                    add_tx(out, st02, "ISN103", "SN1", "SN103", "Item SN103 must be EA")
            if not pid:
                add_tx(out, st02, "PID", "PID", "", "Item PID is expected in Delhaize sample/profile", "Warning")
            elif elem(pid, 1) and elem(pid, 1) != "F":
                add_tx(out, st02, "PID01", "PID", "PID01", "PID01 should be F when PID is used")

        else:
            add_tx(out, st02, "HL03", "HL", "HL03", f"Unsupported HL03 level {loop.level!r}")

    ctts = [s for s in body if s and s[0] == "CTT"]
    if ctts:
        ctt = ctts[0]
        if not is_int(elem(ctt, 1)):
            add_tx(out, st02, "CTT01", "CTT", "CTT01", "CTT01 must be numeric")
        else:
            expected = len(loops)
            if int(elem(ctt, 1)) != expected:
                add_tx(out, st02, "CTT01C", "CTT", "CTT01", f"CTT01 should equal HL count ({expected})", "Warning")
        if elem(ctt, 2):
            sn_sum = 0
            valid = True
            for seg in body:
                if seg and seg[0] == "SN1":
                    if not is_int(elem(seg, 2)):
                        valid = False
                        break
                    sn_sum += int(elem(seg, 2))
            if valid and is_int(elem(ctt, 2)) and int(elem(ctt, 2)) != sn_sum:
                add_tx(out, st02, "CTT02C", "CTT", "CTT02", f"CTT02 should equal SN102 sum ({sn_sum})", "Warning")


def validate_delhaize_856(segments: List[List[str]], gs03_allow: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if gs03_allow is None:
        gs03_allow = DELHAIZE_GS03

    if not segments:
        add(out, SPEC, "FILE", "FILE", "", "Empty EDI input")
        return out

    envelope_v5010_sh(segments, SPEC, out, gs03_allowed=gs03_allow, isa12="00501", gs08="005010")

    isa = get_all(segments, "ISA")
    if isa:
        i = isa[0]
        if elem(i, 7) != "07":
            add(out, SPEC, "ISA07", "ISA", "ISA07", "ISA07 is typically 07 for Delhaize sample/profile", "Warning")
        if elem(i, 15) not in {"P", "T"}:
            add(out, SPEC, "ISA15", "ISA", "ISA15", "ISA15 must be P or T")

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
    print(json.dumps(validate_delhaize_856(parse_edi(text)), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
