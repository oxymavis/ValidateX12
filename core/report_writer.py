from __future__ import annotations

from typing import Iterable

from .schemas import ValidationFinding


def findings_to_markdown(
    spec_name: str,
    mode_label: str,
    findings: Iterable[ValidationFinding],
    spec_id: str = "",
    build_version: str = "",
    validator_type: str = "",
) -> str:
    finding_list = list(findings)
    lines = [
        "# EDI Validation Report",
        "",
        f"- Spec: `{spec_name}`",
        f"- Spec ID: `{spec_id or '-'}`",
        f"- Validator Build: `{build_version or '-'}`",
        f"- Validator Type: `{validator_type or '-'}`",
        f"- Validation Mode: `{mode_label}`",
        f"- Total Findings: `{len(finding_list)}`",
        "",
        "## Findings",
        "",
    ]
    if not finding_list:
        lines.append("No validation findings.")
        return "\n".join(lines)

    for idx, finding in enumerate(finding_list, start=1):
        lines.extend(
            [
                f"### {idx}. {finding.severity} - {finding.code}",
                f"- Source: `{finding.source}`",
                f"- Segment: `{finding.segment or '-'}`",
                f"- Element: `{finding.element or '-'}`",
                f"- 中文: {finding.message_zh}",
                f"- English: {finding.message_en}",
                f"- Raw Segment Line: `{finding.raw_segment_index or '-'}`",
                f"- Raw Segment: `{finding.raw_segment or '-'}`",
                "",
            ]
        )
    return "\n".join(lines)
