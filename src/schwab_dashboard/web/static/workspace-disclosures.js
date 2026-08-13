(() => {
  const workspace = document.body.dataset.workspaceKey || "workspace";
  const disclosures = [...document.querySelectorAll("details[data-open-book-section]")];

  disclosures.forEach((details) => {
    const section = details.dataset.openBookSection;
    if (!section) return;

    const storageKey = `incoooming:${workspace}:section:${section}`;
    try {
      const saved = window.localStorage.getItem(storageKey);
      if (saved === "open") details.open = true;
      if (saved === "closed") details.open = false;
    } catch (_) {
      // Local storage is optional; the server-provided default remains usable.
    }

    details.addEventListener("toggle", () => {
      try {
        window.localStorage.setItem(storageKey, details.open ? "open" : "closed");
      } catch (_) {
        // Disclosure controls still work when storage is unavailable.
      }
    });
  });
})();
