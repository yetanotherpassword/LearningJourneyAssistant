/* Toolbar for every scroll-boxed table: a live filter and a full-screen view.
 *
 * Progressive enhancement, like sort.js. The toolbar is rendered by the
 * scrollbox macro with `hidden` set, and this file reveals it, so a browser
 * without JavaScript never shows controls that do nothing. Nothing here
 * fetches or recomputes a figure: filtering hides rows the server rendered,
 * and full screen moves the same box into a fixed overlay.
 *
 * Filter: a row stays visible when any of its cells contains the typed text
 * (case-insensitive, on the visible text). The count line says how many of
 * the total are showing. Sorting (sort.js) and filtering compose: sorting
 * permutes rows, filtering toggles their `hidden` attribute.
 *
 * Full screen: the panel gets `is-full`, which CSS turns into a fixed
 * overlay with the toolbar pinned at the top and the box filling the rest.
 * Esc or the same button closes it.
 */
(() => {
  "use strict";

  const setup = (panel) => {
    const tools = panel.querySelector(".scroll-tools");
    const box = panel.querySelector(".scroll-box");
    const table = box && box.querySelector("table");
    if (!tools || !table || !table.tBodies[0]) return;

    const input = tools.querySelector(".scroll-search");
    const count = tools.querySelector(".scroll-count");
    const button = tools.querySelector(".scroll-expand");
    const what = panel.dataset.what || "rows";
    const rows = () => Array.from(table.tBodies[0].rows);
    const total = rows().length;

    tools.hidden = false;

    const applyFilter = () => {
      const q = input.value.trim().toLowerCase();
      let shown = 0;
      rows().forEach((row) => {
        const hit = !q || row.textContent.toLowerCase().includes(q);
        row.hidden = !hit;
        if (hit) shown += 1;
      });
      count.textContent = q ? `${shown} of ${total} ${what} match` : `${total} ${what}`;
      panel.classList.toggle("is-filtered", Boolean(q));
    };

    input.addEventListener("input", applyFilter);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && input.value) {
        input.value = "";
        applyFilter();
        event.stopPropagation();
      }
    });
    applyFilter();

    const setFull = (on) => {
      panel.classList.toggle("is-full", on);
      document.body.classList.toggle("has-modal", on);
      button.textContent = on ? "Close" : "Expand";
      button.setAttribute("aria-expanded", String(on));
      if (on) box.focus();
    };
    button.addEventListener("click", () => setFull(!panel.classList.contains("is-full")));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && panel.classList.contains("is-full")) setFull(false);
    });
  };

  document.querySelectorAll(".scroll-panel").forEach(setup);
})();
