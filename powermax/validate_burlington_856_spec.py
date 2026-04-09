#!/usr/bin/env python3
"""
Burlington Stores 856 validator based on Burlington Stores_856_specifications_13nov17.pdf.

This validator focuses on the field and structure rules explicitly stated in the PDF.
Business-specific alternatives that cannot be inferred from the EDI alone are emitted as warnings.
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

SPEC = "Burlington Stores_856_specifications_13nov17.pdf (4010 Draft, FG=SH)"
GS03_ALLOW = {"6126750000"}
BURLINGTON_DTM_QUALIFIERS = {"011", "017", "067", "068", "AA1", "AA2"}
BURLINGTON_TIME_CODES = {"AS", "CS", "ES", "HS", "LT", "MS", "NS", "PS", "TS"}
REF_QUALIFIERS = {"AO", "BM", "CN", "CO", "DP", "IA", "SI", "VN"}
LIN02_QUALIFIERS = {"EN", "IN", "UK", "UP"}
LIN_POSITION_QUALIFIERS = {
    4: {"IT"},
    6: {"BO"},
    8: {"IZ"},
    10: {"PU"},
    12: {"BL"},
    14: {"VA"},
    16: {"CM", "VE"},
    18: {"SZ"},
}
SLN_POSITION_QUALIFIERS = {
    9: {"EN", "IN", "UK", "UP"},
    11: {"IT"},
    13: {"BO"},
    15: {"IZ"},
    17: {"PU"},
    19: {"BL"},
    21: {"VA"},
    23: {"CM", "VE"},
    25: {"SZ"},
}
N103_QUALIFIERS = {"1", "9", "91", "92", "93", "94", "UL"}


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


def validate_dtm_segment(seg: List[str], st02: str, out: List[Dict[str, Any]], code_prefix: str) -> None:
    if elem(seg, 1) not in BURLINGTON_DTM_QUALIFIERS:
        add_tx(out, st02, f"{code_prefix}01", "DTM", "DTM01", f"Unexpected DTM01 qualifier {elem(seg, 1)!r}", "Warning")
    if not is_ccyymmdd(elem(seg, 2)):
        add_tx(out, st02, f"{code_prefix}02", "DTM", "DTM02", "DTM02 must be CCYYMMDD")
    if elem(seg, 3) and not is_time_x12(elem(seg, 3)):
        add_tx(out, st02, f"{code_prefix}03", "DTM", "DTM03", "DTM03 must be a valid X12 TM")
    if elem(seg, 4) and not elem(seg, 3):
        add_tx(out, st02, f"{code_prefix}04", "DTM", "DTM04", "DTM04 requires DTM03")
    if elem(seg, 4) and elem(seg, 4) not in BURLINGTON_TIME_CODES:
        add_tx(out, st02, f"{code_prefix}05", "DTM", "DTM04", "DTM04 must be a valid Burlington time code")


def validate_n1_loops(chunk: List[List[str]], level: str, st02: str, out: List[Dict[str, Any]]) -> None:
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
    found_by = False
    found_ob = False
    found_z7 = False

    for n1, tail in loops:
        n101 = elem(n1, 1)
        n102 = elem(n1, 2)
        n103 = elem(n1, 3)
        n104 = elem(n1, 4)

        if n101 == "SF":
            found_sf = True
            if level != "S":
                add_tx(out, st02, "N1SF00", "N1", "N101", "N1*SF is expected at Shipment level", "Warning")
            if not n102 and not n103:
                add_tx(out, st02, "N1SF01", "N1", "N102/N103", "Ship From requires at least N102 or N103")
            if n103 and n103 not in N103_QUALIFIERS:
                add_tx(out, st02, "N1SF02", "N1", "N103", "Ship From N103 must be one of 1, 9, 91, 92, 93, 94, UL")
            if bool(n103) != bool(n104):
                add_tx(out, st02, "N1SF03", "N1", "N103/N104", "Ship From N103 and N104 must appear together")
            n3 = next((seg for seg in tail if seg and seg[0] == "N3"), None)
            n4 = next((seg for seg in tail if seg and seg[0] == "N4"), None)
            if not n3:
                add_tx(out, st02, "N1SF04", "N3", "", "Ship From requires N3 address")
            elif not elem(n3, 1):
                add_tx(out, st02, "N1SF05", "N3", "N301", "Ship From N301 is required")
            if not n4:
                add_tx(out, st02, "N1SF06", "N4", "", "Ship From requires N4 geographic information")

        elif n101 == "ST":
            found_st = True
            if n103 and n103 not in N103_QUALIFIERS:
                add_tx(out, st02, "N1ST01", "N1", "N103", "Ship To N103 must be one of 1, 9, 91, 92, 93, 94, UL")
            if bool(n103) != bool(n104):
                add_tx(out, st02, "N1ST02", "N1", "N103/N104", "Ship To N103 and N104 must appear together")
            if not n103:
                n3 = next((seg for seg in tail if seg and seg[0] == "N3"), None)
                n4 = next((seg for seg in tail if seg and seg[0] == "N4"), None)
                if not n3:
                    add_tx(out, st02, "N1ST03", "N3", "", "Ship To without N103/N104 should include N3")
                if not n4:
                    add_tx(out, st02, "N1ST04", "N4", "", "Ship To without N103/N104 should include N4")

        elif n101 == "BY":
            found_by = True
            if n103 and n103 != "92":
                add_tx(out, st02, "N1BY01", "N1", "N103", "Buying Party commonly uses N103=92", "Warning")
            if n103 == "92" and not n104:
                add_tx(out, st02, "N1BY02", "N1", "N104", "Buying Party N104 is required when N103=92")

        elif n101 == "OB":
            found_ob = True
            if n103 or n104:
                add_tx(out, st02, "N1OB01", "N1", "N103/N104", "Ordered By should not require N103/N104", "Warning")

        elif n101 == "Z7":
            found_z7 = True
            if n103 and n103 != "92":
                add_tx(out, st02, "N1Z701", "N1", "N103", "Mark-for Party commonly uses N103=92", "Warning")
            if n103 == "92" and not n104:
                add_tx(out, st02, "N1Z702", "N1", "N104", "Mark-for Party N104 is required when N103=92")

        n4 = next((seg for seg in tail if seg and seg[0] == "N4"), None)
        if n4 and elem(n4, 4) == "USA":
            add_tx(out, st02, "N404", "N4", "N404", "Use US instead of USA", "Warning")

    if level == "S":
        if not found_sf:
            add_tx(out, st02, "N1REQSF", "N1", "N101", "Shipment level requires N1*SF")
        if not (found_st or found_by or found_ob):
            add_tx(out, st02, "N1REQDST", "N1", "N101", "Shipment/order detail should identify ST, BY, or OB", "Warning")
    if level == "P" and found_z7:
        return


def validate_td1(seg: List[str], st02: str, out: List[Dict[str, Any]], prefix: str) -> None:
    if elem(seg, 1) and elem(seg, 1) not in {"BAG", "CTN", "SLP", "SRW"}:
        add_tx(out, st02, f"{prefix}01", "TD1", "TD101", "TD101 must be one of BAG, CTN, SLP, SRW when used", "Warning")
    if elem(seg, 1) and not is_int(elem(seg, 2)):
        add_tx(out, st02, f"{prefix}02", "TD1", "TD102", "TD102 is required and must be an integer when TD101 is used")
    if elem(seg, 6) and elem(seg, 6) != "G":
        add_tx(out, st02, f"{prefix}06", "TD1", "TD106", "TD106 must be G when used")
    if elem(seg, 6) and not is_number(elem(seg, 7)):
        add_tx(out, st02, f"{prefix}07", "TD1", "TD107", "TD107 is required and must be numeric when TD106 is used")
    if elem(seg, 7) and elem(seg, 8) not in {"KG", "LB"}:
        add_tx(out, st02, f"{prefix}08", "TD1", "TD108", "TD108 must be KG or LB when TD107 is used")


def validate_td5(seg: List[str], st02: str, out: List[Dict[str, Any]], prefix: str) -> None:
    if elem(seg, 2) and elem(seg, 2) != "2":
        add_tx(out, st02, f"{prefix}02", "TD5", "TD502", "TD502 must be 2 when Burlington uses SCAC")
    if elem(seg, 2) == "2" and not elem(seg, 3):
        add_tx(out, st02, f"{prefix}03", "TD5", "TD503", "TD503 is required when TD502=2")
    if elem(seg, 7) and not elem(seg, 8):
        add_tx(out, st02, f"{prefix}07", "TD5", "TD507/TD508", "TD508 is required when TD507 is used")


def validate_td3(seg: List[str], st02: str, out: List[Dict[str, Any]], prefix: str) -> None:
    if elem(seg, 1) != "TL":
        add_tx(out, st02, f"{prefix}01", "TD3", "TD301", "TD301 must be TL when TD3 is used")
    if elem(seg, 2) and not elem(seg, 3):
        add_tx(out, st02, f"{prefix}02", "TD3", "TD302/TD303", "TD303 is required when TD302 is used")
    if not elem(seg, 3):
        add_tx(out, st02, f"{prefix}03", "TD3", "TD303", "TD303 equipment number is required")


def validate_ref(seg: List[str], st02: str, out: List[Dict[str, Any]], prefix: str) -> None:
    if elem(seg, 1) not in REF_QUALIFIERS:
        add_tx(out, st02, f"{prefix}01", "REF", "REF01", f"Unexpected REF01 qualifier {elem(seg, 1)!r}", "Warning")
    if not elem(seg, 2):
        add_tx(out, st02, f"{prefix}02", "REF", "REF02", "REF02 is required")


def validate_lin(seg: List[str], st02: str, out: List[Dict[str, Any]]) -> None:
    if elem(seg, 1) and len(elem(seg, 1)) > 20:
        add_tx(out, st02, "LIN01", "LIN", "LIN01", "LIN01 length must be 1-20")
    if elem(seg, 2) not in LIN02_QUALIFIERS:
        add_tx(out, st02, "LIN02", "LIN", "LIN02", "LIN02 must be EN, IN, UK, or UP")
    if not elem(seg, 3):
        add_tx(out, st02, "LIN03", "LIN", "LIN03", "LIN03 item ID is required")

    for pos, allowed in LIN_POSITION_QUALIFIERS.items():
        qualifier = elem(seg, pos)
        value = elem(seg, pos + 1)
        if qualifier or value:
            if qualifier not in allowed:
                add_tx(out, st02, f"LIN{pos:02d}", "LIN", f"LIN{pos:02d}", f"LIN{pos:02d} must be one of {sorted(allowed)}")
            if not value:
                add_tx(out, st02, f"LIN{pos + 1:02d}", "LIN", f"LIN{pos + 1:02d}", f"LIN{pos + 1:02d} is required when LIN{pos:02d} is used")


def validate_sln(seg: List[str], st02: str, out: List[Dict[str, Any]], idx: int) -> None:
    if not elem(seg, 1):
        add_tx(out, st02, f"SLN{idx:02d}01", "SLN", "SLN01", "SLN01 is required")
    if elem(seg, 3) != "I":
        add_tx(out, st02, f"SLN{idx:02d}03", "SLN", "SLN03", "SLN03 must be I")
    if elem(seg, 4) and not is_int(elem(seg, 4)):
        add_tx(out, st02, f"SLN{idx:02d}04", "SLN", "SLN04", "SLN04 must be an integer when used")
    if elem(seg, 4) and not elem(seg, 5):
        add_tx(out, st02, f"SLN{idx:02d}05", "SLN", "SLN05-01", "SLN05 composite UOM is required when SLN04 is used")

    for pos, allowed in SLN_POSITION_QUALIFIERS.items():
        qualifier = elem(seg, pos)
        value = elem(seg, pos + 1)
        if qualifier or value:
            if qualifier not in allowed:
                add_tx(out, st02, f"SLN{idx:02d}{pos:02d}", "SLN", f"SLN{pos:02d}", f"SLN{pos:02d} must be one of {sorted(allowed)}")
            if not value:
                add_tx(out, st02, f"SLN{idx:02d}{pos + 1:02d}", "SLN", f"SLN{pos + 1:02d}", f"SLN{pos + 1:02d} is required when SLN{pos:02d} is used")


def validate_shipment_loop(loop: HLLoop, body: List[List[str]], st02: str, out: List[Dict[str, Any]]) -> None:
    chunk = loop_body(loop, body)
    td1s = [seg for seg in chunk if seg and seg[0] == "TD1"]
    td5s = [seg for seg in chunk if seg and seg[0] == "TD5"]
    refs = [seg for seg in chunk if seg and seg[0] == "REF"]
    n1s = [seg for seg in chunk if seg and seg[0] == "N1"]

    if not td5s:
        add_tx(out, st02, "SHIPTD5", "TD5", "", "Shipment level should include TD5")
    for idx, seg in enumerate(td1s, start=1):
        validate_td1(seg, st02, out, f"SHIPTD1{idx:02d}")
    for idx, seg in enumerate(td5s, start=1):
        validate_td5(seg, st02, out, f"SHIPTD5{idx:02d}")
    for idx, seg in enumerate([s for s in chunk if s and s[0] == "TD3"], start=1):
        validate_td3(seg, st02, out, f"SHIPTD3{idx:02d}")
    for idx, seg in enumerate(refs, start=1):
        validate_ref(seg, st02, out, f"SHIPREF{idx:02d}")

    if refs and not any(elem(seg, 1) in {"BM", "CN"} for seg in refs):
        add_tx(out, st02, "SHIPREFBM", "REF", "REF01", "Shipment REF commonly includes BM and/or CN", "Warning")
    if not n1s:
        add_tx(out, st02, "SHIPN1", "N1", "", "Shipment level should include N1 detail")
    validate_n1_loops(chunk, "S", st02, out)


def validate_order_loop(loop: HLLoop, body: List[List[str]], st02: str, out: List[Dict[str, Any]]) -> None:
    chunk = loop_body(loop, body)
    prf = next((seg for seg in chunk if seg and seg[0] == "PRF"), None)
    if not prf:
        add_tx(out, st02, "ORDPRF", "PRF", "", "Order level requires PRF")
    elif not elem(prf, 1):
        add_tx(out, st02, "ORDPRF01", "PRF", "PRF01", "PRF01 purchase order number is required")

    for idx, seg in enumerate([s for s in chunk if s and s[0] == "TD1"], start=1):
        validate_td1(seg, st02, out, f"ORDTD1{idx:02d}")
    for idx, seg in enumerate([s for s in chunk if s and s[0] == "TD5"], start=1):
        validate_td5(seg, st02, out, f"ORDTD5{idx:02d}")


def validate_pack_loop(loop: HLLoop, body: List[List[str]], st02: str, out: List[Dict[str, Any]]) -> None:
    chunk = loop_body(loop, body)
    mans = [seg for seg in chunk if seg and seg[0] == "MAN"]
    if not mans:
        add_tx(out, st02, "PKGMAN", "MAN", "", "Pack level should include MAN")
    gm_found = False
    for idx, seg in enumerate(mans, start=1):
        if elem(seg, 1) not in {"CP", "GM"}:
            add_tx(out, st02, f"PKGMAN{idx:02d}01", "MAN", "MAN01", "MAN01 must be CP or GM")
        if not elem(seg, 2):
            add_tx(out, st02, f"PKGMAN{idx:02d}02", "MAN", "MAN02", "MAN02 is required")
        if elem(seg, 1) == "GM":
            gm_found = True
    if mans and not gm_found:
        add_tx(out, st02, "PKGMANGM", "MAN", "MAN01", "Pack level should include MAN*GM", "Warning")

    validate_n1_loops(chunk, "P", st02, out)


def validate_item_loop(loop: HLLoop, body: List[List[str]], st02: str, out: List[Dict[str, Any]]) -> None:
    chunk = loop_body(loop, body)
    lin = next((seg for seg in chunk if seg and seg[0] == "LIN"), None)
    sn1 = next((seg for seg in chunk if seg and seg[0] == "SN1"), None)
    slns = [seg for seg in chunk if seg and seg[0] == "SLN"]

    if not lin:
        add_tx(out, st02, "ITEMLIN", "LIN", "", "Item level requires LIN")
    else:
        validate_lin(lin, st02, out)
    if not sn1:
        add_tx(out, st02, "ITEMSN1", "SN1", "", "Item level requires SN1")
    else:
        if elem(sn1, 1) and lin and elem(sn1, 1) != elem(lin, 1):
            add_tx(out, st02, "ITEMSN101", "SN1", "SN101", "SN101 should match LIN01", "Warning")
        if not is_int(elem(sn1, 2)):
            add_tx(out, st02, "ITEMSN102", "SN1", "SN102", "SN102 must be a whole number integer")
        if elem(sn1, 3) not in {"AS", "EA"}:
            add_tx(out, st02, "ITEMSN103", "SN1", "SN103", "SN103 must be AS or EA")
        if elem(sn1, 3) == "AS" and not slns:
            add_tx(out, st02, "ITEMSLN", "SLN", "", "SLN is required when SN103=AS")

    for idx, seg in enumerate(slns, start=1):
        validate_sln(seg, st02, out, idx)


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

    bsn = next((seg for seg in body if seg and seg[0] == "BSN"), None)
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
        if elem(bsn, 5) not in {"0001", "0002", "0004"}:
            add_tx(out, st02, "BSN05", "BSN", "BSN05", "BSN05 must be 0001, 0002, or 0004")
        elif elem(bsn, 5) != "0001":
            add_tx(out, st02, "BSN05W", "BSN", "BSN05", "Burlington prefers 0001 SOPI except DTC/GOH cases", "Warning")

    first_hl_idx = next((i for i, seg in enumerate(body) if seg and seg[0] == "HL"), None)
    if first_hl_idx is None:
        add_tx(out, st02, "HL00", "HL", "", "At least one HL is required")
        return

    heading_dtms = [seg for seg in body[:first_hl_idx] if seg and seg[0] == "DTM"]
    if not any(elem(seg, 1) == "011" for seg in heading_dtms):
        add_tx(out, st02, "DTM011", "DTM", "DTM01", "Header/shipment DTM*011 is required")
    for idx, seg in enumerate(heading_dtms, start=1):
        validate_dtm_segment(seg, st02, out, f"HDTM{idx:02d}")

    loops = build_hl_loops(body)
    loops_by_id: Dict[str, HLLoop] = {}
    shipment_loops = 0
    prev_id: Optional[int] = None
    for loop in loops:
        if not loop.hl_id:
            add_tx(out, st02, "HL01", "HL", "HL01", "HL01 is required")
            continue
        if loop.hl_id in loops_by_id:
            add_tx(out, st02, "HL01D", "HL", "HL01", f"Duplicate HL01 {loop.hl_id!r}")
        loops_by_id[loop.hl_id] = loop
        if not is_int(loop.hl_id):
            add_tx(out, st02, "HL01N", "HL", "HL01", "HL01 should be sequential numeric", "Warning")
        else:
            current = int(loop.hl_id)
            if prev_id is None and current != 1:
                add_tx(out, st02, "HL01S", "HL", "HL01", "First HL01 should be 1")
            if prev_id is not None and current != prev_id + 1:
                add_tx(out, st02, "HL01SEQ", "HL", "HL01", "HL01 should increment by 1", "Warning")
            prev_id = current

        if loop.level == "S":
            shipment_loops += 1

    if loops[0].level != "S":
        add_tx(out, st02, "HL03F", "HL", "HL03", "First HL must be Shipment (S)")
    if loops[0].parent_id:
        add_tx(out, st02, "HL02S", "HL", "HL02", "Shipment HL must not have a parent")
    if shipment_loops != 1:
        add_tx(out, st02, "HL03S", "HL", "HL03", "Exactly one Shipment HL is allowed")

    bsn05 = elem(bsn, 5) if bsn else ""
    for loop in loops:
        parent = loops_by_id.get(loop.parent_id)
        if loop.level == "O":
            if not parent or parent.level != "S":
                add_tx(out, st02, "HLO", "HL", "HL02", "Order HL parent must be Shipment HL")
            validate_order_loop(loop, body, st02, out)
        elif loop.level == "P":
            if bsn05 == "0001" and (not parent or parent.level != "O"):
                add_tx(out, st02, "HLP1", "HL", "HL02", "With BSN05=0001, Pack HL parent must be Order HL")
            elif bsn05 == "0002" and (not parent or parent.level != "I"):
                add_tx(out, st02, "HLP2", "HL", "HL02", "With BSN05=0002, Pack HL parent must be Item HL")
            elif bsn05 == "0004":
                add_tx(out, st02, "HLP4", "HL", "HL03", "BSN05=0004 normally omits Pack HL", "Warning")
            validate_pack_loop(loop, body, st02, out)
        elif loop.level == "I":
            if bsn05 == "0001" and (not parent or parent.level != "P"):
                add_tx(out, st02, "HLI1", "HL", "HL02", "With BSN05=0001, Item HL parent must be Pack HL")
            elif bsn05 in {"0002", "0004"} and (not parent or parent.level != "O"):
                add_tx(out, st02, "HLI2", "HL", "HL02", "With BSN05=0002/0004, Item HL parent must be Order HL")
            validate_item_loop(loop, body, st02, out)
        elif loop.level == "S":
            validate_shipment_loop(loop, body, st02, out)
        else:
            add_tx(out, st02, "HL03", "HL", "HL03", f"Unsupported Burlington HL03 level {loop.level!r}")

    if not any(loop.level == "O" for loop in loops):
        add_tx(out, st02, "HLO00", "HL", "HL03", "At least one Order HL is required")
    if not any(loop.level == "I" for loop in loops):
        add_tx(out, st02, "HLI00", "HL", "HL03", "At least one Item HL is required")
    if bsn05 == "0001" and not any(loop.level == "P" for loop in loops):
        add_tx(out, st02, "HLP00", "HL", "HL03", "BSN05=0001 SOPI requires Pack HL")

    ctts = [seg for seg in body if seg and seg[0] == "CTT"]
    if ctts:
        ctt = ctts[0]
        if not is_int(elem(ctt, 1)):
            add_tx(out, st02, "CTT01", "CTT", "CTT01", "CTT01 must be numeric")
        else:
            hl_count = len(loops)
            if int(elem(ctt, 1)) != hl_count:
                add_tx(out, st02, "CTT01C", "CTT", "CTT01", f"CTT01 should equal HL count ({hl_count})", "Warning")


def validate_burlington_856(segments: List[List[str]], gs03_allow: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
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
    print(json.dumps(validate_burlington_856(parse_edi(text)), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
