from __future__ import annotations

import re
from typing import List, Tuple


def detect_element_separator(text: str) -> str:
    candidates = ["*", "|", "^"]
    counts = {sep: text.count(sep) for sep in candidates}
    best = max(counts, key=counts.get)
    return best if counts[best] else "*"


def split_raw_segments(edi_text: str) -> Tuple[List[str], str]:
    clean = edi_text.strip().replace("\r\n", "\n").replace("\r", "\n")
    if "~" in clean:
        raw_segments = [seg.strip() for seg in clean.replace("\n", "").split("~") if seg.strip()]
    else:
        raw_segments = [seg.strip() for seg in clean.split("\n") if seg.strip()]
    if not raw_segments:
        return [], "*"
    separator = detect_element_separator(clean)
    return raw_segments, separator


def parse_edi(edi_text: str) -> Tuple[List[List[str]], str]:
    raw_segments, separator = split_raw_segments(edi_text)
    return [[part.strip() for part in segment.split(separator)] for segment in raw_segments], separator


def parse_edi_with_raw(edi_text: str) -> Tuple[List[List[str]], List[str], str]:
    raw_segments, separator = split_raw_segments(edi_text)
    return [[part.strip() for part in segment.split(separator)] for segment in raw_segments], raw_segments, separator


def segment_occurrences(segments: List[List[str]], tag: str) -> List[List[str]]:
    upper_tag = tag.upper()
    return [seg for seg in segments if seg and seg[0].upper() == upper_tag]


def element_value(segment: List[str], index: int) -> str:
    return segment[index].strip() if 0 < index < len(segment) else ""


def element_index(element_ref: str) -> int:
    match = re.search(r"(\d{2})$", element_ref)
    return int(match.group(1)) if match else 0


def hl_chunks(segments: List[List[str]]) -> List[tuple[str, List[List[str]]]]:
    starts = [idx for idx, seg in enumerate(segments) if seg and seg[0].upper() == "HL"]
    chunks: List[tuple[str, List[List[str]]]] = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(segments)
        chunk = segments[start:end]
        level = element_value(chunk[0], 3).upper() if chunk else ""
        chunks.append((level, chunk))
    return chunks


def raw_segment_by_tag(segments: List[List[str]], raw_segments: List[str], tag: str) -> tuple[str, int]:
    upper_tag = tag.upper()
    for idx, segment in enumerate(segments, start=1):
        if segment and segment[0].upper() == upper_tag:
            return raw_segments[idx - 1], idx
    return "", 0
