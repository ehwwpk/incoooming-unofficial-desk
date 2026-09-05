(() => {
  const input = document.querySelector("[data-source-files]");
  const status = document.querySelector("[data-source-file-status]");
  if (!(input instanceof HTMLInputElement) || !(status instanceof HTMLElement)) return;

  input.addEventListener("change", () => {
    const files = Array.from(input.files ?? []);
    if (files.length === 0) {
      status.textContent = "No files selected · 10 MB per file";
      return;
    }

    const names = files.slice(0, 2).map((file) => file.name);
    const remaining = files.length - names.length;
    status.textContent = `${files.length} file${files.length === 1 ? "" : "s"} ready · ${names.join(" + ")}${remaining > 0 ? ` + ${remaining} more` : ""}`;
  });
})();

(() => {
  const form = document.querySelector(".csv-import-form");
  if (!(form instanceof HTMLFormElement)) return;
  const preview = form.querySelector("[data-import-preview]");
  const fingerprint = form.querySelector("[data-preview-fingerprint]");
  const submit = form.querySelector("[data-import-submit]");
  if (!(preview instanceof HTMLElement) || !(fingerprint instanceof HTMLInputElement) || !(submit instanceof HTMLButtonElement)) return;

  const maxFiles = 8;
  const maxFileBytes = 10 * 1024 * 1024;
  let revision = 0;
  let reviewed = null;
  let activeRequest = null;
  let committing = false;
  let committed = false;

  const clearPreview = () => {
    if (committing || committed) return;
    revision += 1;
    reviewed = null;
    activeRequest?.abort();
    activeRequest = null;
    fingerprint.value = "";
    preview.hidden = true;
    preview.replaceChildren();
    submit.disabled = false;
    submit.innerHTML = "REVIEW FILES <span>&rarr;</span>";
  };

  const prepareUpload = async (selectedRevision) => {
    const original = new FormData(form);
    const files = original.getAll("files");
    if (!files.length || files.some((file) => !(file instanceof File) || !file.name)) {
      throw new Error("Choose your CSV files first.");
    }
    if (files.length > maxFiles) throw new Error("Choose no more than eight CSV files at once.");
    if (files.some((file) => file.size > maxFileBytes)) {
      throw new Error("Each CSV file must be 10 MB or smaller.");
    }
    const payload = new FormData();
    for (const [name, value] of original.entries()) {
      if (name !== "files") payload.append(name, value);
    }
    // Some Safari versions drop an entire multipart body with disk-backed File entries.
    // Memory-backed Blobs preserve the exact bytes for both preview and final import.
    // https://bugs.webkit.org/show_bug.cgi?id=319985
    for (const file of files) {
      let bytes;
      try {
        bytes = await file.arrayBuffer();
      } catch {
        throw new Error("A selected file could not be read. Download it to this computer, then choose it again.");
      }
      if (selectedRevision !== revision) return null;
      if (bytes.byteLength !== file.size || bytes.byteLength > maxFileBytes) {
        throw new Error("A selected file changed while it was being read. Choose your files again.");
      }
      payload.append("files", new Blob([bytes], { type: file.type || "text/csv" }), file.name);
    }
    return payload;
  };

  form.addEventListener("input", clearPreview);
  form.addEventListener("change", clearPreview);
  form.addEventListener("reset", (event) => {
    if (committing || committed) event.preventDefault();
    else clearPreview();
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (activeRequest || committed) return;
    const selectedRevision = revision;
    const controller = new AbortController();
    activeRequest = controller;
    const isCommit = reviewed !== null && fingerprint.value !== "";
    let disabledControls = [];
    submit.disabled = true;
    submit.textContent = isCommit ? "IMPORTING BOOK..." : "READING FILES...";
    try {
      const payload = isCommit ? reviewed : await prepareUpload(selectedRevision);
      if (selectedRevision !== revision || !payload) return;
      if (isCommit) {
        // Capture first: disabled controls are omitted when constructing FormData.
        payload.set("preview_fingerprint", fingerprint.value);
        committing = true;
        disabledControls = [...form.querySelectorAll("input, select, textarea")]
          .filter((control) => !control.disabled);
        disabledControls.forEach((control) => { control.disabled = true; });
      }
      const response = await fetch(isCommit ? "/sources/csv" : "/sources/csv/preview", {
        method: "POST",
        headers: { Accept: "application/json" },
        body: payload,
        signal: controller.signal,
      });
      const body = await response.json();
      if (selectedRevision !== revision) return;
      if (!response.ok || !body.ok) {
        throw new Error(body.error || (isCommit
          ? "The import was not confirmed. Open BOOK and check your saved books before trying again."
          : "These files could not be previewed. Choose them again and check the selected broker format."));
      }
      if (isCommit) {
        // Keep a confirmed import locked while navigation is pending.
        committed = true;
        reviewed = null;
        fingerprint.value = "";
        submit.textContent = "OPENING BOOK...";
        window.location.assign("/");
        return;
      }
      const fileRows = body.files.map((file) => {
        const issues = file.issues.map((issue) => `<small class="csv-preview-issue">ROW ${issue.row} / ${escapeText(issue.status.toUpperCase().replace("_", " "))} / ${escapeText(issue.reason)}</small>`).join("");
        return `<li><b>${escapeText(file.name)}</b><span>${escapeText(file.broker.toUpperCase())} / ${escapeText(file.profile)} / ${file.imported} IMPORTED / ${file.review} REVIEW / ${file.rejected} REJECTED</span>${issues}</li>`;
      }).join("");
      const warnings = body.warnings.map((warning) => `<p>${escapeText(warning)}</p>`).join("");
      preview.innerHTML = `<header><b>IMPORT PREVIEW</b><span>${body.counts.positions} POSITIONS / ${body.counts.activity} ACTIVITY</span></header><ul>${fileRows}</ul>${warnings}`;
      preview.hidden = false;
      reviewed = body.can_commit ? payload : null;
      fingerprint.value = body.can_commit ? body.fingerprint : "";
      submit.innerHTML = body.can_commit
        ? "IMPORT REVIEWED BOOK <span>&rarr;</span>"
        : "REVIEW FILES <span>&rarr;</span>";
      preview.scrollIntoView({ block: "nearest", behavior: "smooth" });
    } catch (error) {
      if (selectedRevision !== revision) return;
      if (committed) {
        preview.innerHTML = "<p>Your book was imported. Open BOOK to see it.</p>";
        preview.hidden = false;
        return;
      }
      reviewed = null;
      fingerprint.value = "";
      const message = isCommit && (error instanceof TypeError || error instanceof SyntaxError)
        ? "The import was not confirmed. Open BOOK and check your saved books before trying again."
        : error instanceof Error ? error.message : "The files could not be read. Choose them again.";
      preview.innerHTML = `<p>${escapeText(message)}</p>`;
      preview.hidden = false;
      submit.innerHTML = "REVIEW FILES <span>&rarr;</span>";
    } finally {
      if (!committed) disabledControls.forEach((control) => { control.disabled = false; });
      if (activeRequest === controller && !committed) {
        activeRequest = null;
        committing = false;
        submit.disabled = false;
      }
    }
  });

  function escapeText(value) {
    const node = document.createElement("span");
    node.textContent = String(value);
    return node.innerHTML;
  }
})();
