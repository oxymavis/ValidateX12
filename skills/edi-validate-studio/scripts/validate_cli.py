#!/usr/bin/env python3
"""Headless EDI validation using the same engine as edi_validate_web_app (no Flask).

Requires the Validation EDI monorepo: edi_validate_web_app/ + parent-level validators.

Usage:
  python scripts/validate_cli.py --spec ./guide.pdf --edi ./message.edi
  python scripts/validate_cli.py --spec a.pdf b.xlsx --edi - < message.edi
  python validate_cli.py --repo /path/to/Validation\\ EDI --spec spec.pdf --edi msg.edi

Environment:
  VALIDATION_EDI_ROOT  Optional absolute path to repo root (overrides auto-detect).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def _repo_root(cli_repo: str | None) -> Path:
    if cli_repo:
        return Path(cli_repo).resolve()
    env = os.environ.get("VALIDATION_EDI_ROOT", "").strip()
    if env:
        return Path(env).resolve()
    # skills/edi-validate-studio/scripts/this.py -> parents[3] = Validation EDI root
    return Path(__file__).resolve().parents[3]


def _bootstrap_paths(repo: Path) -> Path:
    web = repo / "edi_validate_web_app"
    if not web.is_dir():
        print(f"error: edi_validate_web_app not found under {repo}", file=sys.stderr)
        sys.exit(2)
    sys.path.insert(0, str(web))
    sys.path.insert(0, str(repo))
    return web


def findings_summary(findings: list[Any]) -> dict[str, int]:
    return {
        "total": len(findings),
        "errors": sum(1 for item in findings if item.severity == "Error"),
        "warnings": sum(1 for item in findings if item.severity != "Error"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run EDI Validate Studio engine without HTTP.")
    parser.add_argument(
        "--repo",
        default=None,
        help="Validation EDI repository root (default: parent of skills/ or VALIDATION_EDI_ROOT)",
    )
    parser.add_argument(
        "--spec",
        action="append",
        dest="specs",
        required=True,
        help="Spec file path (repeat for multiple files)",
    )
    parser.add_argument(
        "--edi",
        required=True,
        help="EDI message file path, or - for stdin",
    )
    args = parser.parse_args()

    repo = _repo_root(args.repo)
    web = _bootstrap_paths(repo)
    os.chdir(web)

    from core.generic_validator import validate_generic
    from core.parsers import extract_text
    from core.plugin_registry import plugin_available, run_plugin_validation
    from core.profile_detector import detect_profile
    from core.result_merger import merge_findings
    from core.rule_extractor import compile_points, group_points
    from core.schemas import ValidationFinding, ValidationPoint

    file_payloads: list[tuple[str, bytes]] = []
    unsupported: list[dict[str, str]] = []
    extracted_texts: list[str] = []
    all_points: list[ValidationPoint] = []

    for path_str in args.specs:
        path = Path(path_str).expanduser()
        if not path.is_file():
            print(f"error: spec file not found: {path}", file=sys.stderr)
            sys.exit(2)
        file_name = path.name
        file_bytes = path.read_bytes()
        try:
            text = extract_text(file_name, file_bytes)
            extracted_texts.append(text)
            file_payloads.append((file_name, file_bytes))
        except Exception as exc:
            unsupported.append({"fileName": file_name, "reason": str(exc)})

    if not file_payloads:
        print(
            json.dumps({"error": "All spec files failed to parse.", "unsupported": unsupported}, ensure_ascii=False),
            file=sys.stderr,
        )
        sys.exit(1)

    for (file_name, _file_bytes) in file_payloads:
        text = extract_text(file_name, _file_bytes)
        all_points.extend(compile_points(file_name, text))

    doc_names = [fn for fn, _ in file_payloads]
    detected_profile = detect_profile(extracted_texts, doc_names)
    validation_mode = "built_in_profile" if plugin_available(detected_profile) else "generated_spec"

    detected_profile_payload = None
    if detected_profile:
        detected_profile_payload = {
            "name": detected_profile.name,
            "kind": detected_profile.kind,
            "confidence": detected_profile.confidence,
            "matchReason": detected_profile.match_reason,
            "pluginKey": detected_profile.plugin_key,
        }

    if args.edi == "-":
        edi_message = sys.stdin.read()
    else:
        edi_path = Path(args.edi).expanduser()
        if not edi_path.is_file():
            print(f"error: EDI file not found: {edi_path}", file=sys.stderr)
            sys.exit(2)
        edi_message = edi_path.read_text(encoding="utf-8", errors="replace")

    edi_message = edi_message.strip()
    if not edi_message:
        print(json.dumps({"error": "ediMessage is empty."}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    generic_findings: list[ValidationFinding] = []
    plugin_findings: list[ValidationFinding] = []
    plugin_error: str | None = None

    if detected_profile and validation_mode == "built_in_profile":
        try:
            profile_obj = SimpleNamespace(
                name=detected_profile.name,
                kind=detected_profile.kind,
                confidence=detected_profile.confidence,
                match_reason=detected_profile.match_reason,
                plugin_key=detected_profile.plugin_key,
            )
            plugin_findings = run_plugin_validation(profile_obj, edi_message)
        except Exception as exc:
            plugin_error = str(exc)
            validation_mode = "generated_spec"
            generic_findings = validate_generic(edi_message, all_points)
    else:
        generic_findings = validate_generic(edi_message, all_points)

    findings = merge_findings(generic_findings, plugin_findings)

    out: dict[str, Any] = {
        "validationMode": validation_mode,
        "summary": findings_summary(findings),
        "findings": [item.to_dict() for item in findings],
        "detectedProfile": detected_profile_payload,
        "specSummary": {
            "totalPoints": len(all_points),
            "compiledPoints": sum(1 for p in all_points if p.compiled),
            "informationalPoints": sum(1 for p in all_points if not p.compiled),
        },
        "pointGroups": group_points(all_points),
        "unsupported": unsupported,
    }
    if plugin_error:
        out["fallback"] = {
            "messageZh": "内置插件校验失败，已回退到通用规则引擎。",
            "messageEn": "Built-in profile validation failed. The app fell back to the generic rule engine.",
            "details": plugin_error,
        }

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
