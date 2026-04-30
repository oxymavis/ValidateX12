const state = {
  specId: "",
  validationMode: "",
  downloadUrl: "",
};

const specForm = document.getElementById("spec-form");
const validateBtn = document.getElementById("validate-btn");
const downloadLink = document.getElementById("download-link");
const ediMessage = document.getElementById("edi-message");

function setStatus(id, message, kind = "muted") {
  const el = document.getElementById(id);
  el.textContent = message;
  el.className = `status ${kind}`;
}

function setHidden(id, hidden) {
  document.getElementById(id).classList.toggle("hidden", hidden);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderDocuments(documents) {
  const container = document.getElementById("documents-box");
  container.innerHTML = "";
  const tpl = document.getElementById("document-template");
  documents.forEach((doc) => {
    const node = tpl.content.cloneNode(true);
    node.querySelector(".doc-name").textContent = doc.file_name || doc.fileName;
    node.querySelector(".doc-type").textContent = (doc.file_type || doc.fileType || "").toUpperCase();
    node.querySelector(".document-meta").innerHTML =
      `Characters: <strong>${doc.characters}</strong><br>Stored Path: <code>${escapeHtml(doc.stored_path || doc.storedPath || "")}</code>`;
    container.appendChild(node);
  });
}

function renderUnsupported(items) {
  const container = document.getElementById("unsupported-box");
  container.innerHTML = "";
  if (!items || !items.length) {
    return;
  }
  const card = document.createElement("article");
  card.className = "card document-card";
  const rows = items.map((item) => `<li><strong>${escapeHtml(item.fileName)}</strong>: ${escapeHtml(item.reason)}</li>`).join("");
  card.innerHTML = `<strong>Unsupported / Failed Files</strong><ul>${rows}</ul>`;
  container.appendChild(card);
}

function renderMode(payload) {
  setHidden("mode-card", false);
  document.getElementById("mode-label").textContent =
    payload.validationMode === "built_in_profile" ? "Dedicated Spec + Built-in Profile Plugin" : "Dedicated Spec Validator";
  if (payload.detectedProfile) {
    document.getElementById("profile-label").textContent = payload.detectedProfile.name;
    document.getElementById("profile-reason").textContent = payload.detectedProfile.matchReason;
  } else {
    document.getElementById("profile-label").textContent = "No built-in profile matched";
    document.getElementById("profile-reason").textContent = "This upload generated its own dedicated validator build. No other spec rules will be reused.";
  }
  const validator = payload.validator || {};
  document.getElementById("spec-id-label").textContent = payload.specId || "-";
  document.getElementById("validator-build-label").textContent = validator.buildVersion || "-";
  document.getElementById("rules-path-label").textContent = validator.rulesPath || "-";
  document.getElementById("rules-hash-label").textContent = validator.rulesHash || "-";
}

function renderPointGroups(groups) {
  const container = document.getElementById("point-groups");
  const groupTpl = document.getElementById("point-group-template");
  const itemTpl = document.getElementById("point-item-template");
  container.innerHTML = "";

  groups.forEach((group) => {
    const groupNode = groupTpl.content.cloneNode(true);
    groupNode.querySelector("h3").textContent = group.category;
    groupNode.querySelector(".count-pill").textContent = `${group.count} points`;
    const itemsHost = groupNode.querySelector(".point-items");

    group.items.forEach((point) => {
      const itemNode = itemTpl.content.cloneNode(true);
      itemNode.querySelector(".point-title").textContent = point.title;
      itemNode.querySelector(".point-pill").textContent = point.compiled ? "Executable" : "Informational";
      itemNode.querySelector(".point-meta").innerHTML =
        `Source: <strong>${escapeHtml(point.source_file)}</strong><br>` +
        `Rule: <code>${escapeHtml(point.rule_type)}</code>` +
        (point.segment ? ` · Segment: <code>${escapeHtml(point.segment)}</code>` : "") +
        (point.element ? ` · Element: <code>${escapeHtml(point.element)}</code>` : "") +
        (point.qualifier ? ` · Qualifier: <code>${escapeHtml(point.qualifier)}</code>` : "") +
        (point.expected && point.expected.length ? ` · Expected: <code>${escapeHtml(point.expected.join(" / "))}</code>` : "");
      itemNode.querySelector(".point-line").textContent = point.source_line;
      itemsHost.appendChild(itemNode);
    });

    container.appendChild(groupNode);
  });
}

function renderSpecSummary(summary) {
  setHidden("spec-summary", false);
  document.getElementById("metric-total").textContent = summary.totalPoints;
  document.getElementById("metric-compiled").textContent = summary.compiledPoints;
  document.getElementById("metric-info").textContent = summary.informationalPoints;
}

function renderFindings(findings) {
  const container = document.getElementById("findings-list");
  const tpl = document.getElementById("finding-template");
  container.innerHTML = "";

  findings.forEach((finding) => {
    const node = tpl.content.cloneNode(true);
    const card = node.querySelector(".finding-card");
    const severity = String(finding.severity || "Error").toLowerCase();
    card.classList.add(severity);
    const pill = node.querySelector(".severity-pill");
    pill.classList.add(severity);
    pill.textContent = finding.severity;
    node.querySelector(".finding-code").textContent = finding.code;
    node.querySelector(".finding-meta").innerHTML =
      `Segment: <code>${escapeHtml(finding.segment || "-")}</code> · Element: <code>${escapeHtml(finding.element || "-")}</code> · Source: <strong>${escapeHtml(finding.source)}</strong>`;
    node.querySelector(".finding-zh").textContent = `中文：${finding.messageZh}`;
    node.querySelector(".finding-en").textContent = `English: ${finding.messageEn}`;
    const raw = finding.rawSegment
      ? `Line ${finding.rawSegmentIndex || "-"}\n${finding.rawSegment}`
      : "No matching raw segment could be attached to this finding.";
    node.querySelector(".finding-raw").textContent = raw;
    container.appendChild(node);
  });
}

function renderFindingSummary(summary) {
  setHidden("finding-summary", false);
  document.getElementById("finding-total").textContent = summary.total;
  document.getElementById("finding-errors").textContent = summary.errors;
  document.getElementById("finding-warnings").textContent = summary.warnings;
}

specForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const fileInput = document.getElementById("spec-files");
  if (!fileInput.files.length) {
    setStatus("spec-status", "Please upload at least one spec file.", "warning");
    return;
  }

  setStatus("spec-status", "Extracting validation points from uploaded spec files...", "muted");
  const formData = new FormData(specForm);

  try {
    const response = await fetch("/api/spec/upload", {
      method: "POST",
      body: formData,
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Failed to upload spec files.");
    }

    state.specId = payload.specId;
    state.validationMode = payload.validationMode;
    validateBtn.disabled = false;
    renderSpecSummary(payload.summary);
    renderDocuments(payload.documents);
    renderUnsupported(payload.unsupported || []);
    renderPointGroups(payload.pointGroups);
    renderMode(payload);
    setStatus("spec-status", `Spec processed successfully. Dedicated validator build ${payload.validator?.buildVersion || "v1"} is bound to spec ${payload.specId}.`, "muted");
    setStatus("validation-status", "Spec is ready. Validation will use only this spec-bound validator.", "muted");
  } catch (error) {
    setStatus("spec-status", error.message, "warning");
  }
});

validateBtn.addEventListener("click", async () => {
  if (!state.specId) {
    setStatus("validation-status", "Upload a spec first.", "warning");
    return;
  }
  if (!ediMessage.value.trim()) {
    setStatus("validation-status", "Paste an EDI message before validating.", "warning");
    return;
  }

  setStatus("validation-status", "Running validation...", "muted");
  setHidden("fallback-status", true);

  try {
    const response = await fetch("/api/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        specId: state.specId,
        ediMessage: ediMessage.value,
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Validation failed.");
    }

    renderFindingSummary(payload.summary);
    renderFindings(payload.findings);
    state.downloadUrl = payload.downloadUrl;
    downloadLink.href = payload.downloadUrl;
    downloadLink.classList.remove("disabled");
    setStatus("validation-status", `Validation completed in ${payload.validationMode} mode for spec ${state.specId}.`, "muted");

    if (payload.fallback) {
      const fallback = document.getElementById("fallback-status");
      fallback.textContent = `${payload.fallback.messageZh} ${payload.fallback.messageEn}`;
      setHidden("fallback-status", false);
    }
  } catch (error) {
    setStatus("validation-status", error.message, "warning");
  }
});
