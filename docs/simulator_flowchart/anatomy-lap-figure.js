window.ANATOMY_LAP_SVG = (() => {
  "use strict";
  const { part, bolts } = window.ANATOMY_CORE;

  function lapSvg() {
    const railSleepers = Array.from({ length: 11 }, (_, index) => {
      const x = 292 + index * 47;
      const y = 521 - index * 11.8;
      return `<path class="detail-stroke-fine" d="M ${x - 11} ${y + 17} L ${x + 16} ${y + 10}"/>`;
    }).join("");

    const batteryCells = Array.from({ length: 12 }, (_, index) => {
      const col = index % 4;
      const row = Math.floor(index / 4);
      return `<rect x="${635 + col * 18}" y="${353 + row * 19}" width="13" height="14" rx="2.5" fill="var(--anatomy-green)" opacity="${0.66 + row * 0.08}"/>`;
    }).join("");

    const scoreTicks = Array.from({ length: 9 }, (_, index) => {
      const y = 365 + index * 13;
      return `<path class="detail-stroke-fine" d="M 1012 ${y} H ${1036 + (index % 3) * 8}"/>`;
    }).join("");

    return `
      <svg class="anatomy-svg lap-figure" viewBox="0 0 1200 720" role="group" aria-labelledby="lap-figure-title" aria-describedby="lap-figure-desc">
        <title id="lap-figure-title">Interactive isometric LapSim distance-domain test bench</title>
        <desc id="lap-figure-desc">A physical test bench metaphor for the LapSim course input, controls, speed constraints, component physics, distance-cell integration, telemetry, scoring, and optional experimental modules.</desc>
        <defs>
          <linearGradient id="lap-screen-glow" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stop-color="#112535"/>
            <stop offset="1" stop-color="#05090d"/>
          </linearGradient>
          <radialGradient id="lap-spool" cx="35%" cy="28%" r="75%">
            <stop offset="0" stop-color="var(--iso-metal-light)"/>
            <stop offset="1" stop-color="var(--iso-metal)"/>
          </radialGradient>
          <filter id="lap-soft-shadow" x="-30%" y="-30%" width="160%" height="180%">
            <feDropShadow dx="0" dy="10" stdDeviation="12" flood-color="#000" flood-opacity="0.2"/>
          </filter>
          <marker id="lap-arrow-orange" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M0 0L10 5L0 10Z" fill="var(--anatomy-orange)"/>
          </marker>
        </defs>

        <ellipse class="figure-shadow" cx="598" cy="592" rx="465" ry="84"/>

        ${part("lap-vehicle", "Vehicle coordinator cabinet", `
          <polygon class="iso-top" points="568,326 718,286 798,329 644,371"/>
          <polygon class="iso-left" points="568,326 644,371 644,506 568,458"/>
          <polygon class="iso-right" points="644,371 798,329 798,463 644,506"/>
          <path class="iso-edge" d="M568 326L718 286L798 329L798 463L644 506L568 458Z M568 326L644 371L798 329 M644 371V506"/>
          <rect x="661" y="388" width="103" height="73" rx="8" fill="var(--iso-dark)" opacity="0.9"/>
          <path class="detail-stroke" d="M676 406H748M676 423H734M676 440H756"/>
          ${bolts([[581,342],[704,307],[782,342],[581,445],[657,488],[782,450]], 2.8)}
          <text class="diagram-micro" x="676" y="479">VEHICLE COORDINATOR</text>
          <rect class="selection-ring" x="557" y="277" width="252" height="238" rx="20"/>
        `, 0, -28)},

        ${part("lap-course", "Course and curvature reel", `
          <path class="iso-bench-left" d="M112 451L221 482V563L112 529Z"/>
          <path class="iso-bench-right" d="M221 482L298 459V541L221 563Z"/>
          <path class="iso-bench-top" d="M112 451L189 431L298 459L221 482Z"/>
          <path class="iso-edge" d="M112 451L189 431L298 459L298 541L221 563L112 529Z M112 451L221 482L298 459 M221 482V563"/>
          <ellipse cx="195" cy="420" rx="67" ry="37" fill="url(#lap-spool)" stroke="var(--iso-edge)" stroke-width="1.3"/>
          <ellipse cx="195" cy="420" rx="42" ry="22" class="iso-dark"/>
          <ellipse cx="195" cy="420" rx="14" ry="8" fill="var(--anatomy-blue)"/>
          <path class="detail-stroke" d="M134 411C150 395 165 399 179 409C194 420 212 441 251 431"/>
          <path class="detail-stroke-fine" d="M128 423C146 407 164 412 181 424C200 438 222 447 257 437"/>
          <path class="flow-line data-flow" d="M251 431C290 422 315 427 348 443"/>
          <circle class="flow-node data-flow" cx="251" cy="431" r="5"/>
          <text class="diagram-micro" x="145" y="518">COURSE / CURVATURE</text>
          <rect class="selection-ring" x="101" y="371" width="208" height="204" rx="20"/>
        `, -38, 12)},

        ${part("lap-controls", "Driver request console", `
          <polygon class="iso-top" points="268,443 358,420 409,447 318,471"/>
          <polygon class="iso-left" points="268,443 318,471 318,542 268,512"/>
          <polygon class="iso-right" points="318,471 409,447 409,517 318,542"/>
          <path class="iso-edge" d="M268 443L358 420L409 447L409 517L318 542L268 512Z M268 443L318 471L409 447 M318 471V542"/>
          <path class="detail-stroke" d="M303 451L315 411M342 441L349 397M378 432L390 405"/>
          <circle cx="315" cy="410" r="8" fill="var(--anatomy-green)" stroke="var(--iso-edge)"/>
          <circle cx="349" cy="397" r="8" fill="var(--anatomy-red)" stroke="var(--iso-edge)"/>
          <circle cx="390" cy="405" r="8" fill="var(--anatomy-blue)" stroke="var(--iso-edge)"/>
          <rect x="286" y="482" width="90" height="23" rx="5" class="screen-fill"/>
          <path class="screen-trace" d="M294 495L306 490L318 499L331 488L345 494L358 486L368 491"/>
          ${bolts([[281,456],[397,459],[281,504],[397,506]], 2.5)}
          <text class="diagram-micro" x="283" y="528">DRIVER REQUESTS</text>
          <rect class="selection-ring" x="257" y="381" width="163" height="173" rx="20"/>
        `, -16, 48)},

        ${part("lap-envelope", "Corner and braking envelope drums", `
          <polygon class="iso-bench-top" points="382,392 496,362 565,399 448,430"/>
          <polygon class="iso-bench-left" points="382,392 448,430 448,514 382,473"/>
          <polygon class="iso-bench-right" points="448,430 565,399 565,482 448,514"/>
          <path class="iso-edge" d="M382 392L496 362L565 399L565 482L448 514L382 473Z M382 392L448 430L565 399 M448 430V514"/>
          <g class="rotating-part">
            <ellipse cx="437" cy="380" rx="45" ry="24" fill="var(--anatomy-blue)" opacity="0.78" stroke="var(--iso-edge)"/>
            <ellipse cx="437" cy="380" rx="17" ry="9" class="iso-dark"/>
            <path class="detail-stroke-fine" d="M397 374L477 387M404 364L470 396M417 358L458 402"/>
          </g>
          <g class="rotating-part">
            <ellipse cx="504" cy="361" rx="45" ry="24" fill="var(--anatomy-red)" opacity="0.74" stroke="var(--iso-edge)"/>
            <ellipse cx="504" cy="361" rx="17" ry="9" class="iso-dark"/>
            <path class="detail-stroke-fine" d="M464 355L544 368M471 345L537 377M484 339L525 383"/>
          </g>
          <path class="detail-stroke" d="M437 380L462 432M504 361L509 417"/>
          <text class="diagram-micro" x="402" y="476">CORNER + BRAKING PASSES</text>
          <rect class="selection-ring" x="371" y="326" width="205" height="200" rx="20"/>
        `, -8, -36)},

        <g aria-hidden="true">
          <path class="detail-stroke" d="M274 532L840 389" stroke-width="6"/>
          <path class="detail-stroke" d="M287 553L853 410" stroke-width="6"/>
          ${railSleepers}
        </g>

        ${part("lap-cell", "Vehicle cell integrator carriage", `
          <g class="solver-carriage">
            <polygon points="306,489 365,473 399,491 338,508" fill="var(--anatomy-blue)" opacity="0.88"/>
            <polygon points="306,489 338,508 338,544 306,524" fill="color-mix(in srgb, var(--anatomy-blue) 62%, black)"/>
            <polygon points="338,508 399,491 399,527 338,544" fill="color-mix(in srgb, var(--anatomy-blue) 78%, black)"/>
            <path class="iso-edge" d="M306 489L365 473L399 491L399 527L338 544L306 524Z M306 489L338 508L399 491 M338 508V544"/>
            <ellipse cx="324" cy="534" rx="10" ry="6" class="rubber"/>
            <ellipse cx="379" cy="519" rx="10" ry="6" class="rubber"/>
            <rect x="329" y="486" width="39" height="17" rx="4" class="screen-fill"/>
            <path class="screen-trace" d="M334 496L340 491L346 498L352 489L358 496L364 493"/>
            <path class="flow-line mechanical-flow" d="M399 511L432 502" marker-end="url(#lap-arrow-orange)"/>
          </g>
          <rect class="selection-ring" x="290" y="458" width="126" height="101" rx="18"/>
        `, 0, 58)},

        ${part("lap-battery", "Battery energy stack", `
          <polygon points="615,332 690,312 736,337 659,358" fill="color-mix(in srgb, var(--anatomy-green) 72%, var(--iso-top))"/>
          <polygon points="615,332 659,358 659,431 615,404" fill="color-mix(in srgb, var(--anatomy-green) 42%, var(--iso-left))"/>
          <polygon points="659,358 736,337 736,410 659,431" fill="color-mix(in srgb, var(--anatomy-green) 50%, var(--iso-right))"/>
          <path class="iso-edge" d="M615 332L690 312L736 337L736 410L659 431L615 404Z M615 332L659 358L736 337 M659 358V431"/>
          ${batteryCells}
          <path class="flow-line power-flow" d="M729 381C757 378 772 384 794 397"/>
          <circle class="flow-node power-flow" cx="729" cy="381" r="5"/>
          <text class="diagram-micro" x="626" y="414">BATTERY</text>
          <rect class="selection-ring" x="604" y="300" width="143" height="143" rx="18"/>
        `, 3, -84)},

        ${part("lap-powertrain", "Inverter motor and reduction dynamometer", `
          <polygon class="iso-top" points="747,320 814,303 855,325 787,344"/>
          <polygon class="iso-left" points="747,320 787,344 787,402 747,377"/>
          <polygon class="iso-right" points="787,344 855,325 855,383 787,402"/>
          <path class="iso-edge" d="M747 320L814 303L855 325L855 383L787 402L747 377Z M747 320L787 344L855 325 M787 344V402"/>
          <ellipse cx="844" cy="402" rx="45" ry="25" fill="var(--iso-metal)" stroke="var(--iso-edge)" stroke-width="1.3"/>
          <ellipse cx="844" cy="402" rx="27" ry="15" class="iso-dark"/>
          <g class="rotating-part">
            <path class="detail-stroke" d="M819 402H869M844 377V427M827 385L861 419M861 385L827 419"/>
          </g>
          <path class="flow-line mechanical-flow" d="M883 398C905 392 919 391 937 394"/>
          <circle class="flow-node mechanical-flow" cx="883" cy="398" r="5"/>
          <text class="diagram-micro" x="762" y="374">INVERTER / MOTOR</text>
          <rect class="selection-ring" x="736" y="289" width="164" height="151" rx="18"/>
        `, 32, -65)},

        ${part("lap-tires", "Tire force drums", `
          <g>
            <ellipse cx="921" cy="443" rx="30" ry="18" class="rubber"/>
            <ellipse cx="921" cy="443" rx="15" ry="9" class="rim"/>
            <ellipse cx="966" cy="431" rx="30" ry="18" class="rubber"/>
            <ellipse cx="966" cy="431" rx="15" ry="9" class="rim"/>
            <ellipse cx="938" cy="482" rx="30" ry="18" class="rubber"/>
            <ellipse cx="938" cy="482" rx="15" ry="9" class="rim"/>
            <ellipse cx="983" cy="470" rx="30" ry="18" class="rubber"/>
            <ellipse cx="983" cy="470" rx="15" ry="9" class="rim"/>
            <path class="detail-stroke" d="M921 443L938 482M966 431L983 470M921 443L966 431M938 482L983 470"/>
          </g>
          <text class="diagram-micro" x="908" y="516">TIRE CAPACITY</text>
          <rect class="selection-ring" x="884" y="405" width="137" height="123" rx="20"/>
        `, 75, 18)},

        ${part("lap-aero", "Aerodynamic load fan", `
          <polygon class="iso-top" points="860,285 928,267 972,291 902,310"/>
          <polygon class="iso-left" points="860,285 902,310 902,357 860,331"/>
          <polygon class="iso-right" points="902,310 972,291 972,338 902,357"/>
          <path class="iso-edge" d="M860 285L928 267L972 291L972 338L902 357L860 331Z M860 285L902 310L972 291 M902 310V357"/>
          <circle cx="917" cy="306" r="29" fill="var(--iso-dark)" stroke="var(--iso-edge)"/>
          <g class="rotating-part">
            <path d="M917 306C910 285 891 286 895 304C899 317 908 319 917 306Z" fill="var(--anatomy-cyan)" opacity="0.8"/>
            <path d="M917 306C938 299 944 317 926 322C913 326 909 316 917 306Z" fill="var(--anatomy-cyan)" opacity="0.8"/>
            <path d="M917 306C914 327 932 334 937 316C940 303 929 299 917 306Z" fill="var(--anatomy-cyan)" opacity="0.8" transform="rotate(120 917 306)"/>
          </g>
          <circle cx="917" cy="306" r="6" class="iso-metal-light"/>
          <path class="flow-line data-flow" d="M971 314C1002 316 1014 327 1028 345"/>
          <text class="diagram-micro" x="870" y="345">AERO LOAD</text>
          <rect class="selection-ring" x="849" y="255" width="134" height="113" rx="18"/>
        `, 70, -64)},

        ${part("lap-telemetry", "Aligned telemetry recorder", `
          <polygon class="iso-top" points="956,268 1055,242 1111,272 1011,299"/>
          <polygon class="iso-left" points="956,268 1011,299 1011,420 956,386"/>
          <polygon class="iso-right" points="1011,299 1111,272 1111,393 1011,420"/>
          <path class="iso-edge" d="M956 268L1055 242L1111 272L1111 393L1011 420L956 386Z M956 268L1011 299L1111 272 M1011 299V420"/>
          <path d="M979 298L1030 285L1083 313L1031 328Z" fill="url(#lap-screen-glow)" stroke="var(--iso-edge)"/>
          <path class="screen-trace" d="M991 307L1002 301L1013 314L1024 296L1036 310L1049 302L1065 311"/>
          <circle cx="990" cy="349" r="7" fill="var(--anatomy-green)"/>
          <circle cx="1012" cy="343" r="7" fill="var(--anatomy-orange)"/>
          <circle cx="1034" cy="337" r="7" fill="var(--anatomy-blue)"/>
          <path class="detail-stroke-fine" d="M978 369L1059 347M978 379L1045 361"/>
          <text class="diagram-micro" x="974" y="394">ALIGNED TELEMETRY</text>
          <rect class="selection-ring" x="945" y="229" width="177" height="203" rx="20"/>
        `, 86, -30)},

        ${part("lap-scoring", "Event timing and scoring register", `
          <polygon class="iso-top" points="996,431 1073,411 1117,434 1039,456"/>
          <polygon class="iso-left" points="996,431 1039,456 1039,544 996,518"/>
          <polygon class="iso-right" points="1039,456 1117,434 1117,522 1039,544"/>
          <path class="iso-edge" d="M996 431L1073 411L1117 434L1117 522L1039 544L996 518Z M996 431L1039 456L1117 434 M1039 456V544"/>
          <rect x="1010" y="451" width="82" height="48" rx="6" class="screen-fill"/>
          ${scoreTicks}
          <circle cx="1088" cy="517" r="8" fill="var(--anatomy-green)" stroke="var(--iso-edge)"/>
          <text class="diagram-micro" x="1010" y="529">TIME · ENERGY · POINTS</text>
          <rect class="selection-ring" x="985" y="400" width="143" height="155" rx="18"/>
        `, 84, 42)},

        ${part("lap-optional", "Optional path planner and four wheel laboratory", `
          <polygon points="438,248 555,216 625,253 505,286" fill="color-mix(in srgb, var(--anatomy-purple) 56%, var(--iso-top))"/>
          <polygon points="438,248 505,286 505,343 438,302" fill="color-mix(in srgb, var(--anatomy-purple) 35%, var(--iso-left))"/>
          <polygon points="505,286 625,253 625,310 505,343" fill="color-mix(in srgb, var(--anatomy-purple) 42%, var(--iso-right))"/>
          <path class="iso-edge" d="M438 248L555 216L625 253L625 310L505 343L438 302Z M438 248L505 286L625 253 M505 286V343"/>
          <path class="detail-stroke" d="M461 272C487 245 526 250 548 268C570 285 592 280 612 265"/>
          <circle cx="470" cy="276" r="6" fill="var(--anatomy-purple)"/>
          <circle cx="540" cy="264" r="6" fill="var(--anatomy-purple)"/>
          <circle cx="606" cy="266" r="6" fill="var(--anatomy-purple)"/>
          <path class="flow-line optional-flow" d="M571 322C588 347 594 362 601 382"/>
          <text class="diagram-micro" x="457" y="316">OPTIONAL / SEPARATE</text>
          <rect class="selection-ring" x="427" y="204" width="209" height="151" rx="20"/>
        `, -20, -72)},

        <g aria-hidden="true">
          <path class="flow-line data-flow" d="M399 503C442 490 474 484 512 474"/>
          <path class="flow-line power-flow" d="M512 474C577 457 634 442 681 427"/>
          <path class="flow-line mechanical-flow" d="M797 430C844 423 884 418 921 443"/>
          <path class="flow-line data-flow" d="M981 410C1010 397 1024 384 1035 365"/>
        </g>
      </svg>`;
  }


  return lapSvg;
})();
