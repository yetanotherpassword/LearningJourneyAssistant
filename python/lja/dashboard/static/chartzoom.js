/* "Enlarge" on every Chart.js chart: opens the same chart in a full-screen
 * modal, with hover tooltips and a live readout of the pointer's position
 * in data units.
 *
 * Progressive enhancement, like sort.js and scrollbox.js: the button is
 * added here, so a browser without JavaScript sees the chart and nothing
 * that does nothing. The modal chart is a second Chart instance built from
 * the original's config (same type, data, options, click handlers), so a
 * point in the big chart opens the same page as the small one.
 */
(() => {
  "use strict";

  if (typeof Chart === "undefined") return;

  const overlay = document.createElement("div");
  overlay.className = "chart-zoom";
  overlay.hidden = true;
  overlay.innerHTML = `
    <div class="chart-zoom-bar">
      <strong class="chart-zoom-title"></strong>
      <span class="chart-zoom-readout" aria-live="polite"></span>
      <button type="button" class="chart-zoom-close">Close</button>
    </div>
    <div class="chart-zoom-body"><canvas></canvas></div>
    <p class="chart-zoom-note">Hover a point for its values; the readout shows where the pointer is in data units. Esc closes.</p>`;
  document.body.appendChild(overlay);

  const title = overlay.querySelector(".chart-zoom-title");
  const readout = overlay.querySelector(".chart-zoom-readout");
  const bigCanvas = overlay.querySelector("canvas");
  let big = null;

  const fmt = (scale, value) => {
    if (value === undefined || value === null || Number.isNaN(value)) return "–";
    if (scale.type === "category") {
      const label = scale.getLabelForValue(Math.round(value));
      return label === undefined ? "–" : String(label);
    }
    return Number(value).toFixed(1);
  };

  const close = () => {
    if (big) { big.destroy(); big = null; }
    overlay.hidden = true;
    document.body.classList.remove("has-modal");
  };

  const open = (canvas, heading) => {
    const src = Chart.getChart(canvas);
    if (!src) return;
    title.textContent = heading;
    readout.textContent = "";
    overlay.hidden = false;
    document.body.classList.add("has-modal");
    const options = { ...src.config.options, responsive: true, maintainAspectRatio: false, animation: false };
    big = new Chart(bigCanvas, { type: src.config.type, data: src.config.data, options, plugins: src.config.plugins || [] });
  };

  bigCanvas.addEventListener("mousemove", (event) => {
    if (!big) return;
    const rect = bigCanvas.getBoundingClientRect();
    const px = event.clientX - rect.left;
    const py = event.clientY - rect.top;
    const parts = [];
    const x = big.scales.x;
    const y = big.scales.y;
    if (x) parts.push(`${x.options.title?.text || "x"}: ${fmt(x, x.getValueForPixel(px))}`);
    if (y) parts.push(`${y.options.title?.text || "y"}: ${fmt(y, y.getValueForPixel(py))}`);
    for (const id of Object.keys(big.scales)) {
      if (id !== "x" && id !== "y") {
        const s = big.scales[id];
        const axis = s.axis === "y" ? py : px;
        parts.push(`${s.options.title?.text || id}: ${fmt(s, s.getValueForPixel(axis))}`);
      }
    }
    readout.textContent = parts.join("  ·  ");
  });
  bigCanvas.addEventListener("mouseleave", () => { readout.textContent = ""; });
  overlay.querySelector(".chart-zoom-close").addEventListener("click", close);
  document.addEventListener("keydown", (event) => { if (event.key === "Escape" && !overlay.hidden) close(); });

  // One button per chart card. Charts are created by inline scripts after
  // this deferred file runs on some pages, so the button resolves the Chart
  // instance at click time, not at setup time.
  document.querySelectorAll(".chart-card canvas").forEach((canvas) => {
    const card = canvas.closest(".chart-card");
    const heading = card.querySelector("h3")?.textContent.trim() || canvas.getAttribute("aria-label") || "Chart";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chart-enlarge";
    button.textContent = "Enlarge";
    button.title = "Open this chart full screen with a live value readout";
    button.addEventListener("click", () => open(canvas, heading));
    card.classList.add("has-enlarge");
    card.insertBefore(button, card.firstChild);
  });
})();
