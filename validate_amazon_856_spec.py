#!/usr/bin/env python3
"""
Amazon Retail X12 856 V5010 — field validation against Amazon_856.pdf (Retail ASN Spec).

Validates (non-exhaustive where PDF defers to Integration Guide):
  ISA: 01,03,06,08,11,12,13,14,15,16; IEA
  GS: 01=SH, 02–08; GE
  ST/SE: 01,02, SE01 count
  BSN: 01–05
  DTM: 011 shipped, 017 estimated (mandatory per PDF segment usage)
  Shipment HL: TD1, TD5, REF BM/CN, DTM, N1 ST/SF, HL chain
  Item: LIN/SN101 alignment, SN102/103
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any, Dict, List, Optional, Set

from edi856_common import (
    add,
    elem,
    envelope_v5010_sh,
    get_all,
    hl_validate_chain,
    is_ccyymmdd,
    is_int,
    parse_edi,
    transaction_body,
)

SPEC = "Amazon_856.pdf Retail V5010"


def validate_amazon_856(segments: List[List[str]], gs03_allow: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if gs03_allow is None:
        gs03_allow = {"AMAZON", "AMAZONCA", "AMAZONMX", "AMAZONBR", "AMAZONSG", "AMAZONAU"}

    envelope_v5010_sh(segments, SPEC, out, gs03_allowed=gs03_allow, isa12="00501", gs08="005010")

    isa = get_all(segments, "ISA")
    if isa:
        i = isa[0]
        if elem(i, 11) != "^":
            add(out, SPEC, "ISA011", "ISA", "ISA11", "ISA11 repetition separator should be ^ (per examples)", "Warning")
        if elem(i, 14) not in {"0", "1"}:
            add(out, SPEC, "ISA014", "ISA", "ISA14", "ISA14 acknowledgment 0 or 1", "Warning")
        if elem(i, 15) not in {"P", "T"}:
            add(out, SPEC, "ISA015", "ISA", "ISA15", "ISA15 P=Production T=Test", "Warning")

    body = transaction_body(segments)
    if not body:
        add(out, SPEC, "TX000", "ST", "", "No transaction body (ST/SE)")
        return out

    st = get_all(segments, "ST")
    if st and elem(st[0], 1) != "856":
        add(out, SPEC, "ST001", "ST", "ST01", "ST01 must be 856")

    bsn = next((s for s in body if s and s[0] == "BSN"), None)
    if not bsn:
        add(out, SPEC, "BSN000", "BSN", "", "BSN mandatory")
    else:
        if elem(bsn, 1) not in {"00", "05"}:
            add(out, SPEC, "BSN01", "BSN", "BSN01", "BSN01 must be 00 Original or 05 Replace")
        if not elem(bsn, 2) or not (2 <= len(elem(bsn, 2)) <= 30):
            add(out, SPEC, "BSN02", "BSN", "BSN02", "BSN02 Shipment ID required (2–30 chars)")
        if not is_ccyymmdd(elem(bsn, 3)):
            add(out, SPEC, "BSN03", "BSN", "BSN03", "BSN03 CCYYMMDD required")
        if elem(bsn, 4) and not re.fullmatch(r"\d{6}", elem(bsn, 4)):
            add(out, SPEC, "BSN04", "BSN", "BSN04", "BSN04 must be HHMMSS per Amazon (6 digits)")
        if elem(bsn, 5) and elem(bsn, 5) != "0001":
            add(out, SPEC, "BSN05", "BSN", "BSN05", "BSN05 hierarchical structure 0001 for SOTPI/SOPI (Warning)", "Warning")

    dtm_q = {elem(d, 1) for d in body if d and d[0] == "DTM"}
    if "011" not in dtm_q:
        add(out, SPEC, "DTM011", "DTM", "DTM01", "DTM*011* Shipped date mandatory")
    if "017" not in dtm_q:
        add(out, SPEC, "DTM017", "DTM", "DTM01", "DTM*017* Estimated delivery mandatory per PDF")
    for d in get_all(body, "DTM"):
        q, dt = elem(d, 1), elem(d, 2)
        if q in {"011", "017"} and dt and not is_ccyymmdd(dt):
            add(out, SPEC, "DTM02", "DTM", "DTM02", f"DTM*{q}* date invalid")

    hl_s = next((s for s in body if s and s[0] == "HL" and elem(s, 3) == "S"), None)
    if not hl_s:
        add(out, SPEC, "HL000", "HL", "HL03", "Shipment HL (HL03=S) required")
    elif elem(hl_s, 2):
        add(out, SPEC, "HL001", "HL", "HL02", "First shipment HL should have empty HL02")

    hl_validate_chain(body, SPEC, out, "HL")

    if not get_all(body, "TD1"):
        add(out, SPEC, "TD1000", "TD1", "", "At least one TD1 at shipment level required per Amazon", "Warning")
    if not get_all(body, "TD5"):
        add(out, SPEC, "TD5000", "TD5", "", "TD5 mandatory at shipment per Amazon")

    ship_refs = []
    for s in body:
        if s and s[0] == "HL" and elem(s, 3) == "O":
            break
        if s and s[0] == "REF":
            ship_refs.append(s)
    ref1 = {elem(r, 1) for r in ship_refs}
    if "CN" not in ref1:
        add(out, SPEC, "REFCN", "REF", "REF01", "REF*CN* tracking/PRO mandatory at shipment")
    for r in ship_refs:
        if elem(r, 1) == "BM" and not elem(r, 2):
            add(out, SPEC, "REFBM2", "REF", "REF02", "REF*BM* reference value required when used")

    if get_all(body, "TD3"):
        add(out, SPEC, "TD3000", "TD3", "", "TD3 only for import — domestic should omit", "Warning")

    n1_before = []
    for s in body:
        if s and s[0] == "HL" and elem(s, 3) == "O":
            break
        if s and s[0] == "N1":
            n1_before.append(s)
    if not any(elem(n, 1) == "ST" for n in n1_before):
        add(out, SPEC, "N1ST", "N1", "N101", "N1*ST* Ship-To required")
    if not any(elem(n, 1) == "SF" for n in n1_before):
        add(out, SPEC, "N1SF", "N1", "N101", "N1*SF* Ship-From required")
    for n4 in get_all(body, "N4"):
        if elem(n4, 4) == "USA":
            add(out, SPEC, "N404", "N4", "N404", "Use US not USA (ISO 3166-1 alpha-2)", "Warning")

    for i, s in enumerate(body):
        if s and s[0] == "HL" and elem(s, 3) == "I":
            end = next((j for j in range(i + 1, len(body)) if body[j] and body[j][0] == "HL"), len(body))
            chunk = body[i:end]
            lin = next((x for x in chunk if x and x[0] == "LIN"), None)
            sn1 = next((x for x in chunk if x and x[0] == "SN1"), None)
            if not lin:
                add(out, SPEC, "LIN000", "LIN", "", "LIN required in item HL")
                continue
            if not sn1:
                add(out, SPEC, "SN1000", "SN1", "", "SN1 required in item HL")
                continue
            l1 = elem(lin, 1)
            if l1 and not elem(sn1, 1):
                add(out, SPEC, "SN101", "SN1", "SN101", f"SN101 must equal LIN01 ({l1!r})")
            elif l1 and elem(sn1, 1) != l1:
                add(out, SPEC, "SN102", "SN1", "SN101", f"SN101 {elem(sn1, 1)!r} must match LIN01 {l1!r}")
            if elem(sn1, 2) and not elem(sn1, 3):
                add(out, SPEC, "SN103", "SN1", "SN103", "SN103 UoM (EA/CA) when SN102 present", "Warning")

    ctt = get_all(body, "CTT")
    if ctt:
        c = ctt[0]
        hl_cnt = len([s for s in body if s and s[0] == "HL"])
        sn_sum = 0
        for s in body:
            if s and s[0] == "SN1" and elem(s, 2) and is_int(elem(s, 2)):
                sn_sum += int(elem(s, 2))
        if elem(c, 1) and is_int(elem(c, 1)) and int(elem(c, 1)) != hl_cnt:
            add(out, SPEC, "CTT01", "CTT", "CTT01", f"CTT01 should equal HL count ({hl_cnt})", "Warning")
        if elem(c, 2) and is_int(elem(c, 2)) and int(elem(c, 2)) != sn_sum:
            add(out, SPEC, "CTT02", "CTT", "CTT02", f"CTT02 should equal sum SN102 ({sn_sum})", "Warning")

    return out


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else None
    text = open(path, encoding="utf-8", errors="replace").read() if path else sys.stdin.read()
    r = validate_amazon_856(parse_edi(text))
    print(json.dumps(r, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
