#!/usr/bin/env python3
"""
Delhaize America 856 DSD V5010 — validation against Delhaize_America_856_v5010_DSD.pdf

NOTE: The PDF file is largely image-based; extractable text is minimal. This module applies:
  - X12 V5010 envelope (ISA 00501, GS*SH*, GS08 005010)
  - Standard 856 retail practices (BSN, ST/SE, HL chain, SN1/LIN alignment)
  - Optional GS03 allow-list when your VAN ID is fixed

Replace or extend DELHAIZE_GS03 with your production receiver ID from Delhaize.
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

SPEC = "Delhaize_America_856_v5010_DSD.pdf (V5010 DSD — PDF text minimal; rules: X12 5010 + profile)"
DELHAIZE_GS03: Set[str] = {"540011000"}


def validate_delhaize_856(segments: List[List[str]], gs03_allow: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if gs03_allow is None:
        gs03_allow = DELHAIZE_GS03
    envelope_v5010_sh(segments, SPEC, out, gs03_allowed=gs03_allow, isa12="00501", gs08="005010")

    body = transaction_body(segments)
    if not body:
        add(out, SPEC, "TX000", "ST", "", "No ST/SE body")
        return out

    joined = "*".join("*".join(s) for s in body).upper()
    if "DELHAIZE" not in joined and "AHOLD" not in joined:
        add(out, SPEC, "DZ001", "N1", "", "Expected Delhaize/Ahold party reference in shipment data", "Warning")

    bsn = next((s for s in body if s and s[0] == "BSN"), None)
    if bsn:
        if elem(bsn, 1) not in {"00", "05"}:
            add(out, SPEC, "BSN01", "BSN", "BSN01", "BSN01 00/05")
        if not is_ccyymmdd(elem(bsn, 3)):
            add(out, SPEC, "BSN03", "BSN", "BSN03", "BSN03 date CCYYMMDD")
        if elem(bsn, 4) and not re.fullmatch(r"\d{4}|\d{6}|\d{7}|\d{8}", elem(bsn, 4)):
            add(out, SPEC, "BSN04", "BSN", "BSN04", "BSN04 valid TM")

    hl_validate_chain(body, SPEC, out, "HL")

    for i, s in enumerate(body):
        if s and s[0] == "HL" and elem(s, 3) == "I":
            end = next((j for j in range(i + 1, len(body)) if body[j] and body[j][0] == "HL"), len(body))
            chunk = body[i:end]
            lin = next((x for x in chunk if x and x[0] == "LIN"), None)
            sn1 = next((x for x in chunk if x and x[0] == "SN1"), None)
            if lin and sn1 and elem(lin, 1) and not elem(sn1, 1):
                add(out, SPEC, "SN101", "SN1", "SN101", f"SN101 should repeat LIN01 ({elem(lin, 1)!r})")

    for n4 in get_all(body, "N4"):
        if elem(n4, 4) == "USA":
            add(out, SPEC, "N404", "N4", "N404", "Prefer ISO alpha-2 US", "Warning")

    return out


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else None
    text = open(path, encoding="utf-8", errors="replace").read() if path else sys.stdin.read()
    print(json.dumps(validate_delhaize_856(parse_edi(text)), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
