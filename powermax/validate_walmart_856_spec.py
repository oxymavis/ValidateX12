#!/usr/bin/env python3
"""
Walmart 856 V5010 VICS — validation against Walmart-856.pdf (Goods for Resale, v3.12).

Field checks include:
  Envelope: ISA12=00501, GS01=SH, GS08=005010 (Functional Group SH)
  ST: 856, control number 4–9
  BSN: 01=00; 02 unique shipment ID 2–30; 03 date; 04 time (HHMM or HHMMSS per X12);
       05 required by Walmart: 0001 / 0002 / 0004 (SOP/I hierarchies)
  HL: parent chain; first shipment S
  CTT: if present, CTT01 = HL count; CTT02 = sum of SN102 (Walmart note)
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any, Dict, List

from edi856_common import (
    add,
    elem,
    envelope_v5010_sh,
    get_all,
    hl_validate_chain,
    is_ccyymmdd,
    is_int,
    is_time_x12,
    parse_edi,
    transaction_body,
)

SPEC = "Walmart-856.pdf V5010 VICS v3.12"


def validate_walmart_856(segments: List[List[str]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    envelope_v5010_sh(segments, SPEC, out, gs03_allowed=None, isa12="00501", gs08="005010")

    body = transaction_body(segments)
    if not body:
        add(out, SPEC, "TX000", "ST", "", "No ST/SE body")
        return out

    st = get_all(segments, "ST")
    if st:
        if elem(st[0], 1) != "856":
            add(out, SPEC, "ST01", "ST", "ST01", "ST01 must be 856")
        st2 = elem(st[0], 2)
        if not st2 or not (4 <= len(st2) <= 9):
            add(out, SPEC, "ST02", "ST", "ST02", "ST02 control number length 4–9")

    bsn = next((s for s in body if s and s[0] == "BSN"), None)
    if not bsn:
        add(out, SPEC, "BSN0", "BSN", "", "BSN mandatory")
    else:
        if elem(bsn, 1) != "00":
            add(out, SPEC, "BSN01", "BSN", "BSN01", "Walmart initial ASN uses 00 Original (see note for 824)", "Warning")
        if not elem(bsn, 2) or not (2 <= len(elem(bsn, 2)) <= 30):
            add(out, SPEC, "BSN02", "BSN", "BSN02", "BSN02 Shipment ID 2–30 chars")
        if not is_ccyymmdd(elem(bsn, 3)):
            add(out, SPEC, "BSN03", "BSN", "BSN03", "BSN03 CCYYMMDD")
        if not elem(bsn, 4) or not is_time_x12(elem(bsn, 4)):
            add(out, SPEC, "BSN04", "BSN", "BSN04", "BSN04 time TM (HHMM/HHMMSS/…)")
        b5 = elem(bsn, 5)
        if not b5:
            add(out, SPEC, "BSN05", "BSN", "BSN05", "BSN05 hierarchical structure required by Walmart")
        elif b5 not in {"0001", "0002", "0004"}:
            add(out, SPEC, "BSN05b", "BSN", "BSN05", f"BSN05 must be 0001, 0002, or 0004 (got {b5!r})")

    hl_validate_chain(body, SPEC, out, "HL")

    first_hl = next((s for s in body if s and s[0] == "HL"), None)
    if first_hl and elem(first_hl, 3) != "S":
        add(out, SPEC, "HL_S", "HL", "HL03", "First HL must be shipment S")

    ctt = get_all(body, "CTT")
    if ctt:
        c = ctt[0]
        hl_n = len([s for s in body if s and s[0] == "HL"])
        sn_sum = sum(int(elem(s, 2)) for s in body if s and s[0] == "SN1" and elem(s, 2) and is_int(elem(s, 2)))
        if elem(c, 1) and is_int(elem(c, 1)) and int(elem(c, 1)) != hl_n:
            add(out, SPEC, "CTT01", "CTT", "CTT01", f"CTT01 should equal number of HL segments ({hl_n})", "Warning")
        if elem(c, 2) and is_int(elem(c, 2)) and int(elem(c, 2)) != sn_sum:
            add(out, SPEC, "CTT02", "CTT", "CTT02", f"CTT02 should equal sum SN102 ({sn_sum})", "Warning")

    return out


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else None
    text = open(path, encoding="utf-8", errors="replace").read() if path else sys.stdin.read()
    print(json.dumps(validate_walmart_856(parse_edi(text)), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
