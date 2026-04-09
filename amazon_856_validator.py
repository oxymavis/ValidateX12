#!/usr/bin/env python3
"""
Amazon Retail X12 856 (V5010) validator — rules from Amazon Retail 856 ASN Specification v3.1 (PDF).
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class ValidationError:
    code: str
    segment: str
    element: str
    severity: str
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "segment": self.segment,
            "element": self.element,
            "severity": self.severity,
            "message": self.message,
        }


def parse_edi(edi_content: str) -> List[List[str]]:
    edi_content = edi_content.strip()
    if not edi_content:
        return []
    if "~" in edi_content:
        raw = edi_content.replace("~\n", "~").replace("\n", "~")
        seg_strings = [s.strip() for s in raw.split("~") if s.strip()]
    else:
        seg_strings = [s.strip() for s in edi_content.splitlines() if s.strip()]
    return [s.split("*") for s in seg_strings]


def elem(seg: List[str], idx: int) -> str:
    if idx <= 0 or idx >= len(seg):
        return ""
    return (seg[idx] or "").strip()


def raw_elem(seg: List[str], idx: int) -> str:
    if idx <= 0 or idx >= len(seg):
        return ""
    return seg[idx] or ""


def get_segments(segments: List[List[str]], seg_id: str) -> List[List[str]]:
    return [s for s in segments if s and s[0] == seg_id]


def is_valid_date_ccyymmdd(value: str) -> bool:
    if not re.fullmatch(r"\d{8}", value or ""):
        return False
    from datetime import datetime

    try:
        datetime.strptime(value, "%Y%m%d")
        return True
    except ValueError:
        return False


def is_integer(s: str) -> bool:
    return bool(re.fullmatch(r"-?\d+", s or ""))


def validate_amazon_856_retail(segments: List[List[str]]) -> List[Dict[str, Any]]:
    errors: List[ValidationError] = []

    def add(
        code: str,
        segment: str,
        element: str,
        message: str,
        severity: str = "Error",
    ) -> None:
        errors.append(ValidationError(code, segment, element, severity, message))

    if not segments:
        add("A001", "FILE", "", "Empty EDI")
        return [e.to_dict() for e in errors]

    # --- ISA ---
    isa = get_segments(segments, "ISA")
    if not isa:
        add("A010", "ISA", "", "ISA missing")
    else:
        i = isa[0]
        if elem(i, 12) != "00501":
            add("A011", "ISA", "ISA12", f"Amazon spec: ISA12 must be 00501 (got {elem(i, 12)!r})")
        if elem(i, 8) not in {"AMAZON", "AMAZONCA", "AMAZONMX", "AMAZONBR", "AMAZONSG", "AMAZONAU"}:
            add(
                "A012",
                "ISA",
                "ISA08",
                f"ISA08 should be Amazon receiver id (e.g. AMAZON); got {elem(i, 8)!r}",
                severity="Warning",
            )
        if len(raw_elem(i, 6)) != 15:
            add("A013", "ISA", "ISA06", "ISA06 must be exactly 15 characters (padded)")
        if len(raw_elem(i, 8)) != 15:
            add("A014", "ISA", "ISA08", "ISA08 must be exactly 15 characters (padded)")
        if elem(i, 15) == "T":
            add(
                "A015",
                "ISA",
                "ISA15",
                "ISA15=T (Test). Production traffic should use P per Amazon examples.",
                severity="Warning",
            )

    iea_list = get_segments(segments, "IEA")
    if isa and iea_list:
        iea = iea_list[0]
        if elem(iea, 2) != elem(isa[0], 13):
            add("A016", "IEA", "IEA02", "IEA02 must equal ISA13 interchange control number")
        if elem(iea, 1) != "1":
            add("A017", "IEA", "IEA01", "IEA01 must equal number of functional groups (typically 1)")

    # --- GS ---
    gs = get_segments(segments, "GS")
    if not gs:
        add("A020", "GS", "", "GS missing")
    else:
        g = gs[0]
        # PDF: GS01 = SH (Ship Notice/Manifest)
        if elem(g, 1) != "SH":
            add(
                "A021",
                "GS",
                "GS01",
                f"Amazon 856 requires GS01=SH (Ship Notice/Manifest); got {elem(g, 1)!r}. "
                "SW is incorrect for this guide.",
            )
        if elem(g, 8) != "005010":
            add("A022", "GS", "GS08", f"Amazon V5010 expects GS08=005010 (got {elem(g, 8)!r})")

    ge_list = get_segments(segments, "GE")
    if gs and ge_list:
        ge = ge_list[0]
        g0 = gs[0]
        if elem(ge, 2) != elem(g0, 6):
            add("A025", "GE", "GE02", f"GE02 must equal GS06 (got GE02={elem(ge, 2)!r}, GS06={elem(g0, 6)!r})")
        if elem(ge, 1) != "1":
            add("A026", "GE", "GE01", "GE01 must equal number of ST/SE sets in group (1 for single 856)")

    # --- ST/SE body ---
    st_idx = next((i for i, s in enumerate(segments) if s and s[0] == "ST"), None)
    se_idx = next((i for i, s in enumerate(segments) if s and s[0] == "SE"), None)
    if st_idx is None or se_idx is None or se_idx <= st_idx:
        add("A030", "ST/SE", "", "ST/SE transaction boundaries not found")
        return [e.to_dict() for e in errors]

    st = segments[st_idx]
    se = segments[se_idx]
    if elem(st, 1) != "856":
        add("A031", "ST", "ST01", "ST01 must be 856")
    if elem(se, 2) != elem(st, 2):
        add("A034", "SE", "SE02", f"SE02 must equal ST02 (got {elem(se, 2)!r} vs {elem(st, 2)!r})")

    body = segments[st_idx + 1 : se_idx]

    # SE01 count
    if is_integer(elem(se, 1)):
        expected = int(elem(se, 1))
        actual = se_idx - st_idx + 1
        if expected != actual:
            add(
                "A032",
                "SE",
                "SE01",
                f"SE01 segment count: reported {expected}, actual {actual} (ST through SE inclusive)",
            )

    # --- BSN ---
    bsn_list = [s for s in body if s and s[0] == "BSN"]
    if not bsn_list:
        add("A100", "BSN", "", "BSN required")
    else:
        b = bsn_list[0]
        if elem(b, 1) not in {"00", "05"}:
            add("A101", "BSN", "BSN01", f"BSN01 should be 00 (Original) or 05 (Replace); got {elem(b, 1)!r}")
        if not elem(b, 2):
            add("A102", "BSN", "BSN02", "BSN02 Shipment ID required (unique per ASN)")
        if not is_valid_date_ccyymmdd(elem(b, 3)):
            add("A103", "BSN", "BSN03", "BSN03 must be CCYYMMDD (ASN creation date)")
        # PDF: BSN04 Time expressed as HHMMSS
        bsn04 = elem(b, 4)
        if bsn04:
            if not re.fullmatch(r"\d{6}", bsn04):
                add(
                    "A104",
                    "BSN",
                    "BSN04",
                    f"Amazon spec: BSN04 time must be HHMMSS (6 digits); got {bsn04!r}",
                )
        if elem(b, 5) and elem(b, 5) != "0001":
            add(
                "A105",
                "BSN",
                "BSN05",
                f"BSN05 hierarchical structure code: expected 0001 for pick/pack; got {elem(b, 5)!r}",
                severity="Warning",
            )

    # --- DTM: Shipped 011 and Estimated Delivery 017 both mandatory per PDF segment usage ---
    dtm_list = [s for s in body if s and s[0] == "DTM"]
    dtm_quals = {elem(d, 1) for d in dtm_list}
    if "011" not in dtm_quals:
        add("A110", "DTM", "DTM01", "Shipped date DTM*011*CCYYMMDD is required")
    if "017" not in dtm_quals:
        add("A111", "DTM", "DTM01", "Estimated delivery DTM*017*CCYYMMDD is required (per Amazon spec)")
    for d in dtm_list:
        q = elem(d, 1)
        if q in {"011", "017"} and elem(d, 2) and not is_valid_date_ccyymmdd(elem(d, 2)):
            add("A112", "DTM", "DTM02", f"DTM*{q}* date must be CCYYMMDD")

    # --- TD3: import only ---
    if get_segments(body, "TD3"):
        add(
            "A120",
            "TD3",
            "",
            "TD3 is only for import ASNs — not for domestic US messaging (per Amazon spec)",
            severity="Warning",
        )

    # --- Shipment HL: one shipment loop ---
    hl_all = [(i, s) for i, s in enumerate(body) if s and s[0] == "HL"]
    if not hl_all:
        add("A200", "HL", "", "At least one HL required")
    else:
        first_hl = hl_all[0][1]
        if elem(first_hl, 3) != "S":
            add("A201", "HL", "HL03", "First HL must be shipment level (HL03=S)")
        # HL04 optional in examples as 2 elements; spec example HL*1**S
        hl01_seen: Set[str] = set()
        for _, h in hl_all:
            h01, h02 = elem(h, 1), elem(h, 2)
            if not h01:
                add("A202", "HL", "HL01", "HL01 required")
            elif h01 in hl01_seen:
                add("A203", "HL", "HL01", f"Duplicate HL01 {h01!r}")
            if h02 and h02 not in hl01_seen:
                add("A204", "HL", "HL02", f"HL02 parent {h02!r} must reference a prior HL01")
            if h01 and h01 not in hl01_seen:
                hl01_seen.add(h01)

    # --- REF shipment level: CN mandatory; BM conditional TL/LTL ---
    # Collect REFs before first Order HL (HL with HL03=O)
    shipment_refs: List[List[str]] = []
    for s in body:
        if s and s[0] == "HL" and elem(s, 3) == "O":
            break
        if s and s[0] == "REF":
            shipment_refs.append(s)
    ref1 = {elem(r, 1) for r in shipment_refs}
    if "CN" not in ref1:
        add("A210", "REF", "REF01", "Shipment-level REF*CN (tracking/PRO) is required for LTL/TL/small parcel")

    # --- N1 at shipment: ST and SF mandatory; SO not in Amazon mandatory table ---
    n1_before_order: List[List[str]] = []
    for s in body:
        if s and s[0] == "HL" and elem(s, 3) == "O":
            break
        if s and s[0] == "N1":
            n1_before_order.append(s)
    n1_codes = [elem(n, 1) for n in n1_before_order]
    if "ST" not in n1_codes:
        add("A220", "N1", "N101", "Shipment loop must include N1*ST (Ship To)")
    if "SF" not in n1_codes:
        add("A221", "N1", "N101", "Shipment loop must include N1*SF (Ship From)")
    for n in n1_before_order:
        if elem(n, 1) == "SO":
            add(
                "A222",
                "N1",
                "N101",
                "N1*SO is not in Amazon mandatory shipment party list (ST/SF required). "
                "Verify if your partner allows Sold To / ordering party here.",
                severity="Warning",
            )
        if elem(n, 1) == "ST":
            n4_list = []  # find N4 following this N1 until next N1/HL
            idx = body.index(n)
            for j in range(idx + 1, len(body)):
                if body[j][0] in {"N1", "HL"}:
                    break
                if body[j][0] == "N4":
                    n4_list.append(body[j])
            for n4 in n4_list:
                c = elem(n4, 4)
                if c and c not in {"US", "CA", "MX", "GB"} and len(c) != 2:
                    add(
                        "A223",
                        "N4",
                        "N404",
                        f"N404 country should be ISO 3166-1 alpha-2; got {c!r}",
                        severity="Warning",
                    )
                if c == "USA":
                    add(
                        "A224",
                        "N4",
                        "N404",
                        "Use ISO alpha-2 'US' rather than 'USA' for N404 (Amazon formatting notes)",
                        severity="Warning",
                    )

    # --- Item loops: LIN01 vs SN102; CTT ---
    item_hl_indices = [i for i, s in enumerate(body) if s and s[0] == "HL" and elem(s, 3) == "I"]
    sn1_sum = 0
    for hi in item_hl_indices:
        # LIN and SN1 expected immediately after HL*I in structure
        chunk_end = len(body)
        for k in range(hi + 1, len(body)):
            if body[k] and body[k][0] == "HL":
                chunk_end = k
                break
        chunk = body[hi:chunk_end]
        lin_segs = [x for x in chunk if x and x[0] == "LIN"]
        sn1_segs = [x for x in chunk if x and x[0] == "SN1"]
        if not lin_segs:
            add("A300", "LIN", "", "Item HL loop must include LIN")
            continue
        if not sn1_segs:
            add("A301", "SN1", "", "Item HL loop must include SN1")
            continue
        lin, sn1 = lin_segs[0], sn1_segs[0]
        l1 = elem(lin, 1)
        # Amazon SN1 notes: SN101 must match LIN01 (line number)
        s1 = elem(sn1, 1)
        s2 = elem(sn1, 2)
        if l1 and s1 and l1 != s1:
            add(
                "A302",
                "SN1",
                "SN101",
                f"SN101 ({s1!r}) must match LIN01 ({l1!r}) per Amazon spec",
            )
        elif l1 and not s1:
            add(
                "A303",
                "SN1",
                "SN101",
                f"SN101 should repeat LIN01 ({l1!r}) — currently empty",
            )
        if s2 and is_integer(s2):
            sn1_sum += int(s2)
        sn3 = elem(sn1, 3)
        if s2 and not sn3:
            add(
                "A304",
                "SN1",
                "SN103",
                f"SN103 unit of measure (EA/CA) required when SN102 is present; LIN01={l1!r}",
                severity="Warning",
            )

    ctt_list = [s for s in body if s and s[0] == "CTT"]
    if ctt_list:
        c = ctt_list[0]
        hl_count = len([s for s in body if s and s[0] == "HL"])
        ctt1 = elem(c, 1)
        ctt2 = elem(c, 2)
        if ctt1 and is_integer(ctt1) and int(ctt1) != hl_count:
            add(
                "A310",
                "CTT",
                "CTT01",
                f"CTT01 should equal logical count of HL loops ({hl_count}); got {ctt1!r}",
            )
        if ctt2 and is_integer(ctt2) and int(ctt2) != sn1_sum:
            add(
                "A311",
                "CTT",
                "CTT02",
                f"CTT02 should equal sum of SN102 units ({sn1_sum}); got {ctt2!r}",
            )

    # --- REF*VN vs spec naming (Vendor code often used; BX is ARN) ---
    for r in get_segments(body, "REF"):
        if elem(r, 1) == "23":
            add(
                "A400",
                "REF",
                "REF01",
                "REF*23 — verify qualifier is accepted by Amazon for your region (not in core BM/CN/SN/BX list)",
                severity="Warning",
            )

    return [e.to_dict() for e in errors]


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if path:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    else:
        content = sys.stdin.read()
    segs = parse_edi(content)
    print(json.dumps(validate_amazon_856_retail(segs), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
