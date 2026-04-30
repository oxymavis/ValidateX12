from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
SPECS_DIR = DATA_DIR / "specs"
REPORTS_DIR = DATA_DIR / "reports"
CACHE_DIR = DATA_DIR / "cache"
GENERATED_VALIDATORS_DIR = DATA_DIR / "generated_validators"

for path in (UPLOADS_DIR, SPECS_DIR, REPORTS_DIR, CACHE_DIR, GENERATED_VALIDATORS_DIR):
    path.mkdir(parents=True, exist_ok=True)


def timestamp_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def safe_filename(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in name).strip()
    return cleaned or "upload.bin"


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def save_uploads(spec_id: str, files: Iterable[tuple[str, bytes]]) -> List[Dict[str, str]]:
    spec_dir = UPLOADS_DIR / spec_id
    spec_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for file_name, file_bytes in files:
        safe_name = safe_filename(file_name)
        path = spec_dir / safe_name
        path.write_bytes(file_bytes)
        saved.append(
            {
                "file_name": safe_name,
                "stored_path": str(path.relative_to(BASE_DIR)),
                "sha256": sha256_hex(file_bytes),
            }
        )
    return saved


def save_spec_bundle(spec_id: str, payload: Dict[str, Any]) -> Path:
    path = SPECS_DIR / f"{spec_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_spec_bundle(spec_id: str) -> Dict[str, Any]:
    path = SPECS_DIR / f"{spec_id}.json"
    if not path.exists():
        raise FileNotFoundError(spec_id)
    return json.loads(path.read_text(encoding="utf-8"))


def save_report(report_id: str, markdown: str) -> Path:
    path = REPORTS_DIR / f"{report_id}.md"
    path.write_text(markdown, encoding="utf-8")
    return path


def report_path(report_id: str) -> Path:
    return REPORTS_DIR / f"{report_id}.md"


def generated_validator_dir(spec_id: str, build_version: str = "v1") -> Path:
    path = GENERATED_VALIDATORS_DIR / spec_id / build_version
    path.mkdir(parents=True, exist_ok=True)
    return path


def generated_manifest_path(spec_id: str, build_version: str = "v1") -> Path:
    return generated_validator_dir(spec_id, build_version) / "manifest.json"


def generated_rules_path(spec_id: str, build_version: str = "v1") -> Path:
    return generated_validator_dir(spec_id, build_version) / "rules.json"


def generated_validator_path(spec_id: str, build_version: str = "v1") -> Path:
    return generated_validator_dir(spec_id, build_version) / "validator.py"


def write_generated_artifacts(spec_id: str, manifest: Dict[str, Any], rules_payload: Dict[str, Any]) -> Dict[str, str]:
    rules_json = json.dumps(rules_payload, ensure_ascii=False, indent=2)
    rules_hash = sha256_hex(rules_json.encode("utf-8"))
    manifest = dict(manifest)
    manifest["rulesHash"] = rules_hash

    build_version = str(manifest.get("buildVersion", "v1"))
    base_dir = generated_validator_dir(spec_id, build_version)
    manifest_file = generated_manifest_path(spec_id, build_version)
    rules_file = generated_rules_path(spec_id, build_version)
    validator_file = generated_validator_path(spec_id, build_version)

    rules_file.write_text(rules_json, encoding="utf-8")
    manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    validator_file.write_text(_validator_template(spec_id, build_version), encoding="utf-8")

    return {
        "manifestPath": str(manifest_file.relative_to(BASE_DIR)),
        "rulesPath": str(rules_file.relative_to(BASE_DIR)),
        "validatorPath": str(validator_file.relative_to(BASE_DIR)),
        "rulesHash": rules_hash,
        "buildDir": str(base_dir.relative_to(BASE_DIR)),
    }


def load_generated_manifest(spec_id: str, build_version: str = "v1") -> Dict[str, Any]:
    path = generated_manifest_path(spec_id, build_version)
    if not path.exists():
        raise FileNotFoundError(spec_id)
    return json.loads(path.read_text(encoding="utf-8"))


def load_generated_rules(spec_id: str, build_version: str = "v1") -> Dict[str, Any]:
    path = generated_rules_path(spec_id, build_version)
    if not path.exists():
        raise FileNotFoundError(spec_id)
    return json.loads(path.read_text(encoding="utf-8"))


def _validator_template(spec_id: str, build_version: str) -> str:
    return f"""from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.generic_validator import validate_generic
from core.schemas import ValidationPoint


SPEC_ID = "{spec_id}"
BUILD_VERSION = "{build_version}"
BASE_DIR = Path(__file__).resolve().parent


def load_points() -> list[ValidationPoint]:
    rules_path = BASE_DIR / "rules.json"
    payload = json.loads(rules_path.read_text(encoding="utf-8"))
    return [ValidationPoint(**point) for point in payload.get("points", [])]


def validate(edi_message: str):
    return validate_generic(edi_message, load_points())
"""
