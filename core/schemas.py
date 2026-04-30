from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class UploadedDocument:
    file_name: str
    file_type: str
    stored_path: str
    characters: int
    sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DetectedProfile:
    name: str
    kind: str
    confidence: str
    match_reason: str
    plugin_key: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ValidationPoint:
    id: str
    title: str
    source_line: str
    source_file: str
    category: str
    rule_type: str
    segment: str = ""
    element: str = ""
    qualifier: str = ""
    expected: List[str] = field(default_factory=list)
    severity: str = "Error"
    compiled: bool = False
    description_zh: str = ""
    description_en: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ValidationFinding:
    code: str
    severity: str
    segment: str
    element: str
    message_zh: str
    message_en: str
    source: str
    point_id: str = ""
    raw_segment: str = ""
    raw_segment_index: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "segment": self.segment,
            "element": self.element,
            "messageZh": self.message_zh,
            "messageEn": self.message_en,
            "source": self.source,
            "pointId": self.point_id,
            "rawSegment": self.raw_segment,
            "rawSegmentIndex": self.raw_segment_index,
        }
