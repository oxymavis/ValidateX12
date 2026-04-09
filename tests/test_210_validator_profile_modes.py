from __future__ import annotations

import unittest

from edi_210_validator import validate_edi_210


BASE_EDI = (
    "ISA*00*          *00*          *02*SENDERID1234567*01*RECEIVERID12345*260408*1200*U*00401*000000001*0*P*>~"
    "GS*IM*SENDER*RECEIVER*20260408*1200*1*X*004010~"
    "ST*210*0001~"
    "B3**INV001*SHIP001*PP**20260408*150000****ABCD~"
    "C3*USD~"
    "N1*SH*SHIPPER~"
    "LX*1~"
    "L1****150000~"
    "L3****150000~"
    "SE*8*0001~"
    "GE*1*1~"
    "IEA*1*000000001~"
)


def find_messages(errors: list[dict], code: str) -> list[dict]:
    return [item for item in errors if item.get("code") == code]


class ValidatorProfileModeTests(unittest.TestCase):
    def test_default_mode_turns_profile_only_rules_into_warnings(self) -> None:
        errors = validate_edi_210(BASE_EDI)

        self.assertTrue(find_messages(errors, "E122"))
        self.assertTrue(find_messages(errors, "E123"))
        self.assertTrue(find_messages(errors, "E203"))
        self.assertTrue(all(item["severity"] == "Warning" for item in find_messages(errors, "E122")))
        self.assertTrue(all(item["severity"] == "Warning" for item in find_messages(errors, "E123")))
        self.assertTrue(all(item["severity"] == "Warning" for item in find_messages(errors, "E203")))

    def test_default_mode_no_longer_requires_heading_n3(self) -> None:
        errors = validate_edi_210(BASE_EDI)

        self.assertFalse(any(item["code"] == "E133" and item["segment"] == "N3" for item in errors))

    def test_strict_mode_keeps_profile_rules_as_errors(self) -> None:
        errors = validate_edi_210(BASE_EDI, strict_profile=True)

        self.assertTrue(all(item["severity"] == "Error" for item in find_messages(errors, "E122")))
        self.assertTrue(all(item["severity"] == "Error" for item in find_messages(errors, "E123")))
        self.assertTrue(all(item["severity"] == "Error" for item in find_messages(errors, "E203")))


if __name__ == "__main__":
    unittest.main()
