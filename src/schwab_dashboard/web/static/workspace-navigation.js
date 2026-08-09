(() => {
  const disclosures = [...document.querySelectorAll("[data-tools-disclosure]")];

  const closeDisclosure = (disclosure, restoreFocus = false) => {
    const toggle = disclosure.querySelector("[data-tools-toggle]");
    const panel = disclosure.querySelector("[data-tools-panel]");
    if (!toggle || !panel) return;
    toggle.setAttribute("aria-expanded", "false");
    panel.hidden = true;
    if (restoreFocus) toggle.focus();
  };

  const openDisclosure = (disclosure, focusFirstLink = false) => {
    disclosures.forEach((item) => {
      if (item !== disclosure) closeDisclosure(item);
    });
    const toggle = disclosure.querySelector("[data-tools-toggle]");
    const panel = disclosure.querySelector("[data-tools-panel]");
    if (!toggle || !panel) return;
    toggle.setAttribute("aria-expanded", "true");
    panel.hidden = false;
    if (focusFirstLink) panel.querySelector("a")?.focus();
  };

  disclosures.forEach((disclosure) => {
    const toggle = disclosure.querySelector("[data-tools-toggle]");
    if (!toggle) return;

    toggle.addEventListener("click", () => {
      if (toggle.getAttribute("aria-expanded") === "true") {
        closeDisclosure(disclosure);
      } else {
        openDisclosure(disclosure);
      }
    });

    toggle.addEventListener("keydown", (event) => {
      if (event.key !== "ArrowDown") return;
      event.preventDefault();
      openDisclosure(disclosure, true);
    });

    disclosure.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      closeDisclosure(disclosure, true);
    });

    disclosure.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => closeDisclosure(disclosure));
    });
  });

  document.addEventListener("pointerdown", (event) => {
    disclosures.forEach((disclosure) => {
      if (!disclosure.contains(event.target)) closeDisclosure(disclosure);
    });
  });

  document.addEventListener("focusin", (event) => {
    disclosures.forEach((disclosure) => {
      if (!disclosure.contains(event.target)) closeDisclosure(disclosure);
    });
  });

  document.querySelectorAll("[data-open-workspace]").forEach((button) => {
    const name = button.dataset.windowName;
    const url = button.dataset.workspaceUrl;
    if (!name || !url) return;

    if (window.name === name) {
      if (button.hasAttribute("data-window-button-compact")) {
        button.textContent = "✓";
        button.setAttribute("aria-label", "This tool is open in the current window");
      } else {
        button.textContent = "THIS WINDOW";
      }
      button.disabled = true;
      return;
    }

    button.addEventListener("click", () => {
      const child = window.open(url, name);
      if (!child) {
        window.location.assign(url);
        return;
      }
      child.focus();
    });
  });
})();
