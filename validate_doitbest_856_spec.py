#!/usr/bin/env python3
"""
Do it Best Corp 856 V4010 — validation against Do it Best Corp_856.pdf (856_V4010_Advance_Ship_Notice).

Minimum segment path (PDF): BSN; HL*1**S; TD1; TD5; REF*BM; REF*CN; DTM*011*; DTM*067/017 (delivery, cond. on FOB);
  N1*ST**92*; N1*SF* + N3 + N4; HL*O; PRF; HL*I; LIN; SN1; CTT.

Hierarchy in minimum table: Shipment → Order → Item (no Pack in minimum row — multi-level may use HL P per X12).

Field-level rules from PDF tables:
  BSN01: 00 or 14; BSN02–04; HL01–03; TD1/TD5 elements; REF BM/CN; DTM 011 + 067/017;
  N1 ST 92 + ID; N1 SF + address; PRF01; LIN02 IN/CB + LIN03 6-digit SKU; SN102/103/108 IA; CTT.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any, Dict, List, Optional, Set

from edi856_common import (
    add,
    elem,
    envelope_v4010_sh,
    get_all,
    hl_validate_chain,
    is_ccyymmdd,
    is_int,
    parse_edi,
    transaction_body,
)

SPEC = "Do it Best Corp_856.pdf V4010"


def validate_doitbest_856(segments: List[List[str]], gs03_allow: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    envelope_v4010_sh(segments, SPEC, out, gs03_allowed=gs03_allow, isa12="00401", gs08="004010")

    body = transaction_body(segments)
    if not body:
        add(out, SPEC, "TX000", "ST", "", "No ST/SE body")
        return out

    bsn = next((s for s in body if s and s[0] == "BSN"), None)
    if not bsn:
        add(out, SPEC, "BSN0", "BSN", "", "BSN mandatory")
    else:
        if elem(bsn, 1) not in {"00", "14"}:
            add(out, SPEC, "BSN01", "BSN", "BSN01", "BSN01 must be 00 Original or 14 Advance notice per PDF", "Warning")
        if not elem(bsn, 2):
            add(out, SPEC, "BSN02", "BSN", "BSN02", "BSN02 Shipment ID mandatory")
        if not is_ccyymmdd(elem(bsn, 3)):
            add(out, SPEC, "BSN03", "BSN", "BSN03", "BSN03 ASN date CCYYMMDD")
        if not elem(bsn, 4) or not re.fullmatch(r"\d{4}", elem(bsn, 4)):
            add(out, SPEC, "BSN04", "BSN", "BSN04", "BSN04 HHMM per PDF", "Warning")

    first_hl = next((s for s in body if s and s[0] == "HL"), None)
    if first_hl:
        if elem(first_hl, 1) != "1":
            add(out, SPEC, "HL01s", "HL", "HL01", "First shipment HL often HL01=1 per examples", "Warning")
        if elem(first_hl, 3) != "S":
            add(out, SPEC, "HL03s", "HL", "HL03", "Shipment HL03=S")

    td1 = next((s for s in body if s and s[0] == "TD1"), None)
    if td1:
        if elem(td1, 6) and elem(td1, 6) != "G":
            add(out, SPEC, "TD106", "TD1", "TD106", "TD106 weight qualifier G=Gross per PDF", "Warning")
        if elem(td1, 8) and elem(td1, 8) != "LB":
            add(out, SPEC, "TD108", "TD1", "TD108", "TD108 LB per PDF")

    td5 = next((s for s in body if s and s[0] == "TD5"), None)
    if td5:
        if elem(td5, 2) != "2":
            add(out, SPEC, "TD502", "TD5", "TD502", "TD502=2 SCAC")
        if not elem(td5, 3):
            add(out, SPEC, "TD503", "TD5", "TD503", "TD503 SCAC mandatory")
        if not elem(td5, 4):
            add(out, SPEC, "TD504", "TD5", "TD504", "TD504 transport method (L/M/U/…) mandatory")
        if not elem(td5, 5):
            add(out, SPEC, "TD505", "TD5", "TD505", "TD505 carrier name mandatory")

    bm = next((r for r in get_all(body, "REF") if elem(r, 1) == "BM"), None)
    if not bm:
        add(out, SPEC, "REFBM", "REF", "REF01", "REF*BM* BOL mandatory (RSC; conditional DS)")
    elif not elem(bm, 2):
        add(out, SPEC, "REFBM2", "REF", "REF02", "REF*BM*02 BOL number")

    cn = next((r for r in get_all(body, "REF") if elem(r, 1) == "CN"), None)
    if not cn:
        add(out, SPEC, "REFCN", "REF", "REF01", "REF*CN* carrier reference mandatory")
    elif not elem(cn, 2):
        add(out, SPEC, "REFCN2", "REF", "REF02", "REF*CN*02 value")

    if not any(elem(d, 1) == "011" for d in get_all(body, "DTM")):
        add(out, SPEC, "DTM011", "DTM", "DTM01", "DTM*011* ship date mandatory")
    dtm_deliv = [d for d in get_all(body, "DTM") if elem(d, 1) in {"067", "017"}]
    fob = next((s for s in body if s and s[0] == "FOB"), None)
    if fob and elem(fob, 1) == "PP" and not dtm_deliv:
        add(out, SPEC, "DTM017", "DTM", "DTM01", "DTM*067/017* delivery required when FOB is PP", "Warning")

    st_n1 = next((n for n in get_all(body, "N1") if elem(n, 1) == "ST"), None)
    if st_n1:
        if elem(st_n1, 3) != "92":
            add(out, SPEC, "N103", "N1", "N103", "N1*ST* N103=92 assigned by Do it Best")
        if not elem(st_n1, 4) or not re.fullmatch(r"\d{4,5}", elem(st_n1, 4)):
            add(out, SPEC, "N104", "N1", "N104", "N104 4–5 position RSC/member ID")

    sf = next((n for n in get_all(body, "N1") if elem(n, 1) == "SF"), None)
    if sf:
        if not elem(sf, 2):
            add(out, SPEC, "N102", "N1", "N102", "N1*SF* ship-from name")
        # N3/N4 after SF — simplified: require at least one N3 and one N4 in body after SF
        sf_i = body.index(sf)
        after = body[sf_i : sf_i + 8]
        if not any(s and s[0] == "N3" for s in after):
            add(out, SPEC, "N3SF", "N3", "", "N3 Ship-From address mandatory")
        if not any(s and s[0] == "N4" for s in after):
            add(out, SPEC, "N4SF", "N4", "", "N4 Ship-From city/state/zip/country mandatory")

    prf = next((s for s in body if s and s[0] == "PRF"), None)
    if prf and not elem(prf, 1):
        add(out, SPEC, "PRF01", "PRF", "PRF01", "PRF01 PO number mandatory")

    hl_validate_chain(body, SPEC, out, "HL")

    for i, s in enumerate(body):
        if s and s[0] == "HL" and elem(s, 3) == "I":
            end = next((j for j in range(i + 1, len(body)) if body[j] and body[j][0] == "HL"), len(body))
            chunk = body[i:end]
            lin = next((x for x in chunk if x and x[0] == "LIN"), None)
            sn1 = next((x for x in chunk if x and x[0] == "SN1"), None)
            if lin:
                if elem(lin, 2) not in {"IN", "CB"}:
                    add(out, SPEC, "LIN02", "LIN", "LIN02", "LIN02 must be IN or CB (Buyer item) per PDF", "Warning")
                sku = elem(lin, 3)
                if sku and len(sku) != 6:
                    add(out, SPEC, "LIN03", "LIN", "LIN03", "Do it Best SKU 6 positions", "Warning")
            if sn1:
                if not elem(sn1, 2):
                    add(out, SPEC, "SN102", "SN1", "SN102", "SN102 quantity shipped mandatory")
                if not elem(sn1, 3):
                    add(out, SPEC, "SN103", "SN1", "SN103", "SN103 UoM mandatory")
                if elem(sn1, 8) and elem(sn1, 8) != "IA":
                    add(out, SPEC, "SN108", "SN1", "SN108", "SN108 line status IA when used", "Warning")

    if not get_all(body, "CTT"):
        add(out, SPEC, "CTT0", "CTT", "", "CTT mandatory per PDF")

    return out


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else None
    text = open(path, encoding="utf-8", errors="replace").read() if path else sys.stdin.read()
    print(json.dumps(validate_doitbest_856(parse_edi(text)), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
