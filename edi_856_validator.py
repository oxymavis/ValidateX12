#!/usr/bin/env python3
"""
EDI 856 (Ship Notice/Manifest) — strict validator against configurable customer spec.

Edit CUSTOMER_SPEC below to match your trading partner (required REF qualifiers,
N1 entity codes, HL rules, etc.). Default profile follows common X12 4010 856 practice.
"""

from __future__ import annotations

import json
import re
import sys
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Customer / partner specification — adjust to match your 856 implementation guide
# ---------------------------------------------------------------------------
CUSTOMER_SPEC: Dict[str, Any] = {
    # Envelope
    "isa12": "00401",
    "gs01": "SH",
    "gs08": "004010",
    # Transaction
    "st01": "856",
    # BSN required element positions (1-based X12 indices): BSN01 purpose, BSN02 ship id, BSN03 date
    "bsn_required_positions": [1, 2, 3],
    "bsn01_allowed": {"00"},  # 00 = Original
    # HL: first segment must be shipment level (HL03 = S)
    "require_first_hl_shipment": True,
    "hl03_shipment_code": "S",
    # HL01 must be unique; HL02 must reference existing HL01 or be empty for root shipment HL
    "validate_hl_parent_links": True,
    # REF: these qualifiers must appear at least once in the transaction (empty list = skip)
    "required_ref_qualifiers": [],
    # Example: ["BM", "PO"] - uncomment or set when your spec requires them
    # N1: at least one of these entity codes must appear (empty = skip)
    "required_n1_entity_codes": [],
    # Example: ["ST", "SF"] or ["ST"] for ship-to only
    # Warn if no TD1/TD3/TD5 (carrier) — many specs require at least one
    "warn_if_no_transport_segments": False,
    # Disallow unused elements in BSN (positions beyond spec) — strict profile
    "bsn_unused_must_be_blank": True,
    # BSN positions considered "not used" in minimal profile (1-based): BSN05-08
    "bsn_unused_positions": [5, 6, 7, 8],
}


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


def parse_edi(edi_content: str) -> Tuple[List[List[str]], str, str]:
    """Parse X12 content and return (segments, element_sep, segment_term)."""
    edi_content = edi_content.strip()
    if not edi_content:
        return [], "*", "~"

    element_sep = "*"
    segment_term = "~"

    if "~" in edi_content:
        raw = edi_content.replace("~\n", "~").replace("\n", "~")
        seg_strings = [s.strip() for s in raw.split(segment_term) if s.strip()]
    else:
        seg_strings = [s.strip() for s in edi_content.splitlines() if s.strip()]

    return [s.split(element_sep) for s in seg_strings], element_sep, segment_term


def get_segments(segments: List[List[str]], seg_id: str) -> List[List[str]]:
    return [s for s in segments if s and s[0] == seg_id]


def elem(seg: List[str], idx: int) -> str:
    if idx <= 0 or idx >= len(seg):
        return ""
    return (seg[idx] or "").strip()


def raw_elem(seg: List[str], idx: int) -> str:
    if idx <= 0 or idx >= len(seg):
        return ""
    return seg[idx] or ""


def is_valid_date(value: str) -> bool:
    if not re.fullmatch(r"\d{8}", value or ""):
        return False
    try:
        datetime.strptime(value, "%Y%m%d")
        return True
    except ValueError:
        return False


def is_valid_time(value: str) -> bool:
    if re.fullmatch(r"\d{4}", value or ""):
        hh, mm = int(value[:2]), int(value[2:])
        return 0 <= hh <= 23 and 0 <= mm <= 59
    if re.fullmatch(r"\d{6}", value or ""):
        hh, mm, ss = int(value[:2]), int(value[2:4]), int(value[4:])
        return 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59
    if re.fullmatch(r"\d{7}", value or ""):
        hh, mm, ss = int(value[:2]), int(value[2:4]), int(value[4:6])
        return 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59
    if re.fullmatch(r"\d{8}", value or ""):
        hh, mm, ss = int(value[:2]), int(value[2:4]), int(value[4:6])
        return 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59
    return False


def is_integer(value: str) -> bool:
    return bool(re.fullmatch(r"-?\d+", value or ""))


def has_value(seg: List[str], idx: int) -> bool:
    return bool(elem(seg, idx))


def merge_spec(override: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out = deepcopy(CUSTOMER_SPEC)
    if override:
        out.update(override)
    return out


def validate_edi_856(
    edi_content: str,
    spec: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    errors: List[ValidationError] = []
    sp = merge_spec(spec)

    def add_error(code: str, segment: str, element: str, message: str, severity: str = "Error") -> None:
        errors.append(ValidationError(code, segment, element, severity, message))

    segments, _, _ = parse_edi(edi_content)
    if not segments:
        return [ValidationError("E001", "ISA", "ISA", "Error", "Empty or no segments").to_dict()]

    segment_ids = [s[0] for s in segments if s]
    isa_list = get_segments(segments, "ISA")
    iea_list = get_segments(segments, "IEA")
    gs_list = get_segments(segments, "GS")
    ge_list = get_segments(segments, "GE")
    st_list = get_segments(segments, "ST")
    se_list = get_segments(segments, "SE")

    # --- Envelope: ISA / IEA ---
    if not isa_list:
        add_error("E001", "ISA", "ISA", "ISA missing")
    elif len(isa_list) > 1:
        add_error("E001", "ISA", "ISA", "ISA must exist exactly once")
    if not iea_list:
        add_error("E002", "IEA", "IEA", "IEA missing")
    elif len(iea_list) > 1:
        add_error("E002", "IEA", "IEA", "IEA must exist exactly once")

    isa = isa_list[0] if isa_list else None
    iea = iea_list[-1] if iea_list else None

    if isa:
        if len(raw_elem(isa, 6)) != 15:
            add_error("E003", "ISA", "ISA06", "ISA06 must be 15 characters")
        if len(raw_elem(isa, 8)) != 15:
            add_error("E003", "ISA", "ISA08", "ISA08 must be 15 characters")
        if elem(isa, 12) != sp.get("isa12", "00401"):
            add_error("E003", "ISA", "ISA12", f"ISA12 must be {sp.get('isa12', '00401')}")
        if not re.fullmatch(r"\d{9}", elem(isa, 13) or ""):
            add_error("E003", "ISA", "ISA13", "ISA13 must be 9-digit control number")
    if iea and isa:
        if is_integer(elem(iea, 1)) and int(elem(iea, 1)) != len(gs_list):
            add_error("E004", "IEA", "IEA01", "IEA01 must equal number of GS groups")
        if elem(iea, 2) != elem(isa, 13):
            add_error("E004", "IEA", "IEA02", "IEA02 must equal ISA13")

    # --- GS / GE ---
    if not gs_list:
        add_error("E010", "GS", "GS", "GS missing")
    elif len(gs_list) > 1:
        add_error("E010", "GS", "GS", "GS must exist exactly once")
    if not ge_list:
        add_error("E012", "GE", "GE", "GE missing")
    elif len(ge_list) > 1:
        add_error("E012", "GE", "GE", "GE must exist exactly once")

    gs = gs_list[0] if gs_list else None
    ge = ge_list[-1] if ge_list else None
    if gs:
        if elem(gs, 1) != sp.get("gs01", "SH"):
            add_error("E010", "GS", "GS01", f"GS01 must be {sp.get('gs01', 'SH')} for 856")
        if not (2 <= len(elem(gs, 2)) <= 15):
            add_error("E011", "GS", "GS02", "GS02 required and must be length 2-15")
        if not (2 <= len(elem(gs, 3)) <= 15):
            add_error("E011", "GS", "GS03", "GS03 required and must be length 2-15")
        if not is_valid_date(elem(gs, 4)):
            add_error("E011", "GS", "GS04", "GS04 must be valid date CCYYMMDD")
        if not is_valid_time(elem(gs, 5)):
            add_error("E011", "GS", "GS05", "GS05 must be valid time")
        if not re.fullmatch(r"\d{1,9}", elem(gs, 6) or ""):
            add_error("E011", "GS", "GS06", "GS06 must be numeric length 1-9")
        if elem(gs, 7) != "X":
            add_error("E011", "GS", "GS07", "GS07 must be X")
        if elem(gs, 8) != sp.get("gs08", "004010"):
            add_error("E011", "GS", "GS08", f"GS08 must be {sp.get('gs08', '004010')}")
    if ge and gs:
        if is_integer(elem(ge, 1)) and int(elem(ge, 1)) != len(st_list):
            add_error("E012", "GE", "GE01", "GE01 must equal ST/SE transaction count")
        if elem(ge, 2) != elem(gs, 6):
            add_error("E012", "GE", "GE02", "GE02 must equal GS06")

    # --- ST / SE ---
    if not st_list:
        add_error("E020", "ST", "ST", "ST missing")
    elif len(st_list) > 1:
        add_error("E020", "ST", "ST", "ST must exist exactly once for this profile")
    if not se_list:
        add_error("E021", "SE", "SE", "SE missing")
    elif len(se_list) > 1:
        add_error("E021", "SE", "SE", "SE must exist exactly once for this profile")

    st_indices = [i for i, s in enumerate(segments) if s and s[0] == "ST"]
    se_indices = [i for i, s in enumerate(segments) if s and s[0] == "SE"]

    for st_idx in st_indices:
        st_seg = segments[st_idx]
        if elem(st_seg, 1) != sp.get("st01", "856"):
            add_error("E020", "ST", "ST01", f"ST01 must be {sp.get('st01', '856')}")
        if not elem(st_seg, 2):
            add_error("E021", "ST", "ST02", "ST02 control number required")
        elif not (4 <= len(elem(st_seg, 2)) <= 9):
            add_error("E021", "ST", "ST02", "ST02 length must be 4-9")

        matching_se_idx = None
        for idx in se_indices:
            if idx > st_idx:
                matching_se_idx = idx
                break
        if matching_se_idx is None:
            add_error("E021", "SE", "SE", "SE missing after ST")
            continue

        se_seg = segments[matching_se_idx]
        if elem(se_seg, 2) != elem(st_seg, 2):
            add_error("E021", "SE", "SE02", "SE02 must equal ST02")
        if is_integer(elem(se_seg, 1)):
            expected_count = int(elem(se_seg, 1))
            actual_count = matching_se_idx - st_idx + 1
            if expected_count != actual_count:
                add_error(
                    "E022",
                    "SE",
                    "SE01",
                    f"SE01 segment count mismatch (expected {expected_count}, actual {actual_count})",
                )

        # Body: ST+1 .. SE-1
        body = segments[st_idx + 1 : matching_se_idx]
        body_ids = [s[0] for s in body if s]

        # --- BSN ---
        bsn_list = [s for s in body if s and s[0] == "BSN"]
        if not bsn_list:
            add_error("E100", "BSN", "BSN", "BSN segment required for 856")
        else:
            if len(bsn_list) > 1:
                add_error("E100", "BSN", "BSN", "Only one BSN allowed per transaction")
            bsn = bsn_list[0]
            for pos in sp.get("bsn_required_positions", [1, 2, 3]):
                if not elem(bsn, pos):
                    add_error("E101", "BSN", f"BSN{pos:02d}", f"BSN{pos:02d} required by spec")
            if elem(bsn, 1) and sp.get("bsn01_allowed") and elem(bsn, 1) not in sp["bsn01_allowed"]:
                add_error("E102", "BSN", "BSN01", f"BSN01 must be one of {sorted(sp['bsn01_allowed'])}")
            if elem(bsn, 3) and not is_valid_date(elem(bsn, 3)):
                add_error("E103", "BSN", "BSN03", "BSN03 must be valid date CCYYMMDD")
            if elem(bsn, 4) and not is_valid_time(elem(bsn, 4)):
                add_error("E104", "BSN", "BSN04", "BSN04 must be valid time when present")
            if sp.get("bsn_unused_must_be_blank"):
                for pos in sp.get("bsn_unused_positions", []):
                    if has_value(bsn, pos):
                        add_error(
                            "E105",
                            "BSN",
                            f"BSN{pos:02d}",
                            f"BSN{pos:02d} should be blank per minimal profile",
                            severity="Warning",
                        )

        # --- HL ---
        hl_list = [s for s in body if s and s[0] == "HL"]
        if not hl_list:
            add_error("E200", "HL", "HL", "At least one HL segment required")
        else:
            if sp.get("require_first_hl_shipment"):
                first = hl_list[0]
                ship_code = sp.get("hl03_shipment_code", "S")
                if elem(first, 3) != ship_code:
                    add_error(
                        "E201",
                        "HL",
                        "HL03",
                        f"First HL03 must be shipment level {ship_code!r}",
                    )
                if elem(first, 2):
                    add_error("E202", "HL", "HL02", "First HL should have empty HL02 (root shipment)")

            if sp.get("validate_hl_parent_links", True):
                hl01_seen: Set[str] = set()
                for h in hl_list:
                    h01 = elem(h, 1)
                    h02 = elem(h, 2)
                    if not h01:
                        add_error("E203", "HL", "HL01", "HL01 hierarchical ID required")
                    elif h01 in hl01_seen:
                        add_error("E204", "HL", "HL01", f"Duplicate HL01 {h01!r}")
                    if h02 and h02 not in hl01_seen:
                        add_error("E205", "HL", "HL02", f"HL02 parent id {h02!r} must reference prior HL01")
                    if h01:
                        hl01_seen.add(h01)

        # --- REF qualifiers (global) ---
        required_refs = sp.get("required_ref_qualifiers") or []
        if required_refs:
            ref_segs = [s for s in body if s and s[0] == "REF"]
            found: Set[str] = set()
            for r in ref_segs:
                q = elem(r, 1)
                if q:
                    found.add(q)
            for rq in required_refs:
                if rq not in found:
                    add_error("E300", "REF", "REF01", f"Required REF qualifier {rq!r} missing")

        # --- N1 entity codes ---
        required_n1 = sp.get("required_n1_entity_codes") or []
        if required_n1:
            n1_segs = [s for s in body if s and s[0] == "N1"]
            codes = {elem(n, 1) for n in n1_segs if elem(n, 1)}
            for code in required_n1:
                if code not in codes:
                    add_error("E310", "N1", "N101", f"Required N1 entity {code!r} missing")

        # --- Optional: transport segments ---
        if sp.get("warn_if_no_transport_segments"):
            if not any(x in body_ids for x in ("TD1", "TD3", "TD5")):
                add_error(
                    "E400",
                    "TD1",
                    "TD1",
                    "No TD1/TD3/TD5 in transaction — verify carrier/packaging per partner spec",
                    severity="Warning",
                )

    return [e.to_dict() for e in errors]


def main() -> None:
    edi_path: Optional[str] = None
    spec_path: Optional[str] = None
    args = sys.argv[1:]
    if args and not args[0].startswith("-"):
        edi_path = args[0]
        args = args[1:]
    if len(args) >= 1 and args[0].endswith(".json"):
        spec_path = args[0]

    spec_override: Optional[Dict[str, Any]] = None
    if spec_path:
        with open(spec_path, "r", encoding="utf-8", errors="replace") as f:
            spec_override = json.load(f)

    if edi_path:
        with open(edi_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    else:
        content = sys.stdin.read()

    print(json.dumps(validate_edi_856(content, spec_override), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
