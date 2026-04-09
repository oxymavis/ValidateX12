# EDI 210 Validation Rules (Based on BluJay 210 Spec)

## 1. Overview

This document defines validation logic for EDI 210 (Motor Carrier
Freight Details and Invoice). The validation rules are divided into four
layers:

1.  Envelope Validation
2.  Transaction Structure Validation
3.  Segment and Element Validation
4.  Business Cross‑Validation

------------------------------------------------------------------------

# 2. Envelope Validation

## ISA / IEA

Rules:

-   ISA must exist exactly once
-   IEA must exist exactly once
-   ISA12 must equal `00401`
-   ISA11 must equal `U`
-   ISA15 should equal `P`
-   IEA02 must equal ISA13

Errors:

-   E001 ISA missing
-   E002 IEA missing
-   E003 ISA12 must be 00401
-   E004 IEA02 must equal ISA13

------------------------------------------------------------------------

## GS / GE

Rules:

-   GS must exist
-   GE must exist
-   GS01 must equal `IM`
-   GS08 must equal `004010`
-   GE02 must equal GS06

Errors:

-   E010 GS01 must be IM
-   E011 GS08 must be 004010
-   E012 GE02 must equal GS06

------------------------------------------------------------------------

## ST / SE

Rules:

-   ST must exist
-   SE must exist
-   ST01 must equal `210`
-   SE02 must equal ST02
-   SE01 must match actual segment count

Errors:

-   E020 ST01 must be 210
-   E021 SE02 must equal ST02
-   E022 SE01 segment count mismatch

------------------------------------------------------------------------

# 3. Header Segment Validation

## B3 Segment (Invoice Header)

Required fields:

-   B302 Invoice Number
-   B303 Shipment Identification Number
-   B304 Shipment Method of Payment
-   B306 Invoice Date
-   B307 Net Amount Due
-   B311 SCAC

Rules:

-   B304 must be `CC` or `PP`
-   B306 must be valid date (CCYYMMDD)
-   B307 must be numeric
-   B311 must be 2--4 characters

Errors:

-   E100 B3 missing
-   E101 Invoice number required
-   E102 Shipment ID required
-   E103 Payment method invalid
-   E104 Invalid invoice date
-   E105 Invalid amount
-   E106 SCAC required

------------------------------------------------------------------------

## C3 Segment (Currency)

Rules:

-   C3 must exist
-   C301 currency code required
-   Recommended ISO codes (USD, CAD, MXN, EUR)

Errors:

-   E110 Currency segment required
-   E111 Currency code required
-   E112 Invalid currency code

------------------------------------------------------------------------

## N1 Loop (Shipper)

Rules:

-   At least one N1 loop must exist
-   N1\*SH must exist
-   N102 or (N103 + N104) required
-   If N103 present, N104 required

Errors:

-   E130 N1 SH missing
-   E131 N1 identification missing
-   E132 N103/N104 must appear together

------------------------------------------------------------------------

# 4. Stop and Location Validation

## S5 Segment

Rules:

-   S501 Stop Sequence Number required
-   S502 must be `LD` or `UL`
-   Stop sequence must be unique

Errors:

-   E200 Stop sequence missing
-   E201 Invalid stop reason
-   E202 Duplicate stop sequence

------------------------------------------------------------------------

## G62 Segment

Rules:

Allowed qualifiers:

Date: - 35 Delivery Date - 86 Pickup Date

Time: - 8 Pickup Time - 9 Delivery Time

Errors:

-   E210 Date qualifier mismatch
-   E211 Time qualifier mismatch
-   E212 Invalid qualifier

------------------------------------------------------------------------

## Location Loop

Rules:

-   N101 must be `SF` or `ST`
-   N3 address required
-   N4 must contain valid country code

Errors:

-   E220 Invalid stop location qualifier
-   E221 Address required

------------------------------------------------------------------------

# 5. Detail Charge Validation

## LX Loop

Rules:

-   LX01 required
-   Must be unique

Errors:

-   E300 LX sequence required
-   E301 Duplicate LX

------------------------------------------------------------------------

## L0 Segment (Weight/Quantity)

Rules:

-   Element pairs must appear together
-   Valid weight qualifiers: B, F, G, N, T

Errors:

-   E310 Invalid quantity pair
-   E311 Invalid weight qualifier

------------------------------------------------------------------------

## L1 Segment (Charges)

Rules:

-   Each LX must contain at least one L1
-   L102 and L103 must appear together
-   At least one of L104/L105/L106 must exist
-   L108 must be valid charge code

Errors:

-   E320 Rate qualifier mismatch
-   E321 Missing charge amount
-   E322 Invalid rate qualifier
-   E323 Invalid charge code

------------------------------------------------------------------------

# 6. Summary Validation

## L3 Segment

Rules:

-   L305 total charge must equal sum of L1 charges

Errors:

-   E400 Total charge mismatch

------------------------------------------------------------------------

# 7. Business Cross‑Validation

Recommended validations:

-   B303 Shipment ID must match original 204 tender
-   B311 SCAC must match original 204
-   At least one charge line must exist
-   Load stop should contain pickup time
-   Unload stop should contain delivery time

Errors:

-   E500 Shipment ID mismatch
-   E501 SCAC mismatch
-   E530 No charge lines found

------------------------------------------------------------------------

# 8. Recommended Error Format

Example JSON response:

``` json
[
  {
    "code": "E103",
    "segment": "B3",
    "element": "B304",
    "severity": "Error",
    "message": "Shipment method must be CC or PP"
  }
]
```

------------------------------------------------------------------------

# 9. Minimum Validation Set

Recommended minimal implementation:

1.  ST01 must equal 210
2.  SE02 must equal ST02
3.  B3 required fields validated
4.  C3 currency required
5.  N1 SH required
6.  At least one LX loop
7.  Each LX must contain L1
8.  Charge total must equal L3 total
