from __future__ import annotations

import unittest

from edi_validate_web_app.core.profile_detector import detect_profile
from edi_validate_web_app.core.rule_extractor import compile_points


SPEC_EXCERPT = """
B3
Segment: Beginning Segment for Carrier's Invoice
Position: 020
Loop:
Level: Heading
Usage: Mandatory
Max Use: 1
Purpose: To transmit basic data relating to the carrier's invoice
M B302 76 Invoice Number M AN 1/22
Must Use B303 145 Shipment Identification Number O AN 1/30
M B304 146 Shipment Method of Payment M ID 2/2
M B306 373 Date M DT 8/8
Date expressed as CCYYMMDD
May be required by your Shipper per BluJay TMS Invoice Validation Profile settings.
M B307 193 Net Amount Due M N2 1/12
M B311 140 Standard Carrier Alpha Code M ID 2/4
Semantic Notes: 1 The data interchange control number GE02 in this trailer must be identical to the same
Note that the N9 "MB" and N9 "PO" references may be required by your Shipper per BluJay TMS Invoice Validation Profile.
G62 Segment may be required by your Shipper per BluJay TMS Invoice Validation Profile.
Invoice - Total Weight (May be required for Invoice Validation)
"""


class RuleExtractor210Tests(unittest.TestCase):
    def test_210_extraction_uses_b3_not_be(self) -> None:
        compiled = [point for point in compile_points("EDI 210 Specs (1).pdf", SPEC_EXCERPT) if point.compiled]

        self.assertTrue(any(point.rule_type == "segment_required" and point.segment == "B3" for point in compiled))
        self.assertFalse(any(point.segment == "BE" for point in compiled))
        self.assertFalse(any(point.expected == ["IDENTICAL", "TO", "THE", "SAME"] for point in compiled))

    def test_210_extraction_captures_key_b3_elements(self) -> None:
        compiled = [point for point in compile_points("EDI 210 Specs (1).pdf", SPEC_EXCERPT) if point.compiled]
        required_elements = {(point.segment, point.element) for point in compiled if point.rule_type == "element_required"}

        self.assertIn(("B3", "B302"), required_elements)
        self.assertIn(("B3", "B303"), required_elements)
        self.assertIn(("B3", "B304"), required_elements)
        self.assertIn(("B3", "B306"), required_elements)
        self.assertIn(("B3", "B307"), required_elements)
        self.assertIn(("B3", "B311"), required_elements)
        self.assertTrue(any(point.rule_type == "date_format" and point.element == "B306" for point in compiled))

    def test_profile_detector_recognizes_blujay_210(self) -> None:
        profile = detect_profile([SPEC_EXCERPT], ["EDI 210 Specs (1).pdf"])

        self.assertIsNotNone(profile)
        assert profile is not None
        self.assertEqual(profile.plugin_key, "blujay_210")


if __name__ == "__main__":
    unittest.main()
