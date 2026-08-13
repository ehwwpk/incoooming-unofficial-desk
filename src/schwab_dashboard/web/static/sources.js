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

  const clearPreview = () => {
    fingerprint.value = "";
    preview.hidden = true;
    preview.replaceChildren();
    submit.innerHTML = "REVIEW FILES <span>&rarr;</span>";
  };
  form.addEventListener("input", clearPreview);
  form.addEventListener("change", clearPreview);
  form.addEventListener("submit", async (event) => {
    if (fingerprint.value) return;
    event.preventDefault();
    submit.disabled = true;
    submit.textContent = "READING FILES...";
    try {
      const response = await fetch("/sources/csv/preview", { method: "POST", body: new FormData(form) });
      const body = await response.json();
      if (!response.ok || !body.ok) throw new Error(body.error || "Preview failed.");
      const fileRows = body.files.map((file) => `<li><b>${escapeText(file.name)}</b><span>${escapeText(file.broker.toUpperCase())} / ${escapeText(file.profile)} / ${file.imported} IMPORTED / ${file.review} REVIEW / ${file.rejected} REJECTED</span></li>`).join("");
      const warnings = body.warnings.map((warning) => `<p>${escapeText(warning)}</p>`).join("");
      preview.innerHTML = `<header><b>IMPORT PREVIEW</b><span>${body.counts.positions} POSITIONS / ${body.counts.activity} ACTIVITY</span></header><ul>${fileRows}</ul>${warnings}`;
      preview.hidden = false;
      fingerprint.value = body.fingerprint;
      submit.innerHTML = "IMPORT REVIEWED BOOK <span>&rarr;</span>";
      preview.scrollIntoView({ block: "nearest", behavior: "smooth" });
    } catch (error) {
      preview.innerHTML = `<p>${escapeText(error instanceof Error ? error.message : "Preview failed.")}</p>`;
      preview.hidden = false;
      submit.innerHTML = "REVIEW FILES <span>&rarr;</span>";
    } finally {
      submit.disabled = false;
    }
  });

  function escapeText(value) {
    const node = document.createElement("span");
    node.textContent = String(value);
    return node.innerHTML;
  }
})();
