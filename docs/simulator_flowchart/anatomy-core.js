window.ANATOMY_CORE = (() => {
  "use strict";

  const esc = (value) => String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  function part(id, label, body, explodeX = 0, explodeY = 0, classes = "") {
    const explode = explodeX || explodeY
      ? ` data-explode style="--explode-x:${explodeX}px;--explode-y:${explodeY}px"`
      : "";
    return `<g class="machine-part ${classes}" data-part-id="${esc(id)}" tabindex="0" role="button" aria-label="${esc(label)}"${explode}>${body}</g>`;
  }

  function bolts(points, radius = 3) {
    return points.map(([x, y]) => `<circle class="fastener" cx="${x}" cy="${y}" r="${radius}"/>`).join("");
  }


  return { esc, part, bolts };
})();
