from __future__ import annotations

import re
from typing import List

from .edi_parser import element_index, element_value, hl_chunks, parse_edi_with_raw, raw_segment_by_tag, segment_occurrences
from .schemas import ValidationFinding, ValidationPoint


def is_date(value: str, fmt: str) -> bool:
    if fmt == "CCYYMMDD":
        return bool(re.fullmatch(r"\d{8}", value or ""))
    if fmt == "YYMMDD":
        return bool(re.fullmatch(r"\d{6}", value or ""))
    return False


def is_time(value: str, fmt: str) -> bool:
    if fmt == "HHMM":
        return bool(re.fullmatch(r"\d{4}", value or ""))
    if fmt == "HHMMSS":
        return bool(re.fullmatch(r"\d{6}", value or ""))
    return False


def make_finding(
    code: str,
    severity: str,
    segment: str,
    element: str,
    message_zh: str,
    message_en: str,
    point_id: str = "",
    raw_segment: str = "",
    raw_segment_index: int = 0,
) -> ValidationFinding:
    return ValidationFinding(
        code=code,
        severity=severity,
        segment=segment,
        element=element,
        message_zh=message_zh,
        message_en=message_en,
        source="generic",
        point_id=point_id,
        raw_segment=raw_segment,
        raw_segment_index=raw_segment_index,
    )


def validate_generic(edi_text: str, points: List[ValidationPoint]) -> List[ValidationFinding]:
    segments, raw_segments, _separator = parse_edi_with_raw(edi_text)
    if not segments:
        return [
            make_finding(
                "PARSE001",
                "Error",
                "",
                "",
                "未解析到任何有效 EDI 段，请检查分隔符或报文内容。",
                "No valid EDI segments were parsed. Please check the delimiters or message content.",
            )
        ]

    findings: List[ValidationFinding] = []
    for point in points:
        if not point.compiled:
            continue

        if point.rule_type == "segment_required":
            if not segment_occurrences(segments, point.segment):
                findings.append(
                    make_finding(
                        point.id,
                        point.severity,
                        point.segment,
                        "",
                        f"缺少必填段 {point.segment}。",
                        f"Required segment {point.segment} is missing.",
                        point.id,
                    )
                )

        elif point.rule_type == "qualified_segment_required":
            matched = False
            raw_segment, raw_index = raw_segment_by_tag(segments, raw_segments, point.segment)
            for segment in segment_occurrences(segments, point.segment):
                if element_value(segment, 1).upper() == point.qualifier.upper():
                    matched = True
                    break
            if not matched:
                findings.append(
                    make_finding(
                        point.id,
                        point.severity,
                        point.segment,
                        f"{point.segment}*{point.qualifier}",
                        f"缺少必填限定段 {point.segment}*{point.qualifier}。",
                        f"Required qualified segment {point.segment}*{point.qualifier} is missing.",
                        point.id,
                        raw_segment,
                        raw_index,
                    )
                )

        elif point.rule_type == "element_required":
            segment_list = segment_occurrences(segments, point.segment)
            if not segment_list:
                findings.append(
                    make_finding(
                        point.id,
                        point.severity,
                        point.segment,
                        point.element,
                        f"缺少段 {point.segment}，无法满足 {point.element} 必填规则。",
                        f"Segment {point.segment} is missing, so required element {point.element} cannot be validated.",
                        point.id,
                    )
                )
                continue
            index = element_index(point.element)
            if not any(element_value(segment, index) for segment in segment_list):
                raw_segment, raw_index = raw_segment_by_tag(segments, raw_segments, point.segment)
                findings.append(
                    make_finding(
                        point.id,
                        point.severity,
                        point.segment,
                        point.element,
                        f"{point.element} 必填，但当前报文为空或缺失。",
                        f"{point.element} is required but missing or empty in the current EDI message.",
                        point.id,
                        raw_segment,
                        raw_index,
                    )
                )

        elif point.rule_type in {"element_equals", "element_one_of"}:
            segment_list = segment_occurrences(segments, point.segment)
            if not segment_list:
                findings.append(
                    make_finding(
                        point.id,
                        point.severity,
                        point.segment,
                        point.element,
                        f"缺少段 {point.segment}，无法校验 {point.element} 的取值。",
                        f"Segment {point.segment} is missing, so {point.element} cannot be validated.",
                        point.id,
                    )
                )
                continue
            index = element_index(point.element)
            actual_values = [element_value(segment, index).upper() for segment in segment_list if element_value(segment, index)]
            expected_values = [value.upper() for value in point.expected]
            if not actual_values:
                raw_segment, raw_index = raw_segment_by_tag(segments, raw_segments, point.segment)
                findings.append(
                    make_finding(
                        point.id,
                        point.severity,
                        point.segment,
                        point.element,
                        f"{point.element} 缺失，期望值为 {' / '.join(point.expected)}。",
                        f"{point.element} is missing. Expected {' / '.join(point.expected)}.",
                        point.id,
                        raw_segment,
                        raw_index,
                    )
                )
            else:
                bad_segment = ""
                bad_index = 0
                for idx, segment in enumerate(segments, start=1):
                    if segment and segment[0].upper() == point.segment.upper():
                        value = element_value(segment, index).upper()
                        if value and value not in expected_values:
                            bad_segment = raw_segments[idx - 1]
                            bad_index = idx
                            break
                if any(value not in expected_values for value in actual_values):
                    findings.append(
                        make_finding(
                            point.id,
                            point.severity,
                            point.segment,
                            point.element,
                            f"{point.element} 取值不符合规则，期望 {' / '.join(point.expected)}，实际 {' / '.join(actual_values)}。",
                            f"{point.element} does not match the expected value set. Expected {' / '.join(point.expected)}, got {' / '.join(actual_values)}.",
                            point.id,
                            bad_segment,
                            bad_index,
                        )
                    )

        elif point.rule_type in {"date_format", "time_format"}:
            segment_list = segment_occurrences(segments, point.segment)
            index = element_index(point.element)
            values = [element_value(segment, index) for segment in segment_list if element_value(segment, index)]
            fmt = point.expected[0] if point.expected else ""
            checker = is_date if point.rule_type == "date_format" else is_time
            if not values:
                raw_segment, raw_index = raw_segment_by_tag(segments, raw_segments, point.segment)
                findings.append(
                    make_finding(
                        point.id,
                        point.severity,
                        point.segment,
                        point.element,
                        f"{point.element} 缺失，无法校验 {fmt} 格式。",
                        f"{point.element} is missing, so {fmt} format cannot be validated.",
                        point.id,
                        raw_segment,
                        raw_index,
                    )
                )
            else:
                bad_segment = ""
                bad_index = 0
                for idx, segment in enumerate(segments, start=1):
                    if segment and segment[0].upper() == point.segment.upper():
                        value = element_value(segment, index)
                        if value and not checker(value, fmt):
                            bad_segment = raw_segments[idx - 1]
                            bad_index = idx
                            break
                if any(not checker(value, fmt) for value in values):
                    findings.append(
                        make_finding(
                            point.id,
                            point.severity,
                            point.segment,
                            point.element,
                            f"{point.element} 格式错误，期望 {fmt}。",
                            f"{point.element} has an invalid format. Expected {fmt}.",
                            point.id,
                            bad_segment,
                            bad_index,
                        )
                    )

        elif point.rule_type == "paired_elements":
            first = point.metadata.get("first", "")
            second = point.metadata.get("second", "")
            first_segment = first[:-2]
            second_segment = second[:-2]
            if first_segment != second_segment:
                continue
            segment_list = segment_occurrences(segments, first_segment)
            first_index = element_index(first)
            second_index = element_index(second)
            for segment in segment_list:
                first_value = element_value(segment, first_index)
                second_value = element_value(segment, second_index)
                if bool(first_value) ^ bool(second_value):
                    raw_segment, raw_index = raw_segment_by_tag(segments, raw_segments, first_segment)
                    findings.append(
                        make_finding(
                            point.id,
                            point.severity,
                            first_segment,
                            f"{first}/{second}",
                            f"{first} 和 {second} 必须同时出现。",
                            f"{first} and {second} must appear together.",
                            point.id,
                            raw_segment,
                            raw_index,
                        )
                    )
                    break

        elif point.rule_type == "conditional_dependency":
            trigger = point.metadata.get("trigger", "")
            required = point.metadata.get("required", "")
            trigger_segment = trigger[:-2]
            required_segment = required[:-2]
            if trigger_segment != required_segment:
                continue
            segment_list = segment_occurrences(segments, trigger_segment)
            trigger_index = element_index(trigger)
            required_index = element_index(required)
            for segment in segment_list:
                if element_value(segment, trigger_index) and not element_value(segment, required_index):
                    raw_segment, raw_index = raw_segment_by_tag(segments, raw_segments, trigger_segment)
                    findings.append(
                        make_finding(
                            point.id,
                            point.severity,
                            trigger_segment,
                            required,
                            f"当 {trigger} 存在时，{required} 必填。",
                            f"When {trigger} is present, {required} is required.",
                            point.id,
                            raw_segment,
                            raw_index,
                        )
                    )
                    break

        elif point.rule_type == "at_least_one_of":
            refs = point.metadata.get("refs", [])
            missing = True
            for ref in refs:
                ref_segment = ref[:-2]
                ref_index = element_index(ref)
                for segment in segment_occurrences(segments, ref_segment):
                    if element_value(segment, ref_index):
                        missing = False
                        break
                if not missing:
                    break
            if missing:
                joined = " / ".join(refs)
                findings.append(
                    make_finding(
                        point.id,
                        point.severity,
                        "",
                        joined,
                        f"{joined} 中至少需要一个有值。",
                        f"At least one of {joined} must have a value.",
                        point.id,
                    )
                )

        elif point.rule_type == "basic_loop_requirement":
            level = str(point.metadata.get("level", "")).upper()
            required_segments = [str(item).upper() for item in point.metadata.get("segments", [])]
            loop_chunks = [chunk for chunk_level, chunk in hl_chunks(segments) if chunk_level == level]
            if not loop_chunks:
                raw_segment, raw_index = raw_segment_by_tag(segments, raw_segments, "HL")
                findings.append(
                    make_finding(
                        point.id,
                        point.severity,
                        "HL",
                        level,
                        f"缺少 {level} 层级，无法满足循环规则。",
                        f"Required HL level {level} is missing, so the loop rule cannot be validated.",
                        point.id,
                        raw_segment,
                        raw_index,
                    )
                )
                continue
            for chunk in loop_chunks:
                tags = {segment[0].upper() for segment in chunk if segment}
                if any(required_segment not in tags for required_segment in required_segments):
                    first_chunk_segment = chunk[0] if chunk else []
                    raw_segment = ""
                    raw_index = 0
                    if first_chunk_segment in segments:
                        idx = segments.index(first_chunk_segment)
                        raw_segment = raw_segments[idx]
                        raw_index = idx + 1
                    findings.append(
                        make_finding(
                            point.id,
                            point.severity,
                            "HL",
                            level,
                            f"{level} 层级缺少必需段 {' / '.join(required_segments)}。",
                            f"HL level {level} is missing one or more required segments: {' / '.join(required_segments)}.",
                            point.id,
                            raw_segment,
                            raw_index,
                        )
                    )
                    break

    return findings
