(() => {
  "use strict";

  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const appearanceOrder = ["auto", "light", "dark"];
  const memory = {
    userInteracted: false,
    motionPaused: false,
    theme: "auto",
  };

  const lapCatalog = window.LAP_ANATOMY_CATALOG;


  const carCatalog = window.CAR_ANATOMY_CATALOG;


  const { esc } = window.ANATOMY_CORE;
  const lapSvg = window.ANATOMY_LAP_SVG;
  const carSvg = window.ANATOMY_CAR_SVG;

  function renderDetail(card, catalog, id, options = {}) {
    const entry = catalog[id];
    if (!entry) return;

    card.dataset.selectedPart = id;
    card.querySelectorAll(".machine-part").forEach((node) => {
      const selected = node.dataset.partId === id;
      node.classList.toggle("is-selected", selected);
      node.setAttribute("aria-pressed", String(selected));
    });

    const inspector = card.querySelector(".anatomy-inspector");
    inspector.querySelector("[data-detail-status]").textContent = entry.status;
    inspector.querySelector("[data-detail-title]").textContent = entry.title;
    inspector.querySelector("[data-detail-summary]").textContent = entry.summary;
    inspector.querySelector("[data-detail-facts]").innerHTML = entry.facts
      .map(([term, value]) => `<div><dt>${esc(term)}</dt><dd>${esc(value)}</dd></div>`)
      .join("");
    inspector.querySelector("[data-detail-links]").innerHTML = entry.links
      .map(([label, href]) => `<a href="${esc(href)}">${esc(label)}</a>`)
      .join("");

    updateReadout(card, options.figure);
  }

  function updateReadout(card, figure) {
    const selected = figure === "lapsim" ? lapCatalog[card.dataset.selectedPart] : carCatalog[card.dataset.selectedPart];
    if (figure === "lapsim") {
      const running = card.dataset.running === "true" && !memory.motionPaused && card.dataset.inView !== "false";
      const state = running ? "Running" : "Paused";
      const label = selected?.title || "Vehicle cell integrator";
      document.getElementById("lapsim-readout").textContent = `${label} · ${state}`;
    } else {
      const modeLabels = { power: "Power flow", signal: "Signal flow", structure: "Structure" };
      const mode = card.dataset.carMode || "power";
      const label = selected?.title || "Rear-wheel-drive energy path";
      document.getElementById("car-readout").textContent = `2026–27 RWD · ${modeLabels[mode]} · ${label}`;
    }
  }

  function bindFigure(card, catalog, figure, defaultId) {
    const stage = card.querySelector(`.anatomy-stage[data-figure="${figure}"]`);
    stage.innerHTML = figure === "lapsim" ? lapSvg() : carSvg();
    stage.querySelectorAll("[data-part-id]").forEach((part) => {
      const visibleLabel = [...part.querySelectorAll("text")]
        .map((text) => text.textContent.trim()).filter(Boolean).join(" ");
      if (visibleLabel) {
        part.setAttribute("aria-description", part.getAttribute("aria-label"));
        part.setAttribute("aria-label", visibleLabel);
      }
    });
    const svg = stage.querySelector("svg");
    if (figure === "car") svg.dataset.mode = card.dataset.carMode || "power";

    const choose = (target, userInitiated = true) => {
      const partNode = target.closest?.("[data-part-id]");
      if (!partNode) return;
      if (userInitiated) memory.userInteracted = true;
      renderDetail(card, catalog, partNode.dataset.partId, { figure });
    };

    stage.addEventListener("click", (event) => choose(event.target));
    stage.addEventListener("keydown", (event) => {
      const partNode = event.target.closest?.("[data-part-id]");
      if (!partNode) return;

      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        choose(partNode);
        return;
      }

      if (["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(event.key)) {
        event.preventDefault();
        memory.userInteracted = true;
        const parts = [...stage.querySelectorAll("[data-part-id]")];
        const index = parts.indexOf(partNode);
        const direction = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : -1;
        parts[(index + direction + parts.length) % parts.length].focus();
      }
    });

    renderDetail(card, catalog, defaultId, { figure });
  }

  function bindCardControls(card, figure, defaultId) {
    card.querySelectorAll("[data-anatomy-action]").forEach((button) => {
      button.addEventListener("click", () => {
        memory.userInteracted = true;
        const action = button.dataset.anatomyAction;

        if (action === "run") {
          const next = card.dataset.running !== "true";
          card.dataset.running = String(next);
          button.setAttribute("aria-pressed", String(next));
          button.textContent = next ? "Pause" : "Run";
        }

        if (action === "explode") {
          const next = !card.classList.contains("is-exploded");
          card.classList.toggle("is-exploded", next);
          button.setAttribute("aria-pressed", String(next));
          button.textContent = next ? "Assemble" : "Explode";
        }

        if (action === "reset") {
          card.classList.remove("is-exploded");
          card.dataset.running = String(!prefersReducedMotion.matches);
          card.querySelectorAll("[data-anatomy-action='explode']").forEach((control) => {
            control.setAttribute("aria-pressed", "false");
            control.textContent = "Explode";
          });
          card.querySelectorAll("[data-anatomy-action='run']").forEach((control) => {
            control.setAttribute("aria-pressed", String(!prefersReducedMotion.matches));
            control.textContent = prefersReducedMotion.matches ? "Run" : "Pause";
          });
          if (figure === "car") setCarMode(card, "power");
          renderDetail(card, figure === "lapsim" ? lapCatalog : carCatalog, defaultId, { figure });
        }

        updateReadout(card, figure);
      });
    });
  }

  function setCarMode(card, mode) {
    card.dataset.carMode = mode;
    const svg = card.querySelector(".car-figure");
    if (svg) svg.dataset.mode = mode;
    card.querySelectorAll("[data-car-mode]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.carMode === mode));
    });
    updateReadout(card, "car");
  }

  function bindCarModes(card) {
    card.querySelectorAll("button[data-car-mode]").forEach((button) => {
      button.addEventListener("click", () => {
        memory.userInteracted = true;
        setCarMode(card, button.dataset.carMode);
      });
    });
  }

  function applyTheme(mode) {
    memory.theme = mode;
    if (mode === "auto") {
      document.documentElement.removeAttribute("data-theme");
    } else {
      document.documentElement.dataset.theme = mode;
    }

    const button = document.getElementById("appearance-toggle");
    if (button) {
      button.dataset.mode = mode;
      button.textContent = `Appearance · ${mode[0].toUpperCase()}${mode.slice(1)}`;
    }

    try { localStorage.setItem("lapsim-anatomy-theme", mode); } catch (_) { /* storage is optional */ }
  }

  function bindGlobalControls(cards) {
    const appearanceButton = document.getElementById("appearance-toggle");
    appearanceButton.addEventListener("click", () => {
      memory.userInteracted = true;
      const current = appearanceOrder.indexOf(memory.theme);
      applyTheme(appearanceOrder[(current + 1) % appearanceOrder.length]);
    });

    const motionButton = document.getElementById("motion-toggle");
    const reflectMotion = () => {
      const systemReduced = prefersReducedMotion.matches;
      if (systemReduced) {
        memory.motionPaused = true;
        document.documentElement.dataset.motion = "paused";
        motionButton.setAttribute("aria-pressed", "true");
        motionButton.textContent = "Motion reduced by system";
        motionButton.disabled = true;
      } else {
        motionButton.disabled = false;
        document.documentElement.dataset.motion = memory.motionPaused ? "paused" : "running";
        motionButton.setAttribute("aria-pressed", String(memory.motionPaused));
        motionButton.textContent = memory.motionPaused ? "Resume motion" : "Pause motion";
      }
      cards.forEach(({ card, figure }) => {
        if (systemReduced) card.dataset.running = "false";
        card.querySelectorAll("[data-anatomy-action='run']").forEach((button) => {
          button.disabled = systemReduced;
          const running = card.dataset.running === "true";
          button.setAttribute("aria-pressed", String(running));
          button.textContent = running ? "Pause" : "Run";
        });
        updateReadout(card, figure);
      });
    };

    motionButton.addEventListener("click", () => {
      memory.userInteracted = true;
      memory.motionPaused = !memory.motionPaused;
      reflectMotion();
    });

    prefersReducedMotion.addEventListener?.("change", reflectMotion);
    reflectMotion();
  }

  function observeCards(cards) {
    if (!("IntersectionObserver" in window)) return;
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        const card = entry.target;
        card.dataset.inView = String(entry.isIntersecting && entry.intersectionRatio > 0.12);
        const figure = card.id === "lapsim-anatomy" ? "lapsim" : "car";
        updateReadout(card, figure);
      });
    }, { threshold: [0, 0.12, 0.45] });

    cards.forEach(({ card }) => observer.observe(card));
  }

  function startIdleTour(cards) {
    if (prefersReducedMotion.matches) return;
    const order = {
      lapsim: ["lap-cell", "lap-course", "lap-envelope", "lap-battery", "lap-powertrain", "lap-tires", "lap-telemetry", "lap-scoring"],
      car: ["car-rwd", "car-accumulator", "car-vcu", "car-inverter", "car-motor", "car-rear-drive", "car-sensors"],
    };
    const indices = { lapsim: 0, car: 0 };

    window.setInterval(() => {
      if (memory.userInteracted || memory.motionPaused || document.hidden) return;
      cards.forEach(({ card, figure, catalog }) => {
        if (card.dataset.inView === "false" || card.dataset.running !== "true") return;
        indices[figure] = (indices[figure] + 1) % order[figure].length;
        renderDetail(card, catalog, order[figure][indices[figure]], { figure });
      });
    }, 8000);
  }

  function init() {
    const lapCard = document.getElementById("lapsim-anatomy");
    const carCard = document.getElementById("car-anatomy");
    if (!lapCard || !carCard) return;

    try {
      const savedTheme = localStorage.getItem("lapsim-anatomy-theme");
      if (appearanceOrder.includes(savedTheme)) memory.theme = savedTheme;
    } catch (_) { /* storage is optional */ }
    applyTheme(memory.theme);

    if (prefersReducedMotion.matches) {
      lapCard.dataset.running = "false";
      carCard.dataset.running = "false";
    }

    bindFigure(lapCard, lapCatalog, "lapsim", "lap-cell");
    bindFigure(carCard, carCatalog, "car", "car-rwd");
    bindCardControls(lapCard, "lapsim", "lap-cell");
    bindCardControls(carCard, "car", "car-rwd");
    bindCarModes(carCard);

    const cards = [
      { card: lapCard, figure: "lapsim", catalog: lapCatalog },
      { card: carCard, figure: "car", catalog: carCatalog },
    ];
    bindGlobalControls(cards);
    observeCards(cards);
    startIdleTour(cards);

    document.addEventListener("visibilitychange", () => {
      cards.forEach(({ card, figure }) => updateReadout(card, figure));
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
