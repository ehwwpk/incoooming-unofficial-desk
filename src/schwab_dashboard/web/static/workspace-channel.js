(() => {
  const STORAGE_KEY = "iud:workspace-context:v1";
  const CHANNEL_NAME = "iud-workspaces-v1";
  const root = document.body;
  const status = document.querySelector("[data-window-state]");
  const allowedKeys = new Set(["account", "symbol", "asOf"]);

  const safeContext = (candidate) => {
    if (!candidate || typeof candidate !== "object") return {};
    return Object.fromEntries(
      Object.entries(candidate)
        .filter(([key, value]) => allowedKeys.has(key) && typeof value === "string")
        .map(([key, value]) => [key, value.slice(0, 40)])
    );
  };

  const initialContext = (() => {
    try {
      const fromPage = safeContext(JSON.parse(root.dataset.workspaceContext || "{}"));
      const fromStorage = safeContext(JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}"));
      return { ...fromPage, ...fromStorage };
    } catch {
      return {};
    }
  })();

  let context = initialContext;
  const channel = "BroadcastChannel" in window ? new BroadcastChannel(CHANNEL_NAME) : null;

  const applyContext = (next) => {
    context = { ...context, ...safeContext(next) };
    document.querySelectorAll("[data-context-account]").forEach((node) => {
      node.textContent = context.account || "---";
    });
    document.querySelectorAll("[data-context-symbol]").forEach((node) => {
      node.textContent = context.symbol === "ALL" ? "ALL NAMES" : context.symbol || "ALL NAMES";
    });
    document.querySelectorAll("[data-context-symbol-row]").forEach((node) => {
      node.dataset.symbolActive = String(node.dataset.contextSymbolRow === context.symbol);
    });
  };

  const publish = (next) => {
    applyContext(next);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(context));
    channel?.postMessage({ type: "context:update", version: 1, context });
  };

  document.querySelectorAll("[data-set-symbol]").forEach((button) => {
    button.addEventListener("click", () => publish({ symbol: button.dataset.setSymbol || "ALL" }));
  });

  channel?.addEventListener("message", (event) => {
    if (event.data?.type === "context:update" && event.data.version === 1) {
      applyContext(event.data.context);
      if (status) status.textContent = "WINDOW CONTEXT UPDATED";
    }
  });

  window.addEventListener("storage", (event) => {
    if (event.key !== STORAGE_KEY || !event.newValue) return;
    try {
      applyContext(JSON.parse(event.newValue));
    } catch {
      // Ignore malformed browser storage; the server ledger remains authoritative.
    }
  });

  applyContext(context);
  if (status) status.textContent = channel ? "WINDOW LINK ACTIVE" : "STORAGE LINK ACTIVE";
})();
