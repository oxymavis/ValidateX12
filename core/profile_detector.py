from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

from .schemas import DetectedProfile


@dataclass
class ProfilePattern:
    key: str
    name: str
    keywords: List[str]
    id_patterns: List[str]


PROFILES: List[ProfilePattern] = [
    ProfilePattern("amazon", "Amazon Warehouse", ["AMAZON WAREHOUSE", "AMAZON.COM", "AMAZON"], ["ZZ:AMAZON/AMAZON", "AMAZON_856"]),
    ProfilePattern("delhaize", "Delhaize America", ["DELHAIZE AMERICA", "DELHAIZE"], ["07:5400110000009/540011000", "51007HO"]),
    ProfilePattern("fleet_farm", "Fleet Farm", ["FLEET FARM", "MILLS FLEET FARM"], ["12:4147318121/4147318121", "0004627"]),
    ProfilePattern("burlington", "Burlington Coat Factory", ["BURLINGTON", "BURLINGTON MERCHANDISING CORP"], ["08:6126750000/6126750000", "0051065"]),
    ProfilePattern("sps", "SPS / Topco", ["TOPCO", "SPS COMMERCE", "SPARTAN STORES", "NASH FINCH"], ["004010UCS", "51012SP", "51012SI", "51012NF"]),
    ProfilePattern("walmart", "Walmart USA", ["WALMART", "WAL-MART STORES"], ["08:925485US00/925485US00", "51010B"]),
    ProfilePattern("doitbest", "DO IT BEST HARDWARE", ["DO IT BEST", "DO IT BEST HARDWARE"], ["ZZ:DOITBESTVP/DOITBESTVP", "0051064"]),
]


def detect_profile(texts: Iterable[str], file_names: Iterable[str]) -> Optional[DetectedProfile]:
    haystack = " ".join(texts).upper()
    file_haystack = " ".join(file_names).upper()
    best_match: Optional[DetectedProfile] = None
    best_score = 0
    for profile in PROFILES:
        score = 0
        matched = []
        for keyword in profile.keywords:
            if keyword.upper() in haystack or keyword.upper() in file_haystack:
                score += 3
                matched.append(keyword)
        for pattern in profile.id_patterns:
            if pattern.upper() in haystack or pattern.upper() in file_haystack:
                score += 5
                matched.append(pattern)
        if score > best_score:
            best_score = score
            confidence = "high" if score >= 8 else "medium"
            best_match = DetectedProfile(
                name=profile.name,
                kind="built_in_example",
                confidence=confidence,
                match_reason="Matched " + ", ".join(matched[:4]),
                plugin_key=profile.key,
            )
    return best_match

