(() => {
  "use strict";

  class CampaignFocusController {
    constructor(shell, button, onChange) {
      this.shell = shell;
      this.button = button;
      this.onChange = onChange;
      this.active = false;
      this.returnFocus = null;
      this.anchor = null;
      button?.addEventListener("click", () => this.toggle());
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && this.active) this.close();
      });
    }

    toggle() {
      if (this.active) this.close();
      else this.open();
    }

    open() {
      this.returnFocus = document.activeElement;
      this.active = true;
      this.anchor = document.createComment("campaign-chart-focus-return");
      this.shell.before(this.anchor);
      document.body.append(this.shell);
      this.shell.classList.add("is-focus");
      document.body.classList.add("campaign-focus-open");
      this.button?.setAttribute("aria-pressed", "true");
      if (this.button) this.button.textContent = "EXIT FOCUS";
      requestAnimationFrame(() => this.onChange?.(true));
    }

    close() {
      this.active = false;
      this.shell.classList.remove("is-focus");
      document.body.classList.remove("campaign-focus-open");
      this.button?.setAttribute("aria-pressed", "false");
      if (this.button) this.button.textContent = "FOCUS";
      if (this.anchor?.parentNode) {
        this.anchor.parentNode.insertBefore(this.shell, this.anchor);
        this.anchor.remove();
      }
      this.anchor = null;
      requestAnimationFrame(() => {
        this.onChange?.(false);
        this.returnFocus?.focus?.();
      });
    }
  }

  window.IncooomingCampaignFocusController = CampaignFocusController;
})();
