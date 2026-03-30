# EDI Validate Studio

## Overview

EDI Validate Studio is a generic web-based EDI validation platform.

It lets users:

- upload customer spec files in `PDF / DOCX / XLS / XLSX / TXT / MD`
- extract validation points from those files
- generate a spec-bound validator build for each upload
- distinguish executable rules from informational notes
- paste an EDI message and run validation
- view bilingual findings in Chinese and English
- download a Markdown report

The product is intentionally generic. Built-in profile validators are included only as optional example plugins.

## Features

- Spec-bound validator generation for every upload
- Generic rule runtime behind generated validators
- Optional built-in profile enhancement
- Bilingual validation findings
- Markdown report export
- Local project-directory persistence
- LAN-friendly Flask app

## Supported Files

- `.pdf`
- `.docx`
- `.xlsx`
- `.xls`
- `.txt`
- `.md`

## Built-in Example Profiles

The app can detect and enhance validation for these built-in example profiles:

- Amazon Warehouse
- Delhaize America
- Fleet Farm
- Burlington Coat Factory
- SPS / Topco
- Walmart USA
- DO IT BEST HARDWARE

These are optional plugin-style enhancements. Each upload still gets its own dedicated validator build, and validation is bound to that upload's `spec_id`.

## Project Structure

```text
edi_validate_web_app/
  app.py
  README.md
  core/
  templates/
  static/
  data/
```

## Run

From the project root:

```bash
cd edi_validate_web_app
python3 app.py
```

Default bind:

- Host: `0.0.0.0`
- Port: `5050`

Access URLs:

- Local machine: `http://127.0.0.1:5050`
- LAN: `http://<your-lan-ip>:5050`

## Storage

Uploaded specs, extracted bundles, and generated reports are stored in:

- `data/uploads/`
- `data/specs/`
- `data/generated_validators/`
- `data/reports/`

Each upload creates a dedicated validator artifact set:

- `manifest.json`
- `rules.json`
- `validator.py`

Validation requests are bound to the current `spec_id`. The app will not silently reuse another spec's rules.

The app does not auto-delete files in V1.

## Security Notes

This version is designed for trusted LAN environments.

It includes:

- upload file type allow-list
- upload size limit
- safe file naming
- report download path restriction
- built-in plugin allow-list only

It does not include:

- login
- role-based access control
- database-backed audit logs

Do not expose this version directly to the public internet.

## Known Limitations

- Natural-language rule extraction is heuristic-based, not perfect
- Some complex business semantics are shown as informational points only
- Old `.xls` parsing may fall back to lower-quality text extraction
- Built-in plugin results depend on the quality of the existing validator scripts

## Add a New Built-in Plugin

1. Add a new validator function in the main repo, following the existing `validate_*_856_spec.py` pattern.
2. Register it in [`core/plugin_registry.py`](./core/plugin_registry.py).
3. Add matching keywords and ID patterns in [`core/profile_detector.py`](./core/profile_detector.py).
4. Restart the app.
