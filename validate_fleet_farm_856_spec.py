#!/usr/bin/env python3
"""
Fleet Farm 856 — validation against Fleet Farm_856.xls (EDI Mapping Specs v4010 Invoice/856).

Per spreadsheet (M=mandatory):
  BSN 01–04; HL shipment S; TD1 packaging/weight; TD5 SCAC (TD502=2); REF BM or MA or CF or CN or 2I;
  PER*CE* contact (M); DTM*011*; N1*ST* N103=92 N104; N1*SF* + N3/N4;
  Order: HL O, PRF PO, REF*IA*; Tare/Pack HL T/P + MAN*GM*;
  Item: HL I, LIN qualifiers, SN1 qty+UOM, PID F; CTT
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional, Set

from edi856_common import (
    add,
    elem,
    envelope_v4010_sh,
    get_all,
    hl_validate_chain,
    parse_edi,
    transaction_body,
)

SPEC = "Fleet Farm_856.xls v4010"


def validate_fleet_farm_856(segments: List[List[str]], gs03_allow: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if gs03_allow is None:
        gs03_allow = {"4147318121"}
    envelope_v4010_sh(segments, SPEC, out, gs03_allowed=gs03_allow, isa12="00401", gs08="004010")

    body = transaction_body(segments)
    if not body:
        add(out, SPEC, "TX000", "ST", "", "No ST/SE body")
        return out

    bsn = next((s for s in body if s and s[0] == "BSN"), None)
    if bsn:
        if elem(bsn, 1) != "00":
            add(out, SPEC, "BSN01", "BSN", "BSN01", "BSN01 expected 00 per xls", "Warning")
        for pos, name in ((2, "BSN02"), (3, "BSN03"), (4, "BSN04")):
            if not elem(bsn, pos):
                add(out, SPEC, name, "BSN", name, f"{name} mandatory")

    if not any(s and s[0] == "PER" for s in body):
        add(out, SPEC, "PER00", "PER", "", "PER*CE* supplier contact mandatory (xls M)")

    td5 = next((s for s in body if s and s[0] == "TD5"), None)
    if td5 and elem(td5, 2) != "2":
        add(out, SPEC, "TD502", "TD5", "TD502", "TD502 must be 2 (SCAC)")

    ref_ok = {"BM", "MA", "CF", "CN", "2I"}
    if not ref_ok.intersection({elem(r, 1) for r in get_all(body, "REF")}):
        add(out, SPEC, "REF00", "REF", "", "At least one REF in BM/MA/CF/CN/2I")

    if "011" not in {elem(d, 1) for d in get_all(body, "DTM")}:
        add(out, SPEC, "DTM011", "DTM", "DTM01", "DTM*011* ship date mandatory")

    hl_o = next((i for i, s in enumerate(body) if s and s[0] == "HL" and elem(s, 3) == "O"), None)
    ship_end = hl_o if hl_o is not None else len(body)
    for i, s in enumerate(body):
        if i >= ship_end:
            break
        if s and s[0] == "N1" and elem(s, 1) == "ST":
            if elem(s, 3) != "92":
                add(out, SPEC, "N103", "N1", "N103", "Shipment N1*ST requires N103=92")
            if not elem(s, 4):
                add(out, SPEC, "N104", "N1", "N104", "N104 store/warehouse ID (3–5 digit)")

    if hl_o is not None:
        hl_next = next(
            (i for i, s in enumerate(body) if i > hl_o and s and s[0] == "HL" and elem(s, 3) in {"P", "T", "I"}),
            len(body),
        )
        order_slice = body[hl_o:hl_next]
        if not any(s and s[0] == "REF" and elem(s, 1) == "IA" and elem(s, 2) for s in order_slice):
            add(out, SPEC, "REFIA", "REF", "REF01", "Order loop REF*IA* vendor site number mandatory per xls")

    prf = next((s for s in body if s and s[0] == "PRF"), None)
    if prf and not elem(prf, 4):
        add(out, SPEC, "PRF04", "PRF", "PRF04", "PRF04 PO date mandatory per xls", "Warning")

    hl_validate_chain(body, SPEC, out, "HL")

    for i, s in enumerate(body):
        if s and s[0] == "HL" and elem(s, 3) == "I":
            end = next((j for j in range(i + 1, len(body)) if body[j] and body[j][0] == "HL"), len(body))
            chunk = body[i:end]
            if not any(x and x[0] == "PID" for x in chunk):
                add(out, SPEC, "PID00", "PID", "", "PID*F* item description (xls)", "Warning")
            sn1 = next((x for x in chunk if x and x[0] == "SN1"), None)
            if sn1 and elem(sn1, 2) and not elem(sn1, 3):
                add(out, SPEC, "SN103", "SN1", "SN103", "SN103 UoM mandatory")

    if not get_all(body, "CTT"):
        add(out, SPEC, "CTT00", "CTT", "", "CTT summary required per xls", "Warning")

    return out


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else None
    text = open(path, encoding="utf-8", errors="replace").read() if path else sys.stdin.read()
    print(json.dumps(validate_fleet_farm_856(parse_edi(text)), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
