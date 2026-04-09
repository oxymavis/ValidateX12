#!/usr/bin/env python3
"""
Strict field-level 856 validation for four trading-partner specs:
  - Amazon Retail 856 V5010 (Amazon_856.pdf)
  - Delhaize America DSD 856 V5010 (Delhaize_America_856_v5010_DSD.pdf — structural rules; PDF is scan-light)
  - Fleet Farm 856 v4010 (Fleet Farm_856.xls)
  - Burlington Stores 856 X12 4010 (Burlington Stores_856_specifications_13nov17.pdf — envelope + common ST)

Each finding: partner, spec_ref, code, segment, element, severity, message.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

# ---------------------------------------------------------------------------
# EDI helpers (element index = X12 1-based → list index)
# ---------------------------------------------------------------------------


def parse_edi(content: str) -> List[List[str]]:
    content = content.strip().replace("~\n", "~").replace("\n", "~")
    if not content:
        return []
    return [s.split("*") for s in content.split("~") if s.strip()]


def elem(seg: List[str], i: int) -> str:
    if i <= 0 or i >= len(seg):
        return ""
    return (seg[i] or "").strip()


def raw_elem(seg: List[str], i: int) -> str:
    if i <= 0 or i >= len(seg):
        return ""
    return seg[i] or ""


def get_seg(segs: List[List[str]], tag: str) -> List[List[str]]:
    return [s for s in segs if s and s[0] == tag]


def is_ccyymmdd(s: str) -> bool:
    if not re.fullmatch(r"\d{8}", s or ""):
        return False
    try:
        datetime.strptime(s, "%Y%m%d")
        return True
    except ValueError:
        return False


def is_int(s: str) -> bool:
    return bool(re.fullmatch(r"-?\d+", s or ""))


@dataclass
class Finding:
    partner: str
    spec_ref: str
    code: str
    segment: str
    element: str
    severity: str
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "partner": self.partner,
            "spec_ref": self.spec_ref,
            "code": self.code,
            "segment": self.segment,
            "element": self.element,
            "severity": self.severity,
            "message": self.message,
        }


def add(
    out: List[Finding],
    partner: str,
    spec: str,
    code: str,
    seg: str,
    el: str,
    msg: str,
    sev: str = "Error",
) -> None:
    out.append(Finding(partner, spec, code, seg, el, sev, msg))


# --- shared envelope ---


def check_envelope_common(
    out: List[Finding],
    partner: str,
    spec: str,
    segments: List[List[str]],
    *,
    expect_isa12: str,
    expect_gs08: str,
    expect_gs01: str,
    gs03_allow: Optional[Set[str]] = None,
) -> None:
    isa = get_seg(segments, "ISA")
    gs = get_seg(segments, "GS")
    ge = get_seg(segments, "GE")
    iea = get_seg(segments, "IEA")
    st = get_seg(segments, "ST")
    se = get_seg(segments, "SE")

    if not isa:
        add(out, partner, spec, "ENV001", "ISA", "", "ISA missing")
        return
    i = isa[0]
    if elem(i, 12) != expect_isa12:
        add(out, partner, spec, "ENV002", "ISA", "ISA12", f"ISA12 must be {expect_isa12} (got {elem(i, 12)!r})")
    if len(raw_elem(i, 6)) != 15:
        add(out, partner, spec, "ENV003", "ISA", "ISA06", "ISA06 must be 15 characters")
    if len(raw_elem(i, 8)) != 15:
        add(out, partner, spec, "ENV004", "ISA", "ISA08", "ISA08 must be 15 characters")

    if gs:
        g = gs[0]
        if elem(g, 1) != expect_gs01:
            add(
                out,
                partner,
                spec,
                "ENV010",
                "GS",
                "GS01",
                f"Spec requires GS01={expect_gs01!r} (856 Ship Notice); got {elem(g, 1)!r}",
            )
        if elem(g, 8) != expect_gs08:
            add(out, partner, spec, "ENV011", "GS", "GS08", f"GS08 must be {expect_gs08!r} (got {elem(g, 8)!r})")
        if gs03_allow is not None and elem(g, 3) not in gs03_allow:
            add(
                out,
                partner,
                spec,
                "ENV012",
                "GS",
                "GS03",
                f"GS03 receiver ID {elem(g, 3)!r} not in allowed set for this partner",
            )
    if gs and ge:
        if elem(ge[0], 2) != elem(gs[0], 6):
            add(out, partner, spec, "ENV013", "GE", "GE02", "GE02 must equal GS06")
    if isa and iea and elem(iea[0], 2) != elem(i, 13):
        add(out, partner, spec, "ENV014", "IEA", "IEA02", "IEA02 must equal ISA13")

    st_i = next((x for x, s in enumerate(segments) if s and s[0] == "ST"), None)
    se_i = next((x for x, s in enumerate(segments) if s and s[0] == "SE"), None)
    if st_i is not None and se_i is not None and st and se:
        if elem(se[0], 2) != elem(st[0], 2):
            add(out, partner, spec, "ENV015", "SE", "SE02", "SE02 must equal ST02")
        if is_int(elem(se[0], 1)):
            exp = int(elem(se[0], 1))
            act = se_i - st_i + 1
            if exp != act:
                add(
                    out,
                    partner,
                    spec,
                    "ENV016",
                    "SE",
                    "SE01",
                    f"SE01 count: stated {exp}, actual segments ST..SE inclusive = {act}",
                )


# ============== Amazon (Amazon_856.pdf) ==============


def validate_amazon(segments: List[List[str]]) -> List[Finding]:
    out: List[Finding] = []
    P, S = "Amazon", "Amazon_856.pdf Retail V5010"
    check_envelope_common(
        out, P, S, segments, expect_isa12="00501", expect_gs08="005010", expect_gs01="SH", gs03_allow={"AMAZON"}
    )

    st_i = next((i for i, s in enumerate(segments) if s and s[0] == "ST"), None)
    se_i = next((i for i, s in enumerate(segments) if s and s[0] == "SE"), None)
    if st_i is None or se_i is None:
        add(out, P, S, "AMZ010", "ST", "", "ST/SE missing")
        return out
    body = segments[st_i + 1 : se_i]

    bsn = next((s for s in body if s and s[0] == "BSN"), None)
    if bsn:
        if elem(bsn, 4) and not re.fullmatch(r"\d{6}", elem(bsn, 4)):
            add(out, P, S, "AMZ101", "BSN", "BSN04", "BSN04 time must be HHMMSS (6 digits)", "Error")
        if elem(bsn, 5) and elem(bsn, 5) != "0001":
            add(out, P, S, "AMZ102", "BSN", "BSN05", "BSN05 hierarchical code expected 0001 for SOTPI", "Warning")

    dtm_quals = {elem(d, 1) for d in body if d and d[0] == "DTM"}
    if "011" not in dtm_quals:
        add(out, P, S, "AMZ110", "DTM", "DTM01", "Mandatory DTM*011* (Shipped) missing")
    if "017" not in dtm_quals:
        add(out, P, S, "AMZ111", "DTM", "DTM01", "Mandatory DTM*017* (Estimated delivery) missing")

    if get_seg(body, "TD3"):
        add(out, P, S, "AMZ120", "TD3", "", "TD3 only for import ASNs — not domestic (spec segment usage)", "Warning")

    for n4 in get_seg(body, "N4"):
        if elem(n4, 4) == "USA":
            add(out, P, S, "AMZ130", "N4", "N404", "N404 must be ISO 3166-1 alpha-2 (use US not USA)", "Warning")

    item_hl = [i for i, s in enumerate(body) if s and s[0] == "HL" and elem(s, 3) == "I"]
    for hi in item_hl:
        end = next((j for j in range(hi + 1, len(body)) if body[j] and body[j][0] == "HL"), len(body))
        chunk = body[hi:end]
        lin = next((x for x in chunk if x and x[0] == "LIN"), None)
        sn1 = next((x for x in chunk if x and x[0] == "SN1"), None)
        if lin and sn1:
            l1, s1 = elem(lin, 1), elem(sn1, 1)
            if l1 and not s1:
                add(out, P, S, "AMZ201", "SN1", "SN101", f"SN101 must equal LIN01 ({l1!r}) — empty", "Error")
            elif l1 and s1 and l1 != s1:
                add(out, P, S, "AMZ202", "SN1", "SN101", f"SN101 ({s1!r}) must match LIN01 ({l1!r})", "Error")
            if elem(sn1, 2) and not elem(sn1, 3):
                add(out, P, S, "AMZ203", "SN1", "SN103", "SN103 unit of measure (EA/CA) required when SN102 present", "Warning")

    return out


# ============== Delhaize DSD (Delhaize PDF + same envelope as partner file) ==============


def validate_delhaize(segments: List[List[str]]) -> List[Finding]:
    out: List[Finding] = []
    P, S = "Delhaize", "Delhaize_America_856_v5010_DSD.pdf (V5010 DSD — PDF text minimal; rules per Retail 5010 + message profile)"
    check_envelope_common(
        out,
        P,
        S,
        segments,
        expect_isa12="00501",
        expect_gs08="005010",
        expect_gs01="SH",
        gs03_allow={"540011000"},  # GS03 in sample
    )

    st_i = next((i for i, s in enumerate(segments) if s and s[0] == "ST"), None)
    se_i = next((i for i, s in enumerate(segments) if s and s[0] == "SE"), None)
    if st_i is None or se_i is None:
        return out
    body = segments[st_i + 1 : se_i]

    joined = "~".join("*".join(s) for s in body)
    if "DELHAIZE" not in joined.upper():
        add(out, P, S, "DZH010", "N1", "", "Expected Delhaize/Ahold party (e.g. N1*SO*DELHAIZE AMERICA)", "Warning")

    bsn = next((s for s in body if s and s[0] == "BSN"), None)
    if bsn and elem(bsn, 4) and not re.fullmatch(r"\d{6}", elem(bsn, 4)):
        add(out, P, S, "DZH101", "BSN", "BSN04", "BSN04 should be HHMMSS (6 digits) per X12 time", "Error")

    if "011" not in {elem(d, 1) for d in body if d and d[0] == "DTM"}:
        add(out, P, S, "DZH110", "DTM", "", "Ship date DTM*011* recommended/mandatory for ASN", "Warning")

    for n4 in get_seg(body, "N4"):
        if elem(n4, 4) == "USA":
            add(out, P, S, "DZH130", "N4", "N404", "Prefer ISO country code US not USA", "Warning")

    # Item SN101 = LIN01 (same as Amazon retail practice)
    for i, s in enumerate(body):
        if s and s[0] == "HL" and elem(s, 3) == "I":
            end = next((j for j in range(i + 1, len(body)) if body[j] and body[j][0] == "HL"), len(body))
            chunk = body[i:end]
            lin = next((x for x in chunk if x and x[0] == "LIN"), None)
            sn1 = next((x for x in chunk if x and x[0] == "SN1"), None)
            if lin and sn1 and elem(lin, 1) and not elem(sn1, 1):
                add(out, P, S, "DZH201", "SN1", "SN101", f"SN101 should repeat LIN01 ({elem(lin, 1)!r})", "Error")

    return out


# ============== Fleet Farm (Fleet Farm_856.xls) ==============


def validate_fleet_farm(segments: List[List[str]]) -> List[Finding]:
    out: List[Finding] = []
    P, S = "Fleet Farm", "Fleet Farm_856.xls v4010"
    check_envelope_common(
        out,
        P,
        S,
        segments,
        expect_isa12="00401",
        expect_gs08="004010",
        expect_gs01="SH",
        gs03_allow={"4147318121"},
    )

    st_i = next((i for i, s in enumerate(segments) if s and s[0] == "ST"), None)
    se_i = next((i for i, s in enumerate(segments) if s and s[0] == "SE"), None)
    if st_i is None or se_i is None:
        return out
    body = segments[st_i + 1 : se_i]

    # PER*CE* — M at shipment per xls
    if not any(s and s[0] == "PER" for s in body):
        add(out, P, S, "FF010", "PER", "", "Mandatory PER*CE* (supplier contact) not found in transaction (xls: M)", "Error")

    # TD5: TD502 = 2 (SCAC)
    td5 = next((s for s in body if s and s[0] == "TD5"), None)
    if td5 and elem(td5, 2) != "2":
        add(out, P, S, "FF020", "TD5", "TD502", f"TD502 must be '2' (SCAC ID qual.); got {elem(td5, 2)!r}")

    # REF: at least one of BM, MA, CF, CN, 2I — file has BM+CN
    ref1 = {elem(r, 1) for r in body if r and r[0] == "REF"}
    allowed_ref = {"BM", "MA", "CF", "CN", "2I"}
    if not ref1.intersection(allowed_ref):
        add(out, P, S, "FF030", "REF", "", "At least one REF in BM/MA/CF/CN/2I required per xls")

    # Shipment N1*ST: N103=92, N104 store id (xls)
    # Find first N1*ST before Order HL
    hl_o = next((i for i, s in enumerate(body) if s and s[0] == "HL" and elem(s, 3) == "O"), len(body))
    for i, s in enumerate(body):
        if i >= hl_o:
            break
        if s and s[0] == "N1" and elem(s, 1) == "ST":
            if elem(s, 3) != "92":
                add(
                    out,
                    P,
                    S,
                    "FF040",
                    "N1",
                    "N103",
                    f"Shipment N1*ST requires N103=92 (Assigned by Buyer); got {elem(s, 3)!r}",
                    "Error",
                )
            if not elem(s, 4):
                add(out, P, S, "FF041", "N1", "N104", "N104 Ship-To location/store ID required when N103=92", "Error")

    # PRF: PO date PRF04 (xls M04)
    prf = next((s for s in body if s and s[0] == "PRF"), None)
    if prf and not elem(prf, 4):
        add(out, P, S, "FF050", "PRF", "PRF04", "PRF04 PO Date mandatory per Fleet Farm xls", "Warning")

    # Order-level REF*IA* vendor number (xls M after PRF)
    hl_o_idx = next((i for i, s in enumerate(body) if s and s[0] == "HL" and elem(s, 3) == "O"), None)
    if hl_o_idx is not None:
        hl_t_idx = next(
            (i for i, s in enumerate(body) if i > hl_o_idx and s and s[0] == "HL" and elem(s, 3) in {"P", "T"}),
            len(body),
        )
        order_slice = body[hl_o_idx:hl_t_idx]
        has_ia = any(s and s[0] == "REF" and elem(s, 1) == "IA" and elem(s, 2) for s in order_slice)
        if not has_ia:
            add(out, P, S, "FF051", "REF", "REF01", "Order loop REF*IA* vendor site number mandatory per xls", "Error")

    # Item LIN/SN1
    for i, s in enumerate(body):
        if s and s[0] == "HL" and elem(s, 3) == "I":
            end = next((j for j in range(i + 1, len(body)) if body[j] and body[j][0] == "HL"), len(body))
            chunk = body[i:end]
            lin = next((x for x in chunk if x and x[0] == "LIN"), None)
            sn1 = next((x for x in chunk if x and x[0] == "SN1"), None)
            if sn1 and elem(sn1, 2) and not elem(sn1, 3):
                add(out, P, S, "FF201", "SN1", "SN103", "SN103 unit of measure mandatory (EA/CA/… per xls)", "Error")

    return out


# ============== Burlington (Burlington PDF 4010 + Functional Group SH) ==============


def validate_burlington(segments: List[List[str]]) -> List[Finding]:
    out: List[Finding] = []
    P, S = "Burlington", "Burlington Stores_856_specifications_13nov17.pdf (4010 Draft, Functional Group SH)"
    check_envelope_common(
        out,
        P,
        S,
        segments,
        expect_isa12="00401",
        expect_gs08="004010",
        expect_gs01="SH",
        gs03_allow={"6126750000"},
    )

    st_i = next((i for i, s in enumerate(segments) if s and s[0] == "ST"), None)
    se_i = next((i for i, s in enumerate(segments) if s and s[0] == "SE"), None)
    if st_i is None or se_i is None:
        return out
    body = segments[st_i + 1 : se_i]

    if "BURLINGTON" not in "~".join("*".join(s) for s in body).upper():
        add(out, P, S, "BRN010", "N1", "", "Expected Burlington party identifier in N1", "Warning")

    bsn = next((s for s in body if s and s[0] == "BSN"), None)
    if bsn and elem(bsn, 4) and not re.fullmatch(r"\d{6}", elem(bsn, 4)):
        add(out, P, S, "BRN101", "BSN", "BSN04", "BSN04 should be HHMMSS (6 digits) per X12", "Warning")

    for n4 in get_seg(body, "N4"):
        if elem(n4, 4) == "USA":
            add(out, P, S, "BRN130", "N4", "N404", "Use ISO 3166-1 alpha-2 US (not USA)", "Warning")

    # Item: SN101 line align
    for i, s in enumerate(body):
        if s and s[0] == "HL" and elem(s, 3) == "I":
            end = next((j for j in range(i + 1, len(body)) if body[j] and body[j][0] == "HL"), len(body))
            chunk = body[i:end]
            lin = next((x for x in chunk if x and x[0] == "LIN"), None)
            sn1 = next((x for x in chunk if x and x[0] == "SN1"), None)
            if lin and sn1 and elem(lin, 1) and not elem(sn1, 1):
                add(out, P, S, "BRN201", "SN1", "SN101", "SN101 should repeat LIN01 per X12 856 practice", "Warning")

    return out


VALIDATORS: Dict[str, Callable[[List[List[str]]], List[Finding]]] = {
    "amazon": validate_amazon,
    "delhaize": validate_delhaize,
    "fleet_farm": validate_fleet_farm,
    "burlington": validate_burlington,
}

DEFAULT_FILES = {
    "amazon": "/Users/shelia/Desktop/powermax/测试生成的asn/AMAZON-0074072_79HFKDZP_20260311181704.edi",
    "delhaize": "/Users/shelia/Desktop/powermax/测试生成的asn/Delhaize-0074099_13532765_20260311181954.edi",
    "fleet_farm": "/Users/shelia/Desktop/powermax/测试生成的asn/Fleet Farm-0073721_4864877_20260311181809.edi",
    "burlington": "/Users/shelia/Desktop/powermax/测试生成的asn/Burlington-0073894_384562802_20260311181739.edi",
}


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Strict four-partner 856 validation")
    ap.add_argument("--json", action="store_true", help="Output JSON only")
    ap.add_argument("files", nargs="*", help="Optional: edi paths in order amazon, delhaize, fleet_farm, burlington")
    args = ap.parse_args()

    order = ["amazon", "delhaize", "fleet_farm", "burlington"]
    paths = args.files if args.files else [DEFAULT_FILES[k] for k in order]

    all_findings: List[Dict[str, Any]] = []
    for key, path in zip(order, paths):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError as e:
            all_findings.append(
                {
                    "partner": key,
                    "spec_ref": "FILE",
                    "code": "FILE",
                    "segment": "",
                    "element": "",
                    "severity": "Error",
                    "message": f"Cannot read {path}: {e}",
                }
            )
            continue
        segs = parse_edi(content)
        for fd in VALIDATORS[key](segs):
            fd_dict = fd.to_dict()
            fd_dict["source_file"] = path
            all_findings.append(fd_dict)

    if args.json:
        print(json.dumps(all_findings, indent=2, ensure_ascii=False))
        return

    # Human-readable summary (group by partner display name)
    labels = {"amazon": "Amazon", "delhaize": "Delhaize", "fleet_farm": "Fleet Farm", "burlington": "Burlington"}
    by_partner: Dict[str, List[Dict[str, Any]]] = {}
    for f in all_findings:
        by_partner.setdefault(f["partner"], []).append(f)

    for p in order:
        items = by_partner.get(labels[p], [])
        print(f"\n{'=' * 72}\n{labels[p].upper()} ({len(items)} findings)\n{'=' * 72}")
        errs = [x for x in items if x["severity"] == "Error"]
        warns = [x for x in items if x["severity"] == "Warning"]
        print(f"  Errors: {len(errs)}  Warnings: {len(warns)}")
        for x in items:
            print(f"  [{x['severity']}] {x['code']} {x['segment']}/{x['element']} — {x['message']}")
            print(f"      spec: {x['spec_ref']}")


if __name__ == "__main__":
    main()
