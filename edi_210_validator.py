#!/usr/bin/env python3
"""
EDI 210 (Motor Carrier Freight Details and Invoice) Validator
Enhanced according to Vitacoco-E2open-EDI_210_validation_rules.md
and additional validation suggestions.
"""

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

APPENDIX_A_SPECIAL_CHARGE_CODES = {
    "002", "003", "010", "015", "020", "025", "027", "030", "090", "095", "100", "105", "110", "145", "150",
    "160", "170", "185", "260", "275", "295", "310", "315", "335", "340", "345", "350", "355", "360", "365",
    "370", "400", "405", "420", "425", "440", "445", "450", "470", "490", "495", "500", "510", "520", "535",
    "540", "550", "555", "560", "565", "570", "580", "585", "586", "593", "600", "605", "615", "650", "665",
    "670", "685", "690", "695", "736", "740", "745", "750", "761", "762", "999", "AAJ", "ABL", "ACH", "ACL",
    "ADH", "ADL", "AFB", "AIC", "AIR", "AMC", "APT", "ARR", "AUX", "BAB", "BAS", "BEY", "BLK", "BND", "BRD",
    "CAA", "CBL", "CDR", "CGL", "CHN", "CLC", "CLN", "CLS", "CMI", "CNS", "COD", "COL", "CON", "COU", "CRS",
    "CTC", "CUA", "CUD", "CUS", "DAA", "DCE", "DCT", "DEL", "DEM", "DEP", "DET", "DEW", "DGS", "DIV", "DLH",
    "DMC", "DNA", "DOC", "DPU", "DRC", "DSC", "DTB", "DTC", "DTD", "DTF", "DTL", "DTU", "DTV", "DWC", "DWP",
    "EAX", "EBD", "EBP", "EEB", "EEF", "ERS", "EVC", "EXC", "EXD", "EXL", "EXM", "EXP", "EXW", "FAH", "FDL",
    "FFR", "FLT", "FUE", "GST", "HAZ", "HDH", "HDW", "HET", "HHB", "HHG", "HOC", "HOL", "HRS", "IAC", "IDL",
    "IFC", "IHT", "IIA", "ILD", "ILP", "IMS", "INC", "INS", "IPU", "ISO", "IST", "LAA", "LAB", "LAY", "LDG",
    "LEC", "LFC", "LFT", "LGD", "LHS", "LOA", "LOC", "LPC", "LYC", "MAB", "MAC", "MIC", "MLS", "MMC", "MNC",
    "MRK", "MSC", "MSG", "NFY", "NYD", "NYP", "OAC", "ORM", "OUT", "OVR", "OWC", "PAV", "PCT", "PDS", "PDY",
    "PEC", "PER", "PLT", "PMS", "PMT", "POD", "PPC", "PPH", "PPN", "PPS", "PRK", "PSC", "PSH", "PUC", "PUD",
    "PUK", "RCC", "RCD", "RCL", "RDC", "REF", "REP", "RES", "RET", "RMC", "RRP", "SAB", "SAC", "SAE", "SAM",
    "SAT", "SCL", "SEC", "SEE", "SGL", "SHH", "SHL", "SLP", "SOC", "SOR", "SPT", "SRG", "SSF", "STD", "STP",
    "STR", "SWC", "TAR", "TDT", "TER", "TOA", "TOC", "TTU", "UND", "UNL", "URC", "VFN", "VOR", "WEI", "WRC",
    "WTG", "WTV",
}

APPENDIX_B_RATE_QUALIFIERS = {
    "AD", "BL", "C5", "CF", "CO", "CS", "CT", "CW", "DV", "ER", "FA", "FC", "FF", "FI", "FL", "FR", "FT", "FV",
    "GT", "HM", "HX", "IM", "IN", "LA", "LB", "LI", "LP", "LS", "LV", "MA", "MB", "MC", "MD", "ME", "MF", "MG",
    "MH", "MI", "MN", "MO", "MP", "MR", "MS", "MT", "MV", "MW", "MX", "ND", "NM", "NP", "NV", "OS", "OT", "P9",
    "PD", "PE", "PF", "PH", "PI", "PL", "PM", "PN", "PP", "PR", "PS", "PT", "PU", "PV", "PW", "PX", "PY", "PZ",
    "RB", "RC", "RP", "RT", "SP", "VA", "VH", "VT", "WK", "WM", "XP",
}

DEFAULT_STRICT_ENTERPRISE_PROFILE = False


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

    first_seg = edi_content.split("~")[0].split("\n")[0].strip()
    if first_seg.startswith("ISA") and "*" in first_seg:
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
    """X12 element index: 01=seg[1], 02=seg[2], ..."""
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
    # HHMMSSD (tenths) or HHMMSSDD (hundredths)
    if re.fullmatch(r"\d{7}", value or ""):
        hh, mm, ss = int(value[:2]), int(value[2:4]), int(value[4:6])
        return 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59
    if re.fullmatch(r"\d{8}", value or ""):
        hh, mm, ss = int(value[:2]), int(value[2:4]), int(value[4:6])
        return 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59
    return False


def is_number(value: str) -> bool:
    return bool(re.fullmatch(r"-?\d+(\.\d+)?", value or ""))


def is_integer(value: str) -> bool:
    return bool(re.fullmatch(r"-?\d+", value or ""))


def is_n0(value: str) -> bool:
    """X12 N0: integer without decimal point."""
    return bool(re.fullmatch(r"\d+", value or ""))


def is_n2(value: str) -> bool:
    """X12 N2: integer with implied 2 decimals (optional leading minus)."""
    return bool(re.fullmatch(r"-?\d+", value or ""))


def n2_to_decimal(value: str) -> float:
    return int(value) / 100.0


def is_valid_country(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{2,3}", value or ""))


def is_placeholder(value: str) -> bool:
    return (value or "").strip().upper() in {"X", "XX", "XXX", "N/A", "NA", "TBD"}


def parse_amount_relaxed(value: str) -> Optional[float]:
    """
    Parse amount for cross-checking.
    - Prefer X12 N2 interpretation (integer with implied 2 decimals)
    - Fall back to decimal numeric parsing for non-compliant payloads, so we can still detect mismatches
    """
    if is_n2(value):
        return n2_to_decimal(value)
    if is_number(value):
        return float(value)
    return None


def has_value(seg: List[str], idx: int) -> bool:
    return bool(elem(seg, idx))


def validate_edi_210(
    edi_content: str,
    expected_204: Optional[Dict[str, str]] = None,
    strict_profile: bool = DEFAULT_STRICT_ENTERPRISE_PROFILE,
) -> List[Dict[str, Any]]:
    errors: List[ValidationError] = []
    segments, _, _ = parse_edi(edi_content)

    def add_error(code: str, segment: str, element: str, message: str, severity: str = "Error") -> None:
        errors.append(ValidationError(code, segment, element, severity, message))

    if not segments:
        return [ValidationError("E001", "ISA", "ISA", "Error", "ISA missing").to_dict()]

    segment_ids = [s[0] for s in segments if s]
    isa_list = get_segments(segments, "ISA")
    iea_list = get_segments(segments, "IEA")
    gs_list = get_segments(segments, "GS")
    ge_list = get_segments(segments, "GE")
    st_list = get_segments(segments, "ST")
    se_list = get_segments(segments, "SE")
    n9_list = get_segments(segments, "N9")
    s5_list = get_segments(segments, "S5")
    lx_all = get_segments(segments, "LX")

    if len(n9_list) > 300:
        add_error("E910", "N9", "N9", "N9 max use exceeded (max 300)")
    if len(s5_list) > 999:
        add_error("E910", "S5", "S5", "S5 loop max use exceeded (max 999)")
    if len(lx_all) > 9999:
        add_error("E910", "LX", "LX", "LX loop max use exceeded (max 9999)")

    # 1) Envelope validation
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
        if elem(isa, 1) != "00":
            add_error("E003", "ISA", "ISA01", "ISA01 must be 00")
        if elem(isa, 3) != "00":
            add_error("E003", "ISA", "ISA03", "ISA03 must be 00")
        if elem(isa, 5) not in {"02", "ZZ"}:
            add_error("E003", "ISA", "ISA05", "ISA05 must be 02 or ZZ")
        if elem(isa, 7) not in {"01", "ZZ"}:
            add_error("E003", "ISA", "ISA07", "ISA07 must be 01 or ZZ")
        if elem(isa, 11) != "U":
            add_error("E003", "ISA", "ISA11", "ISA11 must be U")
        if elem(isa, 12) != "00401":
            add_error("E003", "ISA", "ISA12", "ISA12 must be 00401")
        if not re.fullmatch(r"\d{9}", elem(isa, 13) or ""):
            add_error("E003", "ISA", "ISA13", "ISA13 must be 9-digit numeric control number")
        if elem(isa, 14) not in {"0", "1"}:
            add_error("E003", "ISA", "ISA14", "ISA14 must be 0 or 1")
        if elem(isa, 15) != "P":
            add_error("E003", "ISA", "ISA15", "ISA15 must be P")
        if elem(isa, 16) and elem(isa, 16) != ">":
            add_error("E003", "ISA", "ISA16", "ISA16 is recommended to be > for BluJay", severity="Warning")

    if iea and isa:
        if is_integer(elem(iea, 1)) and int(elem(iea, 1)) != len(gs_list):
            add_error("E004", "IEA", "IEA01", "IEA01 must equal number of GS groups")
        if elem(iea, 2) != elem(isa, 13):
            add_error("E004", "IEA", "IEA02", "IEA02 must equal ISA13")

    # 2) GS / GE
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
        if elem(gs, 1) != "IM":
            add_error("E010", "GS", "GS01", "GS01 must be IM")
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
        if elem(gs, 8) != "004010":
            add_error("E011", "GS", "GS08", "GS08 must be 004010")
    if ge and gs:
        if is_integer(elem(ge, 1)) and int(elem(ge, 1)) != len(st_list):
            add_error("E012", "GE", "GE01", "GE01 must equal ST/SE transaction count")
        if elem(ge, 2) != elem(gs, 6):
            add_error("E012", "GE", "GE02", "GE02 must equal GS06")

    # 3) ST / SE
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
        if elem(st_seg, 1) != "210":
            add_error("E020", "ST", "ST01", "ST01 must be 210")
        if not elem(st_seg, 2):
            add_error("E021", "ST", "ST02", "ST02 required")
        elif not (4 <= len(elem(st_seg, 2)) <= 9):
            add_error("E021", "ST", "ST02", "ST02 length must be 4-9")

        matching_se_idx = None
        for idx in se_indices:
            if idx > st_idx:
                matching_se_idx = idx
                break
        if matching_se_idx is None:
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

    # 4) Required structure and sequence
    required_segments = ["B3", "C3", "LX", "L3"]
    for seg_id in required_segments:
        if seg_id not in segment_ids:
            code = "E100" if seg_id == "B3" else "E110" if seg_id == "C3" else "E300" if seg_id == "LX" else "E400"
            add_error(code, seg_id, seg_id, f"{seg_id} segment required")
    if "B3" in segment_ids and "LX" in segment_ids:
        if segment_ids.index("B3") > segment_ids.index("LX"):
            add_error("E100", "B3", "B3", "B3 must appear before first LX")

    # 5) B3
    b3_list = get_segments(segments, "B3")
    if not b3_list:
        add_error("E100", "B3", "B3", "B3 missing")
    else:
        b3 = b3_list[0]
        if not elem(b3, 2):
            add_error("E101", "B3", "B302", "B302 invoice number required")
        elif not (1 <= len(elem(b3, 2)) <= 22):
            add_error("E101", "B3", "B302", "B302 length must be 1-22")
        if not elem(b3, 3):
            add_error("E102", "B3", "B303", "B303 shipment id required")
        if is_placeholder(elem(b3, 3)):
            add_error("E107", "B3", "B303", "B303 cannot be placeholder value (e.g. X/XX)")
        if elem(b3, 3) and not (1 <= len(elem(b3, 3)) <= 30):
            add_error("E102", "B3", "B303", "B303 length must be 1-30")
        if elem(b3, 3) and not re.fullmatch(r"[A-Za-z0-9_-]+", elem(b3, 3)):
            add_error("E107", "B3", "B303", "B303 contains blanks or special characters")

        if elem(b3, 4) not in {"CC", "PP"}:
            add_error("E103", "B3", "B304", "B304 must be CC or PP")

        if elem(b3, 8) and elem(b3, 8) not in {"BD", "CO"}:
            add_error("E103", "B3", "B308", "B308 must be BD or CO when present")

        if not is_valid_date(elem(b3, 6)):
            add_error("E104", "B3", "B306", "B306 invalid date")

        if not is_n2(elem(b3, 7)):
            add_error("E105", "B3", "B307", "B307 invalid amount (must be N2 integer with implied decimals)")

        if not elem(b3, 11):
            add_error("E106", "B3", "B311", "B311 SCAC required")
        elif not (2 <= len(elem(b3, 11)) <= 4):
            add_error("E106", "B3", "B311", "B311 SCAC length must be 2-4")

        for i, label in ((1, "B301"), (5, "B305"), (9, "B309"), (10, "B310"), (12, "B312"), (13, "B313"), (14, "B314")):
            if has_value(b3, i):
                add_error("E901", "B3", label, f"{label} is not used in BluJay profile and should be blank")

        if expected_204:
            b204 = expected_204.get("B204", "")
            b202 = expected_204.get("B202", "")
            if b204 and elem(b3, 3) != b204:
                add_error("E500", "B3", "B303", "B303 shipment id mismatch to 204 B204")
            if b202 and elem(b3, 11) != b202:
                add_error("E501", "B3", "B311", "B311 SCAC mismatch to 204 B202")

    # 6) C3
    valid_currency = {"USD", "CAD", "MXN", "EUR"}
    c3_list = get_segments(segments, "C3")
    if not c3_list:
        add_error("E110", "C3", "C3", "C3 segment required")
    else:
        c3 = c3_list[0]
        if not elem(c3, 1):
            add_error("E111", "C3", "C301", "C301 currency code required")
        elif elem(c3, 1) not in valid_currency:
            add_error("E112", "C3", "C301", "C301 invalid currency")

    # 7) N9
    mb_exists = False
    po_exists = False
    for n9 in n9_list:
        if not elem(n9, 1):
            add_error("E120", "N9", "N901", "N901 required")
        if not elem(n9, 2) and not elem(n9, 3):
            add_error("E121", "N9", "N902/N903", "N9 reference value required")
        for i, label in ((3, "N903"), (4, "N904"), (5, "N905"), (6, "N906"), (7, "N907")):
            if has_value(n9, i):
                add_error("E920", "N9", label, f"{label} is not used in BluJay profile and should be blank")
        if elem(n9, 1) == "PO" and is_placeholder(elem(n9, 2)):
            add_error("E121", "N9", "N902", "PO reference cannot be placeholder value (e.g. X/XX)")
        if elem(n9, 1) == "MB":
            mb_exists = True
        if elem(n9, 1) == "PO":
            po_exists = True
    if not mb_exists:
        if strict_profile:
            add_error("E122", "N9", "N901", "Required reference MB missing")
        else:
            add_error("E122", "N9", "N901", "Recommended reference MB missing", severity="Warning")
    if not po_exists:
        if strict_profile:
            add_error("E123", "N9", "N901", "Required reference PO missing")
        else:
            add_error("E123", "N9", "N901", "Recommended reference PO missing", severity="Warning")

    # 8) Heading N1 loop (before first S5/LX)
    first_detail_idx = len(segments)
    for i, s in enumerate(segments):
        if s and s[0] in {"S5", "LX"}:
            first_detail_idx = i
            break
    heading_segments = segments[:first_detail_idx]
    heading_n1_indices = [i for i, s in enumerate(heading_segments) if s and s[0] == "N1"]
    heading_n1 = [heading_segments[i] for i in heading_n1_indices]
    if not heading_n1:
        add_error("E130", "N1", "N1", "At least one heading N1 loop required")
    if len(heading_n1) > 10:
        add_error("E910", "N1", "N1", "Heading N1 loop max use exceeded (max 10)")
    if not any(elem(n1, 1) == "SH" for n1 in heading_n1):
        add_error("E130", "N1", "N101", "N1*SH missing")

    for i in heading_n1_indices:
        n1 = heading_segments[i]
        n102 = elem(n1, 2)
        n103 = elem(n1, 3)
        n104 = elem(n1, 4)
        if not n102 and not (n103 and n104):
            add_error("E131", "N1", "N102/N103/N104", "N1 requires N102 or N103/N104")
        if (n103 and not n104) or (n104 and not n103):
            add_error("E132", "N1", "N103/N104", "N103 and N104 must appear together")

        # N3 / N4 checks in same N1 loop
        j = i + 1
        n3_count = 0
        n4_count = 0
        n4_seg: Optional[List[str]] = None
        while j < len(heading_segments) and heading_segments[j] and heading_segments[j][0] not in {"N1", "S5", "LX"}:
            if heading_segments[j][0] == "N3":
                n3_count += 1
                if not elem(heading_segments[j], 1):
                    add_error("E133", "N3", "N301", "N3 required address line missing")
            if heading_segments[j][0] == "N4":
                n4_count += 1
                n4_seg = heading_segments[j]
            j += 1
        if n3_count > 2:
            add_error("E910", "N3", "N3", "Heading N3 max use exceeded (max 2)")
        if n4_count > 1:
            add_error("E910", "N4", "N4", "Heading N4 max use exceeded (max 1)")
        if n4_seg and elem(n4_seg, 4) and not is_valid_country(elem(n4_seg, 4)):
            add_error("E134", "N4", "N404", "Invalid country code")

    # 9) S5/G62/0310 stop loop checks
    stops: List[Dict[str, Any]] = []
    current_stop: Optional[Dict[str, Any]] = None
    for i, seg in enumerate(segments):
        if not seg:
            continue
        sid = seg[0]
        if sid == "S5":
            if current_stop:
                stops.append(current_stop)
            current_stop = {
                "index": i,
                "seq": elem(seg, 1),
                "reason": elem(seg, 2),
                "has_sf": False,
                "has_st": False,
                "has_location_n1": False,
                "has_location_n3": False,
                "date_quals": set(),
                "time_quals": set(),
                "g62_count": 0,
                "n1_count": 0,
            }
        elif sid in {"LX", "L3", "SE"}:
            if current_stop:
                stops.append(current_stop)
                current_stop = None
        elif current_stop and sid == "G62":
            current_stop["g62_count"] += 1
            dqual = elem(seg, 1)
            dval = elem(seg, 2)
            tqual = elem(seg, 3)
            tval = elem(seg, 4)
            tz = elem(seg, 5)
            if (dqual and not dval) or (dval and not dqual):
                add_error("E210", "G62", "G6201/G6202", "G62 date qualifier/date must appear together")
            if (tqual and not tval) or (tval and not tqual):
                add_error("E211", "G62", "G6203/G6204", "G62 time qualifier/time must appear together")
            if dqual and dqual not in {"35", "86"}:
                add_error("E212", "G62", "G6201", "Invalid G62 date qualifier")
            if tqual and tqual not in {"8", "9"}:
                add_error("E213", "G62", "G6203", "Invalid G62 time qualifier")
            if dval and not is_valid_date(dval):
                add_error("E210", "G62", "G6202", "G62 date must be CCYYMMDD")
            if tval and not is_valid_time(tval):
                add_error("E211", "G62", "G6204", "G62 time invalid")
            if tz and tz not in {"CD", "CT", "ED", "ET", "MD", "MT", "PD", "PT"}:
                add_error("E214", "G62", "G6205", "Invalid time zone code")
            if dqual:
                current_stop["date_quals"].add(dqual)
            if tqual:
                current_stop["time_quals"].add(tqual)
        elif current_stop and sid == "N1":
            current_stop["n1_count"] += 1
            n101 = elem(seg, 1)
            n102 = elem(seg, 2)
            n103 = elem(seg, 3)
            n104 = elem(seg, 4)
            current_stop["has_location_n1"] = True

            if n101 not in {"SF", "ST"}:
                add_error("E220", "N1", "N101", "N1 in 0310 must be SF or ST")
            if not n102 and not (n103 and n104):
                add_error("E220", "N1", "N102/N103/N104", "Stop N1 requires N102 or N103/N104")

            if n101 == "SF":
                current_stop["has_sf"] = True
            if n101 == "ST":
                current_stop["has_st"] = True

            # N3 required in 0310 loop
            if i + 1 < len(segments) and segments[i + 1] and segments[i + 1][0] == "N3" and elem(segments[i + 1], 1):
                current_stop["has_location_n3"] = True
            else:
                add_error("E221", "N3", "N3", "N3 required in 0310 loop")
            # N4 country code if present
            if i + 2 < len(segments) and segments[i + 2] and segments[i + 2][0] == "N4":
                n4 = segments[i + 2]
                if elem(n4, 4) and not is_valid_country(elem(n4, 4)):
                    add_error("E134", "N4", "N404", "Invalid country code")

    if current_stop:
        stops.append(current_stop)

    # S5 core validations
    if stops:
        stop_seq_seen = set()
        stop_seq_values: List[int] = []
        has_ld = False
        has_ul = False
        for stop in stops:
            if not stop["seq"]:
                add_error("E200", "S5", "S501", "S5 sequence number required")
            elif stop["seq"] in stop_seq_seen:
                add_error("E202", "S5", "S501", "Duplicate stop sequence")
            else:
                stop_seq_seen.add(stop["seq"])
                if is_integer(stop["seq"]):
                    stop_seq_values.append(int(stop["seq"]))
            if stop["reason"] not in {"LD", "UL"}:
                add_error("E201", "S5", "S502", "S5 stop reason must be LD or UL")
            if stop["reason"] == "LD":
                has_ld = True
            if stop["reason"] == "UL":
                has_ul = True
            if not stop["has_location_n1"] and stop["g62_count"] > 0:
                add_error(
                    "E222",
                    "N1",
                    "N1",
                    "Stop location missing for G62 status detail",
                    severity="Error" if strict_profile else "Warning",
                )
            if stop["reason"] == "LD" and not stop["has_sf"] and stop["g62_count"] > 0:
                add_error(
                    "E223",
                    "N1",
                    "N101",
                    "Pickup stop should use SF when G62 actual pickup status is sent",
                    severity="Error" if strict_profile else "Warning",
                )
            if stop["reason"] == "UL" and not stop["has_st"] and stop["g62_count"] > 0:
                add_error(
                    "E224",
                    "N1",
                    "N101",
                    "Delivery stop should use ST when G62 actual delivery status is sent",
                    severity="Error" if strict_profile else "Warning",
                )
            if stop["g62_count"] > 10:
                add_error("E910", "G62", "G62", "G62 max use exceeded in S5 loop (max 10)")
            if stop["n1_count"] > 2:
                add_error("E910", "N1", "N1", "0310 N1 loop max use exceeded (max 2)")
            if stop["g62_count"] == 0:
                add_error(
                    "E210",
                    "G62",
                    "G62",
                    "G62 required in each S5 loop by strict profile"
                    if strict_profile
                    else "G62 is recommended in each S5 loop and may be required by shipper invoice validation settings",
                    severity="Error" if strict_profile else "Warning",
                )

        if stop_seq_values and stop_seq_values != sorted(stop_seq_values):
            add_error("E202", "S5", "S501", "Stop sequence should be increasing")
        if not (has_ld and has_ul):
            add_error("E203", "S5", "S502", "Missing load or unload stop")
    else:
        add_error(
            "E203",
            "S5",
            "S5",
            "S5 stop loops required by strict profile"
            if strict_profile
            else "S5 stop loops are recommended and may be required by shipper invoice validation settings",
            severity="Error" if strict_profile else "Warning",
        )

    # 10) LX / L0 / L1 / L7 / K1 / SPO / 0460
    lx_indices = [i for i, s in enumerate(segments) if s and s[0] == "LX"]
    l1_segments: List[List[str]] = []
    l1_l104_sum = 0.0
    last_lx = 0

    for pos, lx_idx in enumerate(lx_indices):
        lx = segments[lx_idx]
        lx01 = elem(lx, 1)
        if not lx01:
            add_error("E300", "LX", "LX01", "LX01 required")
        elif not is_integer(lx01) or int(lx01) <= 0:
            add_error("E300", "LX", "LX01", "LX01 must be positive integer")
        else:
            lx_num = int(lx01)
            if lx_num <= last_lx:
                add_error("E301", "LX", "LX01", "LX01 should be unique and increasing")
            last_lx = max(last_lx, lx_num)

        next_boundary = len(segments)
        for b in lx_indices[pos + 1:]:
            if b > lx_idx:
                next_boundary = b
                break
        for i in range(lx_idx + 1, len(segments)):
            if segments[i] and segments[i][0] in {"L3", "SE"}:
                next_boundary = min(next_boundary, i)
                break
        lx_body = segments[lx_idx + 1:next_boundary]
        l0_list = [s for s in lx_body if s and s[0] == "L0"]
        l1_list = [s for s in lx_body if s and s[0] == "L1"]
        l7_list = [s for s in lx_body if s and s[0] == "L7"]
        k1_list = [s for s in lx_body if s and s[0] == "K1"]
        spo_indices = [i for i, s in enumerate(lx_body) if s and s[0] == "SPO"]

        if len(l0_list) > 1:
            add_error("E311", "L0", "L0", "Each LX should have at most one L0")
        if len(l0_list) > 10:
            add_error("E910", "L0", "L0", "L0 max use exceeded in LX loop (max 10)")
        if len(l1_list) == 0:
            add_error("E321", "L1", "L1", "Each LX must contain one L1")
        if len(l1_list) > 1:
            add_error("E321", "L1", "L1", "Each LX should have at most one L1")
        if len(l1_list) > 10:
            add_error("E910", "L1", "L1", "L1 max use exceeded in LX loop (max 10)")
        if len(l7_list) > 10:
            add_error("E910", "L7", "L7", "L7 max use exceeded in LX loop (max 10)")
        if len(k1_list) > 10:
            add_error("E910", "K1", "K1", "K1 max use exceeded in LX loop (max 10)")

        if l0_list:
            l0 = l0_list[0]
            for i, label in ((1, "L001"), (6, "L006"), (7, "L007"), (10, "L010"), (11, "L011"), (12, "L012"), (13, "L013"), (14, "L014"), (15, "L015")):
                if has_value(l0, i):
                    add_error("E920", "L0", label, f"{label} is not used in BluJay profile and should be blank")
            if (elem(l0, 2) and not elem(l0, 3)) or (elem(l0, 3) and not elem(l0, 2)):
                add_error("E310", "L0", "L002/L003", "L002 and L003 must appear together")
            if (elem(l0, 4) and not elem(l0, 5)) or (elem(l0, 5) and not elem(l0, 4)):
                add_error("E311", "L0", "L004/L005", "L004 and L005 must appear together")
            if (elem(l0, 8) and not elem(l0, 9)) or (elem(l0, 9) and not elem(l0, 8)):
                add_error("E312", "L0", "L008/L009", "L008 and L009 must appear together")
            if elem(l0, 3) and elem(l0, 3) not in {"DM", "LB"}:
                add_error("E313", "L0", "L003", "Invalid L003 qualifier")
            if elem(l0, 5) and elem(l0, 5) not in {"B", "F", "G", "N", "T"}:
                add_error("E314", "L0", "L005", "Invalid L005 weight qualifier")
            if elem(l0, 8) and not is_n0(elem(l0, 8)):
                add_error("E312", "L0", "L008", "L008 lading quantity must be N0 integer")

        for l1 in l1_list:
            l1_segments.append(l1)
            l102 = elem(l1, 2)
            l103 = elem(l1, 3)
            l104 = elem(l1, 4)
            l105 = elem(l1, 5)
            l106 = elem(l1, 6)
            l108 = elem(l1, 8)
            l112 = elem(l1, 12)
            for i, label in (
                (1, "L101"), (7, "L107"), (9, "L109"), (10, "L110"), (11, "L111"),
                (13, "L113"), (14, "L114"), (15, "L115"), (16, "L116"), (17, "L117"),
                (18, "L118"), (19, "L119"), (20, "L120"), (21, "L121")
            ):
                if has_value(l1, i):
                    add_error("E920", "L1", label, f"{label} is not used in BluJay profile and should be blank")

            if (l102 and not l103) or (l103 and not l102):
                add_error("E320", "L1", "L102/L103", "L102 and L103 must appear together")
            if not (l104 or l105 or l106):
                add_error("E321", "L1", "L104/L105/L106", "One of L104/L105/L106 is required")
            if l103 and l103 not in APPENDIX_B_RATE_QUALIFIERS:
                add_error("E322", "L1", "L103", "Invalid L103 rate qualifier")
            if l108 and l108 not in APPENDIX_A_SPECIAL_CHARGE_CODES:
                add_error("E323", "L1", "L108", "Invalid L108 special charge code")
            if l108 == "999" and not l112:
                add_error("E324", "L1", "L112", "L112 required when L108=999")
            if l102 and not is_number(l102):
                add_error("E325", "L1", "L102", "Invalid charge rate")
            for value, pos_code in [(l104, "L104"), (l105, "L105"), (l106, "L106")]:
                if value and not is_n2(value):
                    add_error("E325", "L1", pos_code, "Invalid charge amount (must be N2 integer)")

            if l103 in {"PM", "CW"} and not l0_list:
                add_error("E315", "L0", "L0", "L0 required when L1 rate qualifier is PM or CW")

            parsed_l104 = parse_amount_relaxed(l104)
            if parsed_l104 is not None:
                l1_l104_sum += parsed_l104

        for l7 in l7_list:
            if elem(l7, 7) and not re.fullmatch(r"\d{1,2}(\.\d)?", elem(l7, 7)):
                add_error("E330", "L7", "L707", "Invalid freight class")

        for k1 in k1_list:
            if not elem(k1, 1):
                add_error("E340", "K1", "K101", "K101 required")
            elif len(elem(k1, 1)) > 30:
                add_error("E340", "K1", "K101", "K101 length must be <= 30")

        # SPO and 0460 loop checks inside LX body
        for spo_i in spo_indices:
            spo = lx_body[spo_i]
            for i, label in ((2, "SPO02"), (3, "SPO03"), (4, "SPO04"), (5, "SPO05"), (6, "SPO06"), (7, "SPO07"), (8, "SPO08")):
                if has_value(spo, i):
                    add_error("E920", "SPO", label, f"{label} is not used in BluJay profile and should be blank")
            if not elem(spo, 1):
                add_error("E350", "SPO", "SPO01", "SPO01 purchase order required")
            elif is_placeholder(elem(spo, 1)):
                add_error("E350", "SPO", "SPO01", "SPO01 purchase order cannot be placeholder value (e.g. X/XX)")
            elif not (1 <= len(elem(spo, 1)) <= 22):
                add_error("E350", "SPO", "SPO01", "SPO01 length must be 1-22")
            if (elem(spo, 3) and not elem(spo, 4)) or (elem(spo, 4) and not elem(spo, 3)):
                add_error("E351", "SPO", "SPO03/SPO04", "SPO03 and SPO04 must appear together")
            if (elem(spo, 5) and not elem(spo, 6)) or (elem(spo, 6) and not elem(spo, 5)):
                add_error("E352", "SPO", "SPO05/SPO06", "SPO05 and SPO06 must appear together")

            next_spo_boundary = len(lx_body)
            for k in range(spo_i + 1, len(lx_body)):
                if lx_body[k] and lx_body[k][0] in {"SPO", "L1", "LX", "L3", "SE"}:
                    next_spo_boundary = k
                    break
            line_location = lx_body[spo_i + 1:next_spo_boundary]
            for idx, s in enumerate(line_location):
                if not s or s[0] != "N1":
                    continue
                if elem(s, 1) not in {"SF", "ST"}:
                    add_error("E360", "N1", "N101", "0460 N1 must be SF or ST")
                if idx + 1 >= len(line_location) or not line_location[idx + 1] or line_location[idx + 1][0] != "N3":
                    add_error("E361", "N3", "N3", "0460 N3 required")

    # 11) L3 summary
    l3_list = get_segments(segments, "L3")
    for l3 in l3_list:
        for i, label in ((12, "L312"), (13, "L313"), (14, "L314"), (15, "L315")):
            if has_value(l3, i):
                add_error("E920", "L3", label, f"{label} is not used in BluJay profile and should be blank")
        if (elem(l3, 1) and not elem(l3, 2)) or (elem(l3, 2) and not elem(l3, 1)):
            add_error("E400", "L3", "L301/L302", "L301 and L302 must appear together")
        if (elem(l3, 3) and not elem(l3, 4)) or (elem(l3, 4) and not elem(l3, 3)):
            add_error("E401", "L3", "L303/L304", "L303 and L304 must appear together")
        if (elem(l3, 9) and not elem(l3, 10)) or (elem(l3, 10) and not elem(l3, 9)):
            add_error("E402", "L3", "L309/L310", "L309 and L310 must appear together")

        if elem(l3, 2) and elem(l3, 2) not in {"B", "F", "G", "N", "T"}:
            add_error("E403", "L3", "L302", "Invalid L302 weight qualifier")
        if elem(l3, 4) and elem(l3, 4) not in APPENDIX_B_RATE_QUALIFIERS:
            add_error("E404", "L3", "L304", "Invalid L304 rate qualifier")
        if elem(l3, 8) and elem(l3, 8) not in APPENDIX_A_SPECIAL_CHARGE_CODES:
            add_error("E405", "L3", "L308", "Invalid L308 special charge code")
        if elem(l3, 10) and elem(l3, 10) not in {"E", "X"}:
            add_error("E406", "L3", "L310", "Invalid L310 volume qualifier")
        if elem(l3, 11) and not is_n0(elem(l3, 11)):
            add_error("E406", "L3", "L311", "L311 lading quantity must be N0 integer")

        if elem(l3, 5):
            parsed_l3_total = parse_amount_relaxed(elem(l3, 5))
            if not is_n2(elem(l3, 5)):
                add_error("E407", "L3", "L305", "L305 total charge must be N2 integer with implied decimals")
            if parsed_l3_total is not None:
                l3_total = parsed_l3_total
                if abs(l3_total - l1_l104_sum) > 0.01:
                    add_error(
                        "E407",
                        "L3",
                        "L305",
                        f"L305 total charge does not equal sum of L1 charges (L305={l3_total}, L1 sum={l1_l104_sum})",
                    )

    # Charge line existence
    if not l1_segments:
        add_error("E530", "L1", "L1", "No charge lines found")

    return [e.to_dict() for e in errors]


def main() -> None:
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    else:
        content = sys.stdin.read()

    print(json.dumps(validate_edi_210(content), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
