(() => {
  const books = [...document.querySelectorAll("[data-position-details]")];
  if (!books.length) return;

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

  const openHashTarget = () => {
    if (!window.location.hash) return;
    const target = document.querySelector(window.location.hash);
    if (!(target instanceof HTMLDetailsElement) || !target.matches("[data-position-details]")) {
      return;
    }
    target.open = true;
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  window.addEventListener("hashchange", openHashTarget);
  openHashTarget();
})();
