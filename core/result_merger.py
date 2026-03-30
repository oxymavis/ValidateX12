from __future__ import annotations

from typing import Iterable, List

from .schemas import ValidationFinding


def normalize_text(text: str) -> str:
    return " ".join(text.split()).strip().lower()


def merge_findings(generic_findings: Iterable[ValidationFinding], plugin_findings: Iterable[ValidationFinding]) -> List[ValidationFinding]:
    merged: List[ValidationFinding] = []
    seen: set[tuple[str, str, str, str]] = set()

    for finding in list(plugin_findings) + list(generic_findings):
        key = (
            finding.severity,
            finding.segment.upper(),
            finding.element.upper(),
            normalize_text(finding.message_en or finding.message_zh),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(finding)
    return merged

