/* Click-to-sort for any <table class="sortable">.
 *
 * Progressive enhancement, deliberately. The server already emits rows in a
 * sensible default order (student id, ascending), so a browser with no
 * JavaScript still gets a correct and readable table -- this file only adds
 * reordering on top of one that was already right. Nothing here fetches, and
 * nothing here recomputes a figure: it permutes rows the server rendered.
 *
 * Sorting reads each cell's data-sort-value rather than its visible text,
 * because the visible text is formatted for humans -- "70.0%", a badge
 * element, or an em dash for "none". Sorting on that would order 100 before
 * 20 and put "—" somewhere arbitrary. app.py emits the raw value alongside.
 */
(() => {
  "use strict";

  const cellValue = (row, index) => {
    const cell = row.cells[index];
    if (!cell) return "";
    const raw = cell.dataset.sortValue;
    return raw !== undefined ? raw : cell.textContent.trim();
  };

  const comparator = (index, type, direction) => {
    const sign = direction === "descending" ? -1 : 1;
    return (a, b) => {
      const left = cellValue(a, index);
      const right = cellValue(b, index);
      if (type === "number") {
        // Non-numeric or missing values sort as -Infinity so they group at
        // one end rather than scattering unpredictably through the table.
        const ln = parseFloat(left);
        const rn = parseFloat(right);
        const lv = Number.isNaN(ln) ? -Infinity : ln;
        const rv = Number.isNaN(rn) ? -Infinity : rn;
        return (lv - rv) * sign;
      }
      return left.localeCompare(right, undefined, { numeric: true }) * sign;
    };
  };

  const setup = (table) => {
    const headers = Array.from(table.tHead ? table.tHead.rows[0].cells : []);
    const body = table.tBodies[0];
    if (!body) return;

    headers.forEach((header, index) => {
      const type = header.dataset.sortType;
      if (!type) return;

      // Keyboard reachable and announced as a control, not just clickable.
      header.tabIndex = 0;
      header.setAttribute("role", "button");
      header.classList.add("sortable-header");

      const activate = () => {
        // Same column toggles direction; a new column always starts ascending,
        // which is what people expect from a first click.
        const current = header.getAttribute("aria-sort");
        const direction = current === "ascending" ? "descending" : "ascending";

        headers.forEach((other) => other.removeAttribute("aria-sort"));
        header.setAttribute("aria-sort", direction);

        // Array.prototype.sort is stable, so rows equal on this column keep
        // their previous relative order rather than shuffling.
        const rows = Array.from(body.rows);
        rows.sort(comparator(index, type, direction));
        rows.forEach((row) => body.appendChild(row));
      };

      header.addEventListener("click", activate);
      header.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          activate();
        }
      });
    });
  };

  document.querySelectorAll("table.sortable").forEach(setup);
})();
