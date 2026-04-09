#!/usr/bin/env python3
from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

from flask import Flask, jsonify, render_template, request, send_file

from core.generic_validator import validate_generic
from core.parsers import extract_text
from core.plugin_registry import plugin_available, run_plugin_validation
from core.profile_detector import detect_profile
from core.report_writer import findings_to_markdown
from core.result_merger import merge_findings
from core.rule_extractor import compile_points, group_points
from core.schemas import UploadedDocument, ValidationFinding, ValidationPoint
from core.storage import (
    load_generated_manifest,
    load_generated_rules,
    load_spec_bundle,
    report_path,
    save_report,
    save_spec_bundle,
    save_uploads,
    timestamp_iso,
    write_generated_artifacts,
)


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024


def document_fingerprints(documents: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "fileName": str(item.get("fileName", item.get("file_name", ""))),
            "sha256": str(item.get("sha256", "")),
        }
        for item in documents
    ]


def validate_spec_binding(bundle: dict[str, Any], manifest: dict[str, Any], requested_spec_id: str) -> str | None:
    if str(bundle.get("specId", "")) != requested_spec_id:
        return "Spec binding mismatch: the requested spec does not match the stored bundle."
    if str(manifest.get("specId", "")) != requested_spec_id:
        return "Spec binding mismatch: the generated validator does not belong to this spec."
    bundle_docs = document_fingerprints(bundle.get("documents", []))
    manifest_docs = document_fingerprints(manifest.get("sourceFiles", []))
    if bundle_docs != manifest_docs:
        return "Spec binding mismatch: validator source fingerprints do not match the uploaded spec."
    return None


def findings_summary(findings: list[ValidationFinding]) -> dict[str, int]:
    return {
        "total": len(findings),
        "errors": sum(1 for item in findings if item.severity == "Error"),
        "warnings": sum(1 for item in findings if item.severity != "Error"),
    }


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.get("/api/spec/<spec_id>")
def get_spec(spec_id: str) -> Any:
    try:
        bundle = load_spec_bundle(spec_id)
    except FileNotFoundError:
        return jsonify({"error": "Spec bundle not found."}), 404
    return jsonify(bundle)


@app.post("/api/spec/upload")
def upload_spec() -> Any:
    files = request.files.getlist("specFiles")
    if not files:
        return jsonify({"error": "No spec files uploaded."}), 400

    file_payloads = []
    unsupported = []
    extracted_texts: list[str] = []
    documents: list[UploadedDocument] = []
    all_points: list[ValidationPoint] = []
    spec_id = uuid.uuid4().hex[:12]
    extracted_by_name: dict[str, str] = {}

    for uploaded in files:
        file_name = uploaded.filename or "untitled"
        file_bytes = uploaded.read()
        try:
            text = extract_text(file_name, file_bytes)
            extracted_texts.append(text)
            extracted_by_name[file_name] = text
            file_payloads.append((file_name, file_bytes))
        except Exception as exc:
            unsupported.append({"fileName": file_name, "reason": str(exc)})
            continue

    if not file_payloads:
        return jsonify({"error": "All files failed to parse.", "unsupported": unsupported}), 400

    saved = save_uploads(spec_id, file_payloads)
    for (file_name, _file_bytes), stored in zip(file_payloads, saved):
        text = extracted_by_name[file_name]
        suffix = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else "txt"
        document = UploadedDocument(
            file_name=file_name,
            file_type=suffix,
            stored_path=stored["stored_path"],
            characters=len(text),
            sha256=stored["sha256"],
        )
        documents.append(document)
        all_points.extend(compile_points(file_name, text))

    detected_profile = detect_profile(extracted_texts, [doc.file_name for doc in documents])
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

    source_files = [
        {
            "fileName": doc.file_name,
            "storedPath": doc.stored_path,
            "sha256": doc.sha256,
        }
        for doc in documents
    ]
    manifest = {
        "specId": spec_id,
        "specName": " / ".join(doc.file_name for doc in documents),
        "buildVersion": "v1",
        "validatorType": validation_mode,
        "pluginKey": detected_profile.plugin_key if plugin_available(detected_profile) else "",
        "createdAt": timestamp_iso(),
        "sourceFiles": source_files,
    }
    generated = write_generated_artifacts(
        spec_id,
        manifest,
        {
            "specId": spec_id,
            "buildVersion": "v1",
            "points": [point.to_dict() for point in all_points],
        },
    )

    payload = {
        "specId": spec_id,
        "specName": " / ".join(doc.file_name for doc in documents),
        "documents": [doc.to_dict() for doc in documents],
        "detectedProfile": detected_profile_payload,
        "validationMode": validation_mode,
        "validator": {
            "buildVersion": "v1",
            "type": validation_mode,
            "manifestPath": generated["manifestPath"],
            "rulesPath": generated["rulesPath"],
            "validatorPath": generated["validatorPath"],
            "rulesHash": generated["rulesHash"],
        },
        "summary": {
            "totalPoints": len(all_points),
            "compiledPoints": sum(1 for point in all_points if point.compiled),
            "informationalPoints": sum(1 for point in all_points if not point.compiled),
        },
        "pointGroups": group_points(all_points),
        "points": [point.to_dict() for point in all_points],
        "unsupported": unsupported,
        "createdAt": timestamp_iso(),
    }
    save_spec_bundle(spec_id, payload)
    return jsonify(payload)


@app.post("/api/validate")
def validate() -> Any:
    payload = request.get_json(force=True, silent=True) or {}
    spec_id = str(payload.get("specId", "")).strip()
    edi_message = str(payload.get("ediMessage", "")).strip()
    if not spec_id:
        return jsonify({"error": "specId is required."}), 400
    if not edi_message:
        return jsonify({"error": "ediMessage is required."}), 400

    try:
        bundle = load_spec_bundle(spec_id)
    except FileNotFoundError:
        return jsonify({"error": "Spec bundle not found."}), 404

    validator_info = bundle.get("validator") or {}
    build_version = str(validator_info.get("buildVersion", "v1"))
    try:
        manifest = load_generated_manifest(spec_id, build_version)
        binding_error = validate_spec_binding(bundle, manifest, spec_id)
        if binding_error:
            return jsonify({"error": binding_error}), 409
        rules_payload = load_generated_rules(spec_id, build_version)
    except FileNotFoundError:
        return jsonify({"error": "Dedicated validator artifacts are missing for this spec. Re-upload the spec."}), 409

    points = [ValidationPoint(**point) for point in rules_payload.get("points", [])]
    generic_findings: list[ValidationFinding] = []
    plugin_findings: list[ValidationFinding] = []
    plugin_error = None

    detected_profile = bundle.get("detectedProfile")
    validation_mode = bundle.get("validationMode", "generated_spec")
    if detected_profile and validation_mode == "built_in_profile":
        try:
            profile_obj = SimpleNamespace(
                name=detected_profile.get("name", ""),
                kind=detected_profile.get("kind", ""),
                confidence=detected_profile.get("confidence", ""),
                match_reason=detected_profile.get("matchReason", detected_profile.get("match_reason", "")),
                plugin_key=detected_profile.get("pluginKey", detected_profile.get("plugin_key", "")),
            )
            plugin_findings = run_plugin_validation(profile_obj, edi_message)
        except Exception as exc:
            plugin_error = str(exc)
            validation_mode = "generated_spec"
            generic_findings = validate_generic(edi_message, points)
    else:
        generic_findings = validate_generic(edi_message, points)

    findings = merge_findings(generic_findings, plugin_findings)
    report_id = uuid.uuid4().hex[:12]
    report_md = findings_to_markdown(
        bundle.get("specName", "Uploaded spec"),
        validation_mode,
        findings,
        spec_id=spec_id,
        build_version=build_version,
        validator_type=str(validator_info.get("type", validation_mode)),
    )
    save_report(report_id, report_md)

    response = {
        "validationMode": validation_mode,
        "summary": findings_summary(findings),
        "findings": [item.to_dict() for item in findings],
        "downloadUrl": f"/api/report/{report_id}",
    }
    if plugin_error:
        response["fallback"] = {
            "messageZh": "内置插件校验失败，已回退到通用规则引擎。",
            "messageEn": "Built-in profile validation failed. The app fell back to the generic rule engine.",
            "details": plugin_error,
        }
    return jsonify(response)


@app.get("/api/report/<report_id>")
def download_report(report_id: str) -> Any:
    path = report_path(report_id)
    if not path.exists():
        return jsonify({"error": "Report not found."}), 404
    return send_file(path, mimetype="text/markdown", as_attachment=True, download_name=f"edi-validation-{report_id}.md")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)
