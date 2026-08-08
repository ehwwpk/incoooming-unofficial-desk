(() => {
  const wire = document.querySelector("[data-nibwick-wire]");
  const notes = [...document.querySelectorAll("[data-nibwick-note]")];
  const badge = document.querySelector("[data-nibwick-alert-badge]");
  if (!wire || !notes.length) return;

  const position = wire.querySelector("[data-nibwick-note-position]");
  let activeIndex = 0;
  const showNote = (index) => {
    activeIndex = (index + notes.length) % notes.length;
    notes.forEach((note, noteIndex) => {
      note.hidden = noteIndex !== activeIndex;
    });
    if (position) position.textContent = `${activeIndex + 1} / ${notes.length}`;
  };

  wire.querySelector("[data-nibwick-note-prev]")?.addEventListener("click", () => {
    showNote(activeIndex - 1);
  });
  wire.querySelector("[data-nibwick-note-next]")?.addEventListener("click", () => {
    showNote(activeIndex + 1);
  });
  badge?.addEventListener("click", () => {
    wire.scrollIntoView({ behavior: "smooth", block: "center" });
  });
})();
