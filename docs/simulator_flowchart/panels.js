(() => {
  "use strict";

  const workspace = document.querySelector(".workspace");
  const graph = document.getElementById("graph-panel");
  const divider = document.getElementById("panel-divider");
  if (!workspace || !graph || !divider) return;

  const stacked = window.matchMedia("(max-width: 900px)");
  let drag = null;

  function dimension() {
    return stacked.matches ? "height" : "width";
  }

  function property() {
    return stacked.matches ? "--graph-height" : "--details-width";
  }

  function limits() {
    const axis = dimension();
    const available = Math.max(0, workspace.getBoundingClientRect()[axis] - divider.getBoundingClientRect()[axis]);
    const min = Math.min(stacked.matches ? 240 : 280, available / 2);
    const max = Math.max(min, available - (stacked.matches ? 200 : 240));
    return {available, min, max};
  }

  function updateAccessibleSize() {
    const {min, max} = limits();
    const size = graph.getBoundingClientRect()[dimension()];
    divider.setAttribute("aria-orientation", stacked.matches ? "horizontal" : "vertical");
    divider.setAttribute("aria-valuemin", String(Math.round(min)));
    divider.setAttribute("aria-valuemax", String(Math.round(max)));
    divider.setAttribute("aria-valuenow", String(Math.round(size)));
    divider.setAttribute("aria-valuetext", `Graph ${Math.round(size)} pixels ${stacked.matches ? "high" : "wide"}`);
  }

  function setGraphSize(size) {
    const {available, min, max} = limits();
    const bounded = Math.max(min, Math.min(max, size));
    workspace.style.setProperty(property(), `${stacked.matches ? bounded : available - bounded}px`);
    updateAccessibleSize();
  }

  function finishDrag(event) {
    if (!drag || (event?.pointerId !== undefined && event.pointerId !== drag.pointerId)) return;
    const pointerId = drag.pointerId;
    drag = null;
    document.documentElement.removeAttribute("data-panel-resizing");
    if (divider.hasPointerCapture(pointerId)) divider.releasePointerCapture(pointerId);
  }

  function resetSize() {
    finishDrag();
    workspace.style.removeProperty(property());
    updateAccessibleSize();
  }

  divider.addEventListener("pointerdown", event => {
    if (event.button !== 0 || !event.isPrimary || drag) return;
    event.preventDefault();
    divider.focus({preventScroll: true});
    drag = {
      pointerId: event.pointerId,
      start: stacked.matches ? event.clientY : event.clientX,
      size: graph.getBoundingClientRect()[dimension()],
      property: property(),
      previousValue: workspace.style.getPropertyValue(property()),
    };
    divider.setPointerCapture(event.pointerId);
    document.documentElement.setAttribute("data-panel-resizing", stacked.matches ? "row" : "column");
  });

  divider.addEventListener("pointermove", event => {
    if (!drag || event.pointerId !== drag.pointerId) return;
    const position = stacked.matches ? event.clientY : event.clientX;
    setGraphSize(drag.size + position - drag.start);
  });

  divider.addEventListener("pointerup", finishDrag);
  divider.addEventListener("pointercancel", finishDrag);
  divider.addEventListener("lostpointercapture", finishDrag);
  window.addEventListener("blur", () => finishDrag());
  divider.addEventListener("dblclick", resetSize);

  divider.addEventListener("keydown", event => {
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    const previous = stacked.matches ? "ArrowUp" : "ArrowLeft";
    const next = stacked.matches ? "ArrowDown" : "ArrowRight";
    const step = event.shiftKey ? 80 : 24;
    const size = graph.getBoundingClientRect()[dimension()];
    if (event.key === previous) setGraphSize(size - step);
    else if (event.key === next) setGraphSize(size + step);
    else if (event.key === "Home") setGraphSize(limits().min);
    else if (event.key === "End") setGraphSize(limits().max);
    else if (event.key === "Enter") resetSize();
    else if (event.key === "Escape" && drag) {
      if (drag.previousValue) workspace.style.setProperty(drag.property, drag.previousValue);
      else workspace.style.removeProperty(drag.property);
      finishDrag();
      updateAccessibleSize();
    } else return;
    event.preventDefault();
  });

  stacked.addEventListener("change", () => {
    finishDrag();
    updateAccessibleSize();
  });
  new ResizeObserver(updateAccessibleSize).observe(workspace);
  updateAccessibleSize();
})();
