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
