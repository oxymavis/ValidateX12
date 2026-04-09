from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterable, List

from .schemas import ValidationPoint


ERROR_WORDS = ("MUST", "REQUIRED", "MANDATORY", "必填", "必须", "缺少", "MUST USE")
WARNING_WORDS = ("SHOULD", "RECOMMENDED", "TYPICALLY", "建议", "推荐", "通常")
DATE_FORMATS = {"CCYYMMDD", "YYMMDD"}
TIME_FORMATS = {"HHMM", "HHMMSS"}
SEGMENT_TOKEN = r"[A-Z][A-Z0-9]{1,2}"
ELEMENT_TOKEN = r"[A-Z][A-Z0-9]{1,4}\d{2}"
SEGMENT_STOPWORDS = {
    "IS",
    "ARE",
    "THE",
    "FOR",
    "WITH",
    "AND",
    "USE",
    "NOT",
    "ONE",
    "TWO",
    "THREE",
    "HAS",
    "HAVE",
    "HAD",
    "THIS",
    "THAT",
    "WHEN",
    "THEN",
    "MAY",
    "MUST",
    "CAN",
    "SHOULD",
    "FROM",
    "INTO",
    "ITS",
    "PER",
    "ALL",
    "ANY",
    "MAY",
    "WILL",
    "BE",
    "NOTE",
    "NOTES",
    "CODE",
}
VALUE_STOPWORDS = {
    "IDENTICAL",
    "TO",
    "THE",
    "SAME",
    "AS",
    "FOUND",
    "RECEIVED",
    "HEADER",
    "TRAILER",
    "THIS",
    "THAT",
    "VALUE",
}

QUALIFIED_REQUIRED_RE = re.compile(
    rf"\b({SEGMENT_TOKEN})\*([A-Z0-9]{{2,4}})\b.*?(REQUIRED|MANDATORY|MUST USE|必填|必须|缺少)",
    re.IGNORECASE,
)
QUALIFIED_MISSING_RE = re.compile(rf"\bMISSING\s+({SEGMENT_TOKEN})\*([A-Z0-9]{{2,4}})\b", re.IGNORECASE)
ELEMENT_REQUIRED_RE = re.compile(rf"\b({ELEMENT_TOKEN})\b.*?(REQUIRED|MANDATORY|MUST USE|必填|必须|缺少)", re.IGNORECASE)
ELEMENT_USAGE_RE = re.compile(rf"^(?:M|MUST USE)\s+({ELEMENT_TOKEN})\b", re.IGNORECASE)
SEGMENT_REQUIRED_RE = re.compile(rf"^(?:SEGMENT\s*:?\s*)?({SEGMENT_TOKEN})(?:\s+SEGMENT)?\s+(?:IS\s+)?(REQUIRED|MANDATORY|MUST USE|必填|必须|缺少)\b", re.IGNORECASE)
MUST_BE_RE = re.compile(rf"\b({ELEMENT_TOKEN})\b.*?(?:MUST BE|应为|必须是)\s+([A-Z0-9/\- ,|]+)", re.IGNORECASE)
ONE_OF_RE = re.compile(rf"\b({ELEMENT_TOKEN})\b.*?(?:ONE OF|其中之一|必须是)\s+([A-Z0-9/\- ,|]+)", re.IGNORECASE)
FORMAT_RE = re.compile(rf"\b({ELEMENT_TOKEN})\b.*?(CCYYMMDD|YYMMDD|HHMMSS|HHMM)\b", re.IGNORECASE)
FORMAT_CONTEXT_RE = re.compile(r"\b(CCYYMMDD|YYMMDD|HHMMSS|HHMM)\b", re.IGNORECASE)
CONDITIONAL_RE = re.compile(rf"IF\s+({ELEMENT_TOKEN})\s+(?:IS\s+)?PRESENT\s+THEN\s+({ELEMENT_TOKEN})\s+(?:IS\s+)?REQUIRED", re.IGNORECASE)
PAIRED_RE = re.compile(rf"\b({ELEMENT_TOKEN})\b\s+AND\s+\b({ELEMENT_TOKEN})\b.*?(?:TOGETHER|APPEAR TOGETHER|MUST APPEAR TOGETHER)", re.IGNORECASE)
AT_LEAST_ONE_RE = re.compile(rf"AT LEAST ONE OF\s+({ELEMENT_TOKEN}(?:\s*(?:,|/|OR)\s*{ELEMENT_TOKEN})+)", re.IGNORECASE)
LEVEL_REQUIRED_RE = re.compile(rf"\b(SHIPMENT|ORDER|PACK|PACKAGE|TARE|ITEM)\s+(?:LEVEL|HL)?\s+({SEGMENT_TOKEN})\b.*?(REQUIRED|MANDATORY|缺少|必填)", re.IGNORECASE)
LOOP_CONTAINS_RE = re.compile(rf"\b(ITEM|PACK|PACKAGE|ORDER|SHIPMENT|TARE)\s+HL\b.*?(?:CONTAIN|WITH)\s+({SEGMENT_TOKEN})(?:\s+AND\s+({SEGMENT_TOKEN}))?", re.IGNORECASE)
SEGMENT_HEADER_RE = re.compile(rf"^({SEGMENT_TOKEN})$", re.IGNORECASE)
SEGMENT_USAGE_RE = re.compile(r"^USAGE:\s+(MANDATORY|REQUIRED)\b", re.IGNORECASE)
SYNTAX_NOTE_RE = re.compile(r"^\s*\d+\.\s+[CPR]\d{4}\b", re.IGNORECASE)


def severity_for_line(line_upper: str) -> str:
    if any(token in line_upper for token in WARNING_WORDS):
        return "Warning"
    return "Error"


def normalize_values(raw: str) -> List[str]:
    normalized = raw.replace("或", "/").replace(" OR ", "/").replace(" or ", "/").replace(",", "/").replace("|", "/")
    values = [
        item
        for item in re.findall(r"[A-Z0-9]{1,16}", normalized.upper())
        if item not in {"MUST", "BE", "ONE", "OF"} and item not in VALUE_STOPWORDS
    ]
    dedup: List[str] = []
    for value in values:
        if value not in dedup:
            dedup.append(value)
    return dedup[:10]


def freeze_value(value: object) -> object:
    if isinstance(value, dict):
        return tuple(sorted((key, freeze_value(val)) for key, val in value.items()))
    if isinstance(value, list):
        return tuple(freeze_value(item) for item in value)
    return value


def is_syntax_note_line(line_upper: str) -> bool:
    return bool(
        SYNTAX_NOTE_RE.search(line_upper)
        or " IF " in f" {line_upper} "
        or " AT LEAST ONE OF " in f" {line_upper} "
        or " THEN " in f" {line_upper} "
        or " THE OTHER IS REQUIRED" in line_upper
    )


def is_conditional_requirement(line_upper: str) -> bool:
    return " MAY BE REQUIRED" in f" {line_upper} " or " WILL BE REQUIRED" in f" {line_upper} "


def has_literal_expected_values(raw: str, values: List[str]) -> bool:
    raw_upper = raw.upper()
    if not values:
        return False
    if any(phrase in raw_upper for phrase in ("IDENTICAL TO", "THE SAME", "SAME AS", "FOUND IN", "RECEIVED IN")):
        return False
    if len(values) == 1:
        token = values[0]
        return raw.strip().upper() == token
    return any(any(ch.isdigit() for ch in value) or len(value) <= 4 for value in values)


def _make_point(point_id: str, file_name: str, source_line: str, title: str, category: str, rule_type: str, **kwargs: object) -> ValidationPoint:
    severity = kwargs.pop("severity", severity_for_line(source_line.upper()))
    point = ValidationPoint(
        id=point_id,
        title=title,
        source_line=source_line,
        source_file=file_name,
        category=category,
        rule_type=rule_type,
        severity=severity,
        **kwargs,
    )
    point.compiled = rule_type != "informational"
    point.description_zh = source_line
    point.description_en = title
    return point


def compile_points(file_name: str, text: str) -> List[ValidationPoint]:
    points: List[ValidationPoint] = []
    seen: set[tuple] = set()
    current_segment = ""
    current_element = ""
    last_segment_header_line = 0
    for idx, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        upper = line.upper()
        point_id = f"{Path(file_name).stem}-{idx}"

        def add_point(point: ValidationPoint) -> None:
            key = (
                point.rule_type,
                point.segment,
                point.element,
                point.qualifier,
                tuple(point.expected),
                freeze_value(point.metadata),
                point.source_line,
            )
            if key not in seen:
                seen.add(key)
                points.append(point)

        segment_match = SEGMENT_HEADER_RE.match(upper)
        if segment_match and upper not in SEGMENT_STOPWORDS:
            current_segment = segment_match.group(1)
            current_element = ""
            last_segment_header_line = idx
            continue

        element_context = re.match(rf"^(?:NOT USED\s+|M\s+|MUST USE\s+)?({ELEMENT_TOKEN})\b", upper)
        if element_context:
            current_element = element_context.group(1)
            current_segment = current_element[:-2]

        if current_segment and SEGMENT_USAGE_RE.match(upper) and idx - last_segment_header_line <= 8:
            add_point(
                _make_point(
                    point_id,
                    file_name,
                    line,
                    f"{current_segment} segment is required",
                    "Required",
                    "segment_required",
                    segment=current_segment,
                )
            )
            continue

        usage_match = ELEMENT_USAGE_RE.match(upper)
        if usage_match and not is_syntax_note_line(upper):
            element = usage_match.group(1)
            add_point(
                _make_point(
                    point_id,
                    file_name,
                    line,
                    f"{element} is required",
                    "Required",
                    "element_required",
                    segment=element[:-2],
                    element=element,
                )
            )
            continue

        match = QUALIFIED_REQUIRED_RE.search(upper) or QUALIFIED_MISSING_RE.search(upper)
        if match:
            segment, qualifier = match.groups()[:2]
            add_point(
                _make_point(
                    point_id,
                    file_name,
                    line,
                    f"{segment}*{qualifier} is required",
                    "Required",
                    "qualified_segment_required",
                    segment=segment,
                    qualifier=qualifier,
                )
            )
            continue

        match = CONDITIONAL_RE.search(upper)
        if match:
            trigger, required = match.groups()
            add_point(
                _make_point(
                    point_id,
                    file_name,
                    line,
                    f"If {trigger} is present, {required} is required",
                    "Dependency",
                    "conditional_dependency",
                    metadata={"trigger": trigger, "required": required},
                )
            )
            continue

        match = PAIRED_RE.search(upper)
        if match:
            first, second = match.groups()
            add_point(
                _make_point(
                    point_id,
                    file_name,
                    line,
                    f"{first} and {second} must appear together",
                    "Dependency",
                    "paired_elements",
                    metadata={"first": first, "second": second},
                )
            )
            continue

        match = AT_LEAST_ONE_RE.search(upper)
        if match:
            refs = normalize_values(match.group(1))
            if refs:
                add_point(
                    _make_point(
                        point_id,
                        file_name,
                        line,
                        f"At least one of {' / '.join(refs)} is required",
                        "Dependency",
                        "at_least_one_of",
                        metadata={"refs": refs},
                    )
                )
                continue

        match = LOOP_CONTAINS_RE.search(upper)
        if match:
            level_name, first_seg, second_seg = match.groups()
            required_segments = [first_seg]
            if second_seg:
                required_segments.append(second_seg)
            add_point(
                _make_point(
                    point_id,
                    file_name,
                    line,
                    f"{level_name.title()} HL must contain {' and '.join(required_segments)}",
                    "Loop Rule",
                    "basic_loop_requirement",
                    metadata={"level": level_name[:1], "segments": required_segments},
                )
            )
            continue

        match = LEVEL_REQUIRED_RE.search(upper)
        if match:
            level_name, segment, _ = match.groups()
            add_point(
                _make_point(
                    point_id,
                    file_name,
                    line,
                    f"{level_name.title()} level {segment} is required",
                    "Loop Rule",
                    "basic_loop_requirement",
                    metadata={"level": level_name[:1], "segments": [segment]},
                )
            )
            continue

        match = FORMAT_RE.search(upper)
        if match:
            element, fmt = match.groups()
            rule_type = "date_format" if fmt.upper() in DATE_FORMATS else "time_format"
            add_point(
                _make_point(
                    point_id,
                    file_name,
                    line,
                    f"{element} must use {fmt.upper()} format",
                    "Format",
                    rule_type,
                    segment=element[:-2],
                    element=element,
                    expected=[fmt.upper()],
                )
            )
            continue

        if current_element and ("FORMAT" in upper or "EXPRESSED AS" in upper):
            match = FORMAT_CONTEXT_RE.search(upper)
            if match:
                fmt = match.group(1).upper()
                rule_type = "date_format" if fmt in DATE_FORMATS else "time_format"
                add_point(
                    _make_point(
                        point_id,
                        file_name,
                        line,
                        f"{current_element} must use {fmt} format",
                        "Format",
                        rule_type,
                        segment=current_element[:-2],
                        element=current_element,
                        expected=[fmt],
                    )
                )
                continue

        match = ONE_OF_RE.search(upper)
        if match:
            element, raw = match.groups()
            values = normalize_values(raw)
            if len(values) >= 2 and has_literal_expected_values(raw, values):
                add_point(
                    _make_point(
                        point_id,
                        file_name,
                        line,
                        f"{element} must be one of {' / '.join(values)}",
                        "Value Constraint",
                        "element_one_of",
                        segment=element[:-2],
                        element=element,
                        expected=values,
                    )
                )
                continue

        match = MUST_BE_RE.search(upper)
        if match:
            element, raw = match.groups()
            values = normalize_values(raw)
            if not has_literal_expected_values(raw, values):
                continue
            rule_type = "element_one_of" if len(values) > 1 else "element_equals"
            add_point(
                _make_point(
                    point_id,
                    file_name,
                    line,
                    f"{element} must be {' / '.join(values) if values else raw.strip()}",
                    "Value Constraint",
                    rule_type,
                    segment=element[:-2],
                    element=element,
                    expected=values,
                )
            )
            continue

        match = ELEMENT_REQUIRED_RE.search(upper)
        if match:
            if not is_syntax_note_line(upper) and not is_conditional_requirement(upper):
                element = match.group(1)
                add_point(
                    _make_point(
                        point_id,
                        file_name,
                        line,
                        f"{element} is required",
                        "Required",
                        "element_required",
                        segment=element[:-2],
                        element=element,
                    )
                )
                continue

        match = SEGMENT_REQUIRED_RE.search(upper)
        if match:
            segment = match.group(1)
            if segment not in SEGMENT_STOPWORDS and not is_syntax_note_line(upper) and not is_conditional_requirement(upper):
                add_point(
                    _make_point(
                        point_id,
                        file_name,
                        line,
                        f"{segment} segment is required",
                        "Required",
                        "segment_required",
                        segment=segment,
                    )
                )
                continue

        if any(token in upper for token in ERROR_WORDS + WARNING_WORDS):
            add_point(
                _make_point(
                    point_id,
                    file_name,
                    line,
                    "Informational validation point",
                    "Informational",
                    "informational",
                    compiled=False,
                )
            )
    return points


def group_points(points: Iterable[ValidationPoint]) -> List[Dict[str, object]]:
    grouped: Dict[str, List[ValidationPoint]] = {}
    for point in points:
        grouped.setdefault(point.category, []).append(point)
    ordered = []
    for category in ("Required", "Value Constraint", "Dependency", "Format", "Loop Rule", "Informational"):
        items = grouped.get(category, [])
        if not items:
            continue
        items.sort(key=lambda item: (item.segment, item.element, item.qualifier, item.title))
        ordered.append({"category": category, "count": len(items), "items": [item.to_dict() for item in items]})
    return ordered
