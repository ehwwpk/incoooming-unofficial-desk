(() => {
  const books = [...document.querySelectorAll("[data-position-details]")];
  if (!books.length) return;
  const VIEW_STATE_KEY = "incoooming:auto-refresh-view";

  const refreshExpandedCharts = (book) => {
    window.requestAnimationFrame(() => {
      window.dispatchEvent(new Event("resize"));
      document.dispatchEvent(
        new CustomEvent("position-detail-toggle", { detail: { book, open: book.open } }),
      );
    });
  };

  books.forEach((book) => {
    book.addEventListener("toggle", () => {
      if (book.open) {
        books.forEach((otherBook) => {
          if (otherBook !== book) otherBook.open = false;
        });
      }
      refreshExpandedCharts(book);
    });
  });

  const targetFromHash = (hash = window.location.hash) => {
    if (!hash.startsWith("#") || hash.length < 2) return null;
    try {
      return document.getElementById(decodeURIComponent(hash.slice(1)));
    } catch {
      return null;
    }
  };

  const revealTarget = (target, behavior = "smooth") => {
    if (!(target instanceof HTMLElement)) return false;
    const book = target.matches("[data-position-details]")
      ? target
      : target.closest("[data-position-details]");
    if (!(book instanceof HTMLDetailsElement)) return false;

    book.open = true;
    if (target !== book) {
      target.dataset.optionArrival = "true";
      window.setTimeout(() => delete target.dataset.optionArrival, 2400);
    }
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        target.scrollIntoView({ behavior, block: target === book ? "start" : "center" });
        if (target !== book) target.focus({ preventScroll: true });
      });
    });
    return true;
  };

  const openHashTarget = (behavior = "smooth") => {
    revealTarget(targetFromHash(), behavior);
  };

  window.addEventListener("hashchange", () => openHashTarget());
  window.addEventListener("popstate", () => openHashTarget("auto"));
  document.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) return;
    const link = event.target.closest('a[href^="#"]');
    if (!(link instanceof HTMLAnchorElement)) return;
    const target = targetFromHash(link.hash);
    if (!target || !revealTarget(target)) return;
    event.preventDefault();
    if (window.location.hash === link.hash) {
      window.history.replaceState(null, "", link.hash);
    } else {
      window.history.pushState(null, "", link.hash);
    }
  });
  const restoreAutoRefreshView = () => {
    try {
      const serialized = sessionStorage.getItem(VIEW_STATE_KEY);
      if (!serialized) return false;
      sessionStorage.removeItem(VIEW_STATE_KEY);
      const state = JSON.parse(serialized);
      const currentPath = `${window.location.pathname}${window.location.search}`;
      if (state.path !== currentPath) return false;
      const openIds = Array.isArray(state.openDetails) ? state.openDetails : [];
      books.forEach((book) => {
        book.open = Boolean(book.id && openIds.includes(book.id));
      });
      if (Number.isFinite(Number(state.scrollY))) {
        window.requestAnimationFrame(() => window.scrollTo(0, Number(state.scrollY)));
      }
      return true;
    } catch (_) {
      return false;
    }
  };

  if (!restoreAutoRefreshView()) openHashTarget("auto");
})();
