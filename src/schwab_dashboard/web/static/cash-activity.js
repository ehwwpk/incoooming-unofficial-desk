(() => {
  document.querySelectorAll("[data-cash-event-target]").forEach((link) => {
    link.addEventListener("click", () => {
      const target = document.getElementById(link.dataset.cashEventTarget);
      if (!(target instanceof HTMLDetailsElement)) return;
      target.open = true;
      target.dataset.positionAutoOpened = "true";
    });
  });
})();
