#!/usr/bin/env python3
"""
Burlington Stores 856 — validation against Burlington Stores_856_specifications_13nov17.pdf
(BCF_x12_4010_856 Draft, Functional Group SH).

Envelope: X12 4010 interchange (ISA12=00401), GS08=004010, GS01=SH.
Transaction: ST*856*, BSN, HL loops per draft; CTT optional with Walmart-style hash notes where used.
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

SPEC = "Burlington Stores_856_specifications_13nov17.pdf (4010 Draft, FG=SH)"


def validate_burlington_856(segments: List[List[str]], gs03_allow: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if gs03_allow is None:
        gs03_allow = {"6126750000"}
    envelope_v4010_sh(segments, SPEC, out, gs03_allowed=gs03_allow, isa12="00401", gs08="004010")

    body = transaction_body(segments)
    if not body:
        add(out, SPEC, "TX000", "ST", "", "No ST/SE body")
        return out

    st = get_all(segments, "ST")
    if st and elem(st[0], 1) != "856":
        add(out, SPEC, "ST01", "ST", "ST01", "ST01=856")

    bsn = next((s for s in body if s and s[0] == "BSN"), None)
    if bsn:
        if elem(bsn, 1) not in {"00", "05"}:
            add(out, SPEC, "BSN01", "BSN", "BSN01", "BSN01 qualifier", "Warning")
        if not is_ccyymmdd(elem(bsn, 3)):
            add(out, SPEC, "BSN03", "BSN", "BSN03", "BSN03 date")
        if elem(bsn, 4) and not re.fullmatch(r"\d{4,8}", elem(bsn, 4)):
            add(out, SPEC, "BSN04", "BSN", "BSN04", "BSN04 time format", "Warning")

    hl_validate_chain(body, SPEC, out, "HL")

    for n4 in get_all(body, "N4"):
        if elem(n4, 4) == "USA":
            add(out, SPEC, "N404", "N4", "N404", "Use US not USA", "Warning")

    for i, s in enumerate(body):
        if s and s[0] == "HL" and elem(s, 3) == "I":
            end = next((j for j in range(i + 1, len(body)) if body[j] and body[j][0] == "HL"), len(body))
            chunk = body[i:end]
            lin = next((x for x in chunk if x and x[0] == "LIN"), None)
            sn1 = next((x for x in chunk if x and x[0] == "SN1"), None)
            if lin and sn1 and elem(lin, 1) and not elem(sn1, 1):
                add(out, SPEC, "SN101", "SN1", "SN101", "SN101 should match LIN01", "Warning")

    return out


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else None
    text = open(path, encoding="utf-8", errors="replace").read() if path else sys.stdin.read()
    print(json.dumps(validate_burlington_856(parse_edi(text)), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
