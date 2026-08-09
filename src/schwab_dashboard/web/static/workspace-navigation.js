(() => {
  const buttons = [...document.querySelectorAll("[data-open-workspace]")];

  buttons.forEach((button) => {
    const name = button.dataset.windowName;
    const url = button.dataset.workspaceUrl;
    if (!name || !url) return;

    if (window.name === name) {
      button.textContent = "THIS WINDOW";
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
