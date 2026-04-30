---
name: edi-validate-studio
description: >-
  Describes EDI Validate Studio — spec upload, heuristic rule extraction from
  PDF/DOCX/Excel/text, per-upload generated validator artifacts, generic X12
  validation runtime, optional built-in retail 856 / BluJay 210 plugins,
  bilingual findings, Markdown reports, Flask API and deployment constraints.
  Use when the user works with this repo, edi_validate_web_app, X12 856/210
  validation against customer specs, spec-bound validation, or importing this
  product’s behavior into another agent.
---

# EDI Validate Studio — Agent Skill

## Where this file lives (agent sync)

Your agent expects:

```text
{skills_dir}/
  └── edi-validate-studio/
      └── SKILL.md   ← this file
```

In **this repository**, set `{skills_dir}` to the folder **`skills/`** at the repo root (the directory that contains `edi-validate-studio/`). Do not point `{skills_dir}` only at `.cursor/skills/` unless your tool explicitly reads Cursor’s layout.

A **Cursor-compatible** copy of this same skill body is linked from `.cursor/skills/edi-validate-studio/SKILL.md` (symlink to here).

## What this product does

1. **Spec ingestion**: User uploads one or more customer spec files (allow-list: `.pdf`, `.docx`, `.xlsx`, `.xls`, `.txt`, `.md`). Max upload size is configured on the Flask app (typically ~25MB).
2. **Text extraction**: `core/parsers.py` pulls plain text — PDF via pdfplumber, DOCX via ZIP+XML stripping, spreadsheets via pandas, legacy `.xls` with fallback heuristics if pandas fails.
3. **Rule candidates**: `core/rule_extractor.py` turns extracted text into **`ValidationPoint`** records: title, category, optional segment/element/qualifier/expected, `compiled` (executable vs informational), bilingual descriptions when present.
4. **Per-upload binding**: Each upload gets a **`specId`** (short hex). The server writes:
   - `data/uploads/<specId>/` — raw files + SHA-256 fingerprints
   - `data/specs/<specId>.json` — full **spec bundle** (documents, points, mode, validator metadata)
   - `data/generated_validators/<specId>/<buildVersion>/` — **manifest.json**, **rules.json** (points), **validator.py** (artifact for traceability; runtime uses in-memory points from rules)
5. **Validation**: Client POSTs `specId` + EDI body. Server **reloads bundle + manifest + rules**, checks **spec binding** (same `specId`, same document fingerprints). Then either runs **generic engine** on points, or **built-in profile plugin** when matched (see modes below).
6. **Output**: **`ValidationFinding`** list (code, severity, segment, element, `messageZh` / `messageEn`, `source`), optional **Markdown report** at `GET /api/report/<reportId>`.

## Validation modes

| `validationMode` (bundle / response) | Meaning |
|--------------------------------------|---------|
| `generated_spec` | Generic rule engine over extracted **ValidationPoint** list only. |
| `built_in_profile` | A known trading partner **plugin** matched (`core/profile_detector.py`); plugin runs on parsed segments; **generic engine is not run on success**. On plugin failure, app falls back to generic and returns `fallback` in JSON. |

**Profile detection** is keyword + ID-pattern scoring over concatenated extracted text and filenames. Profiles include Amazon 856, Delhaize, Fleet Farm, Burlington, SPS/Topco, Walmart, DO IT BEST, and **BluJay 210** (EDI 210). Only registered **`plugin_key`** values in `core/plugin_registry.py` can execute.

## Data contracts the agent should respect

- **Spec bundle** (`data/specs/<specId>.json`): includes `specId`, `documents` (with `sha256`), `points`, `pointGroups`, `validationMode`, `detectedProfile`, `validator` block (`buildVersion`, `type`, paths, `rulesHash`).
- **Binding errors**: HTTP **409** if manifest/rules missing or fingerprints between bundle and manifest disagree — user must **re-upload** the spec; do not reuse another `specId`’s rules silently.
- **API** (Flask `app.py`):
  - `POST /api/spec/upload` — multipart field name **`specFiles`** (multiple files).
  - `POST /api/validate` — JSON `{ "specId": "...", "ediMessage": "..." }`.
  - `GET /api/spec/<specId>` — returns stored bundle.
  - `GET /api/report/<reportId>` — Markdown download.

Frontend (`static/app.js`) calls these with **same-origin** relative URLs; there is **no separate SPA build** — one Flask process serves UI + API.

## Repository layout requirement

- Web app root: **`edi_validate_web_app/`** (run `python3 app.py` from here; default **0.0.0.0:5050**).
- **`core/plugin_registry.py`** inserts **parent of `edi_validate_web_app`** (the **Validation EDI** repo root) into `sys.path` and imports modules such as `validate_*_856_spec.py`, `edi_210_validator.py`, **`edi856_common.py`**.

**Deploy / clone rule**: Ship **the whole Validation EDI tree** (or equivalent) so parent-level Python modules and `edi_validate_web_app` stay two levels apart as in development. Copying only the `edi_validate_web_app` folder **breaks plugins**.

## Python dependencies (minimal)

- **Flask**, **pandas**, **pdfplumber**, **openpyxl** (for `.xlsx` via pandas).

Plugins may pull additional imports from sibling repo files; satisfy those when running full built-in profile mode.

## Extending built-in plugins

1. Implement validator callable consistent with existing `validate_*_856_spec.py` patterns (returns list of dicts with `message`, `severity`, `segment`, `element`, `code`, etc.).
2. Register in **`core/plugin_registry.py`** (`PLUGIN_REGISTRY`).
3. Add **`ProfilePattern`** in **`core/profile_detector.py`** (keywords + id_patterns + `key` matching registry).
4. Restart the Flask process.

## Security and operations posture (from product intent)

- Designed for **trusted LAN / internal** use: no auth, no RBAC, no audit DB.
- Has allow-list uploads, size limits, safe filenames, restricted report paths, allow-listed plugins only.
- **Do not** expose debug Flask directly to the public internet; use a production WSGI + reverse proxy if externally reachable.

## When another agent should load this skill

- Explaining or automating **EDI Validate Studio** workflows.
- Debugging **409 binding**, **missing generated_validators**, or **plugin import** errors.
- Describing how **spec-bound** validation differs from “one global validator for all specs.”
- Planning deployment (paths, ports, co-hosting with Nginx).

## Quick run (for humans or agent-driven shells)

```bash
cd /path/to/Validation\ EDI/edi_validate_web_app
python3 app.py
# Open http://127.0.0.1:5050
```

## Optional deep reference

For full JSON field shapes and UI copy, read **`edi_validate_web_app/README.md`** in the repo when detail is needed.
