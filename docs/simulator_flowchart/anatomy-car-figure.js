window.ANATOMY_CAR_SVG = (() => {
  "use strict";
  const { part, bolts } = window.ANATOMY_CORE;

  function wheelGroup(cx, cy, scale = 1, rotate = -18) {
    const tread = Array.from({ length: 7 }, (_, index) => {
      const y = cy - 25 * scale + index * 8 * scale;
      return `<path d="M ${cx - 28 * scale} ${y} L ${cx + 28 * scale} ${y - 7 * scale}" stroke="#4f555c" stroke-width="${2.1 * scale}" opacity="0.85"/>`;
    }).join("");
    return `<g transform="rotate(${rotate} ${cx} ${cy})">
      <ellipse class="rubber" cx="${cx}" cy="${cy}" rx="${43 * scale}" ry="${63 * scale}"/>
      ${tread}
      <ellipse class="rim" cx="${cx}" cy="${cy}" rx="${23 * scale}" ry="${36 * scale}"/>
      <ellipse class="iso-dark" cx="${cx}" cy="${cy}" rx="${8 * scale}" ry="${13 * scale}"/>
      <path class="detail-stroke-fine" d="M${cx - 18 * scale} ${cy - 25 * scale}L${cx + 18 * scale} ${cy + 25 * scale}M${cx + 18 * scale} ${cy - 25 * scale}L${cx - 18 * scale} ${cy + 25 * scale}M${cx} ${cy - 34 * scale}V${cy + 34 * scale}"/>
    </g>`;
  }

  function carSvg() {
    const tubeBolts = bolts([[410,488],[493,458],[575,432],[660,405],[747,381],[832,356],[914,333]], 2.2);
    const sensorDots = [[349,467],[507,535],[782,493],[948,405],[650,397],[742,351]].map(([x, y]) =>
      `<circle class="flow-node signal-flow" cx="${x}" cy="${y}" r="5"/>`).join("");

    return `
      <svg class="anatomy-svg car-figure" data-mode="power" viewBox="0 0 1200 720" role="group" aria-labelledby="car-figure-title" aria-describedby="car-figure-desc">
        <title id="car-figure-title">Interactive isometric system anatomy of the 2026–27 rear-wheel-drive Formula SAE electric car</title>
        <desc id="car-figure-desc">A source-aware schematic vehicle showing chassis, driver, accumulator, inverter, traction motor, rear drive, four wheels, brakes, suspension, controller, sensors, cooling, and aerodynamic devices. Exact packaging is intentionally not asserted.</desc>
        <defs>
          <linearGradient id="car-carbon" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stop-color="#38434f"/>
            <stop offset="0.5" stop-color="#202932"/>
            <stop offset="1" stop-color="#11171d"/>
          </linearGradient>
          <linearGradient id="car-seat" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="#303b46"/>
            <stop offset="1" stop-color="#11161c"/>
          </linearGradient>
          <filter id="car-soft-shadow" x="-30%" y="-30%" width="160%" height="180%">
            <feDropShadow dx="0" dy="10" stdDeviation="12" flood-color="#000" flood-opacity="0.22"/>
          </filter>
          <marker id="car-arrow-orange" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M0 0L10 5L0 10Z" fill="var(--anatomy-orange)"/>
          </marker>
          <marker id="car-arrow-blue" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M0 0L10 5L0 10Z" fill="var(--anatomy-blue)"/>
          </marker>
        </defs>

        <ellipse class="figure-shadow" cx="620" cy="587" rx="485" ry="78"/>

        ${part("car-aero", "Aerodynamic devices", `
          <g>
            <path d="M196 397L348 357L397 381L245 423Z" fill="url(#car-carbon)" stroke="var(--iso-edge)" stroke-width="1.3"/>
            <path d="M215 423L365 383L372 401L222 441Z" fill="#161d24" stroke="var(--iso-edge)"/>
            <path class="detail-stroke" d="M257 409L266 450M344 386L349 425"/>
            <path d="M956 338L1099 299L1138 320L996 360Z" fill="url(#car-carbon)" stroke="var(--iso-edge)" stroke-width="1.3"/>
            <path d="M970 359L1110 321L1116 338L978 376Z" fill="#161d24" stroke="var(--iso-edge)"/>
            <path class="detail-stroke" d="M1001 350L1010 389M1084 328L1091 367"/>
          </g>
          <rect class="selection-ring" x="184" y="289" width="966" height="165" rx="26"/>
        `, 0, -72)},

        ${part("car-rear-wheels", "Rear driven wheels", `
          ${wheelGroup(317, 510, 1.05, -18)}
          ${wheelGroup(496, 409, 0.88, -18)}
          <path class="flow-line mechanical-flow" d="M405 451L338 494" marker-end="url(#car-arrow-orange)"/>
          <path class="flow-line mechanical-flow" d="M420 445L483 421" marker-end="url(#car-arrow-orange)"/>
          <rect class="selection-ring" x="260" y="342" width="298" height="245" rx="30"/>
        `, -74, 32)},

        ${part("car-front-wheels", "Front steered wheels", `
          ${wheelGroup(840, 588, 1.02, -18)}
          ${wheelGroup(1025, 486, 0.86, -18)}
          <rect class="selection-ring" x="778" y="418" width="306" height="238" rx="30"/>
        `, 82, 42)},

        ${part("car-brakes", "Four wheel friction brakes", `
          <g>
            <ellipse cx="317" cy="510" rx="20" ry="31" fill="none" stroke="var(--anatomy-red)" stroke-width="4" opacity="0.82" transform="rotate(-18 317 510)"/>
            <ellipse cx="496" cy="409" rx="17" ry="26" fill="none" stroke="var(--anatomy-red)" stroke-width="4" opacity="0.82" transform="rotate(-18 496 409)"/>
            <ellipse cx="840" cy="588" rx="20" ry="30" fill="none" stroke="var(--anatomy-red)" stroke-width="4" opacity="0.82" transform="rotate(-18 840 588)"/>
            <ellipse cx="1025" cy="486" rx="17" ry="25" fill="none" stroke="var(--anatomy-red)" stroke-width="4" opacity="0.82" transform="rotate(-18 1025 486)"/>
          </g>
          <path class="signal-flow flow-line" d="M728 406C660 457 581 485 504 505C434 523 375 532 329 525" marker-end="url(#car-arrow-blue)"/>
          <path class="signal-flow flow-line" d="M730 411C802 446 887 471 1008 484" marker-end="url(#car-arrow-blue)"/>
        `, 0, 68)},

        ${part("car-suspension", "Suspension and steering", `
          <g class="structure-overlay">
            <path class="detail-stroke" d="M353 476L444 451L317 510M353 476L431 500L317 510M472 422L556 405L496 409M472 422L548 456L496 409" stroke-width="4"/>
            <path class="detail-stroke" d="M763 533L840 588L821 505M763 533L814 565L840 588M921 449L1025 486L948 420M921 449L995 462L1025 486" stroke-width="4"/>
            <path class="detail-stroke-fine" d="M812 504L932 437M821 514L941 447"/>
            <path class="detail-stroke" d="M799 492L944 414" stroke-width="3"/>
          </g>
          <rect class="selection-ring" x="300" y="385" width="760" height="246" rx="32"/>
        `, 0, 34)},

        ${part("car-chassis", "Chassis and protected volumes", `
          <g class="structure-overlay">
            <path class="detail-stroke" d="M378 486L507 532L820 448L951 394M378 486L482 420L752 347L951 394M507 532L482 420M820 448L752 347M482 420L556 362L724 317L752 347M556 362L507 532M724 317L820 448" stroke-width="7"/>
            <path class="detail-stroke" d="M556 362L635 464L724 317M482 420L635 464L752 347M507 532L635 464L820 448" stroke-width="5"/>
            <path class="detail-stroke-fine" d="M394 478L508 515L800 438L931 401M408 467L487 429L752 358L936 404"/>
            ${tubeBolts}
          </g>
          <path d="M475 430L554 366L731 319L819 450L634 500L506 523Z" fill="url(#car-carbon)" opacity="0.22"/>
          <rect class="selection-ring" x="356" y="300" width="616" height="250" rx="34"/>
        `, 0, 0)},

        ${part("car-accumulator", "High voltage accumulator", `
          <polygon points="455,439 567,409 637,446 521,479" fill="color-mix(in srgb, var(--anatomy-orange) 75%, var(--iso-top))"/>
          <polygon points="455,439 521,479 521,528 455,486" fill="color-mix(in srgb, var(--anatomy-orange) 48%, var(--iso-left))"/>
          <polygon points="521,479 637,446 637,495 521,528" fill="color-mix(in srgb, var(--anatomy-orange) 56%, var(--iso-right))"/>
          <path class="iso-edge" d="M455 439L567 409L637 446L637 495L521 528L455 486Z M455 439L521 479L637 446 M521 479V528"/>
          <path class="detail-stroke-fine" d="M476 445L534 478M508 436L566 469M540 428L598 460M488 496L608 462"/>
          ${bolts([[469,450],[556,426],[622,453],[469,478],[533,514],[622,484]], 2.4)}
          <text class="diagram-micro" x="481" y="500">HV ACCUMULATOR</text>
          <path class="flow-line power-flow" d="M626 467C661 450 681 438 707 423" marker-end="url(#car-arrow-orange)"/>
          <rect class="selection-ring" x="444" y="398" width="204" height="143" rx="20"/>
        `, -10, 78)},

        ${part("car-driver", "Driver and primary controls", `
          <path d="M612 380C626 345 667 334 691 362L716 414L647 434L601 408Z" fill="url(#car-seat)" stroke="var(--iso-edge)" stroke-width="1.3"/>
          <ellipse cx="654" cy="335" rx="22" ry="27" fill="#c8a987" stroke="var(--iso-edge)"/>
          <path d="M631 344C635 311 673 305 681 338C668 330 648 330 631 344Z" fill="#2d333a"/>
          <path class="detail-stroke" d="M632 380L616 446M680 375L705 430M636 427L600 462M684 419L735 445" stroke-width="6"/>
          <ellipse cx="733" cy="408" rx="31" ry="18" fill="none" stroke="var(--iso-edge)" stroke-width="5" transform="rotate(-14 733 408)"/>
          <path class="detail-stroke" d="M733 408L710 426M733 408L756 389M733 408L757 425"/>
          <path class="signal-flow flow-line" d="M735 410C756 405 770 403 788 402" marker-end="url(#car-arrow-blue)"/>
          <rect class="selection-ring" x="586" y="300" width="197" height="176" rx="24"/>
        `, 4, -82)},

        ${part("car-vcu", "STM32F405 vehicle controller", `
          <polygon points="742,379 815,360 858,383 783,404" fill="color-mix(in srgb, var(--anatomy-blue) 72%, var(--iso-top))"/>
          <polygon points="742,379 783,404 783,447 742,421" fill="color-mix(in srgb, var(--anatomy-blue) 42%, var(--iso-left))"/>
          <polygon points="783,404 858,383 858,426 783,447" fill="color-mix(in srgb, var(--anatomy-blue) 50%, var(--iso-right))"/>
          <path class="iso-edge" d="M742 379L815 360L858 383L858 426L783 447L742 421Z M742 379L783 404L858 383 M783 404V447"/>
          <rect x="773" y="387" width="37" height="26" rx="4" fill="#152238" stroke="var(--iso-metal-light)"/>
          <path class="detail-stroke-fine" d="M779 393H803M779 400H803M779 407H803"/>
          <circle cx="828" cy="397" r="4" fill="var(--anatomy-green)"/>
          <circle cx="840" cy="393" r="4" fill="var(--anatomy-orange)"/>
          <text class="diagram-micro" x="758" y="433">STM32F405 VCU</text>
          <path class="signal-flow flow-line" d="M845 400C885 403 907 408 935 421" marker-end="url(#car-arrow-blue)"/>
          <rect class="selection-ring" x="731" y="348" width="138" height="112" rx="18"/>
        `, 48, -48)},

        ${part("car-inverter", "Traction inverter", `
          <polygon points="397,397 472,377 516,401 439,422" fill="color-mix(in srgb, var(--anatomy-purple) 66%, var(--iso-top))"/>
          <polygon points="397,397 439,422 439,470 397,444" fill="color-mix(in srgb, var(--anatomy-purple) 38%, var(--iso-left))"/>
          <polygon points="439,422 516,401 516,449 439,470" fill="color-mix(in srgb, var(--anatomy-purple) 47%, var(--iso-right))"/>
          <path class="iso-edge" d="M397 397L472 377L516 401L516 449L439 470L397 444Z M397 397L439 422L516 401 M439 422V470"/>
          <path class="detail-stroke-fine" d="M414 409L481 391M414 421L493 400M414 433L499 410"/>
          ${bolts([[409,408],[469,391],[503,409],[409,437],[449,458],[503,440]], 2.2)}
          <text class="diagram-micro" x="411" y="451">INVERTER</text>
          <path class="flow-line power-flow" d="M448 417C418 415 398 417 374 427" marker-end="url(#car-arrow-orange)"/>
          <rect class="selection-ring" x="386" y="365" width="141" height="117" rx="18"/>
        `, -58, -40)},

        ${part("car-motor", "Rear traction motor", `
          <ellipse cx="365" cy="434" rx="51" ry="28" fill="var(--iso-metal)" stroke="var(--iso-edge)" stroke-width="1.4" transform="rotate(-15 365 434)"/>
          <ellipse cx="343" cy="440" rx="34" ry="24" class="iso-dark" transform="rotate(-15 343 440)"/>
          <ellipse cx="389" cy="428" rx="24" ry="15" fill="var(--iso-metal-light)" stroke="var(--iso-edge)" transform="rotate(-15 389 428)"/>
          <path class="detail-stroke-fine" d="M328 418L389 452M337 409L399 443M350 404L409 435"/>
          <circle cx="399" cy="425" r="7" fill="var(--anatomy-orange)" stroke="var(--iso-edge)"/>
          <text class="diagram-micro" x="322" y="477">TRACTION MOTOR</text>
          <path class="flow-line mechanical-flow" d="M328 446C307 458 296 469 287 487" marker-end="url(#car-arrow-orange)"/>
          <rect class="selection-ring" x="302" y="392" width="119" height="98" rx="20"/>
        `, -88, -30)},

        ${part("car-rear-drive", "Rear reduction and axle", `
          <ellipse cx="405" cy="462" rx="40" ry="20" fill="var(--iso-metal-light)" stroke="var(--iso-edge)" stroke-width="1.3" transform="rotate(-15 405 462)"/>
          <ellipse cx="405" cy="462" rx="15" ry="8" class="iso-dark" transform="rotate(-15 405 462)"/>
          <g class="rotating-part">
            <path class="detail-stroke" d="M368 462H443M405 443V481M379 449L431 475M431 449L379 475"/>
          </g>
          <path class="detail-stroke" d="M405 462L320 510M405 462L490 414" stroke-width="5"/>
          <text class="diagram-micro" x="371" y="496">REAR DRIVE</text>
          <rect class="selection-ring" x="290" y="399" width="219" height="127" rx="20"/>
        `, -60, 34)},

        ${part("car-cooling", "Thermal management loop", `
          <path class="flow-line data-flow" d="M458 390C495 345 555 325 603 336C656 348 686 373 712 403C735 432 770 442 816 429"/>
          <path class="flow-line data-flow" d="M814 429C848 416 870 400 891 375"/>
          <polygon points="873,352 928,338 961,356 904,371" fill="color-mix(in srgb, var(--anatomy-cyan) 58%, var(--iso-top))"/>
          <polygon points="873,352 904,371 904,421 873,401" fill="color-mix(in srgb, var(--anatomy-cyan) 34%, var(--iso-left))"/>
          <polygon points="904,371 961,356 961,406 904,421" fill="color-mix(in srgb, var(--anatomy-cyan) 42%, var(--iso-right))"/>
          <path class="iso-edge" d="M873 352L928 338L961 356L961 406L904 421L873 401Z M873 352L904 371L961 356 M904 371V421"/>
          <path class="detail-stroke-fine" d="M885 366L948 349M885 377L953 359M885 389L953 371"/>
          <text class="diagram-micro" x="881" y="413">THERMAL LOOP</text>
          <rect class="selection-ring" x="441" y="313" width="531" height="143" rx="26"/>
        `, 38, -74)},

        ${part("car-sensors", "Vehicle and driver sensing", `
          <g>
            ${sensorDots}
            <path class="signal-flow flow-line" d="M349 467C428 443 505 420 581 402C646 386 697 386 751 399" marker-end="url(#car-arrow-blue)"/>
            <path class="signal-flow flow-line" d="M507 535C578 499 644 465 751 414" marker-end="url(#car-arrow-blue)"/>
            <path class="signal-flow flow-line" d="M782 493C778 465 777 439 791 416" marker-end="url(#car-arrow-blue)"/>
            <path class="signal-flow flow-line" d="M948 405C908 399 883 399 852 402" marker-end="url(#car-arrow-blue)"/>
            <path class="signal-flow flow-line" d="M650 397C688 398 722 401 758 406" marker-end="url(#car-arrow-blue)"/>
          </g>
          <rect class="selection-ring" x="330" y="376" width="641" height="183" rx="28"/>
        `, 0, -95)},

        <g aria-hidden="true">
          <path class="flow-line power-flow" d="M457 466C426 454 400 444 385 438" marker-end="url(#car-arrow-orange)"/>
          <path class="flow-line power-flow" d="M394 428C373 426 355 429 339 438" marker-end="url(#car-arrow-orange)"/>
          <path class="flow-line mechanical-flow" d="M337 450C323 465 313 480 306 496" marker-end="url(#car-arrow-orange)"/>
          <path class="signal-flow flow-line" d="M789 405C710 423 625 437 519 437" marker-end="url(#car-arrow-blue)"/>
        </g>

        <text class="diagram-label" x="175" y="628">REAR · DRIVEN</text>
        <text class="diagram-label" x="938" y="628">FRONT · STEERED</text>
        <text class="diagram-micro" x="493" y="670">SYSTEM TOPOLOGY · ILLUSTRATIVE PACKAGING · NOT CAD</text>
      </svg>`;
  }

  return carSvg;
})();
