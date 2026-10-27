# Simulated endurance and efficiency points

`lapsim.experiments.tournament_scoring` is a pure scoring function for saved
outcomes. It does not run or retune a controller. Its basis is [SAE 2027 V1,
D12.13 and D13.3–4](https://www.fsaeonline.com/cdsweb/gen/DownloadDocument.aspx?DocumentID=da79bcb4-0935-4f7b-83d7-0dbb8ce68d38).
The intended split is endurance 275 maximum plus efficiency 100 maximum.

These are **FSAE-inspired simulated points**, not official event results.
Equal simulated laps replace an endurance event, the 25-point completion
credit is simulated, and no real driver change, inspection or cone/off-course
penalty tally is implemented here. A caller must provide penalties explicitly
and disclose whether they are modeled. A physical corridor failure must not
be silently converted into an invented time penalty.

For valid full finishers, corrected time includes supplied penalties. With
`Tmax = 1.45 * Tbest`, endurance is
`250 * ((Tmax / Ti) - 1) / ((Tmax / Tbest) - 1) + 25` below the cutoff.
Slower full finishers receive only simulated completion credit. Failed or
unfinished runs receive no time credit and must not enter an aggregate as
successful low-energy laps. There is no linear partial-distance award.

Efficiency uses net battery energy, so regen is credited once. Convert EV
energy to CO2 equivalent with `C = 0.65 * net_kWh`. The factor is
`F = ((Tref/NtimeRef)/(Ti/Ni)) * ((Cref/NenergyRef)/(Ci/Ni))`.
The time and energy references are independently selected eligible competitors.
The score is `100 * (F - Fmin) / (Fmax - Fmin)`, where this implementation
interprets Fmax as the best eligible observed factor. Fmin uses 1.45 times
the reference average lap time and the EV consumption cap of 0.308 kWh/km
(20.02 kg CO2/100 km). Efficiency requires measurable positive net energy,
completion, the time cutoff and the energy cap.

`score_field` rejects mixing geometry, hardware or lap counts. It returns
component points, eligibility reasons, corrected time, exact references and
the version/source alongside `official_points: false`. Missing or unreliable
completed reference inputs make the field unavailable. Nonfinite conversion,
normalization and nonpositive denominator cases cannot produce a winner.
One-lap and equal ten-lap strata are regression-tested separately.

The caller must freeze field membership and mark partial fields provisional.
Our six-course tournament averages the six course subtotals equally, only
for candidates with full valid coverage; that aggregation is a tournament
choice rather than a rulebook formula. Preserve fastest, lowest-energy and
time-energy Pareto views separately. Power/voltage are feasibility constraints,
not additional objective rewards. The caller owns those constraints; this
function does not certify an 80 kW/600 V or low-speed-regen implementation.

Keep executed values and raw records at full precision. Present points and
measurements with sensible significant figures and units, with exact values
available. This source increment changes no live presentation, controller,
saved input or simulation result. Required source integration and presentation
release remain separate reviewed actions.
