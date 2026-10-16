# TC-01T: gear-efficiency-consistent synthetic power envelope

Scope: research-only for hypothetical 2027–28 U.S. Formula SAE Electric torque allocation. This is not firmware, vehicle approval, or a Company Runtime ACK.

Finding: the existing remote aggregate-power reference computes wheel power Σ(τ_wheel × ω_wheel). The unpublished TC-01R copper-loss experiment accounts for a drivetrain-efficiency factor in motor torque-to-current conversion but does not account for that factor when estimating positive shaft mechanical input power. For a **constant gearbox efficiency** η in (0,1], shaft mechanical power is Σ(τ_wheel × ω_wheel / η). The referenced TC-01S current ceiling is independent of this power constraint. These are frozen offline predecessors, not remotely integrated dependencies.

Synthetic counterexample: four hypothetical wheels each deliver 50 N·m at 10 rad/s. At η=0.8, wheel output is 2000 W while shaft input is 2500 W; with phase resistance 0.01 Ω, Kt=1 N·m/A_peak, and 5:1 gearing, modeled copper losses are 9.375 W. Against an *illustrative* 2300 W budget, TC-01R's 2009.375 W modeled demand does not limit; the corrected model does. A separate hypothetical 10 A_peak q-axis motor ceiling yields common torque scale 0.8.

Reference equation for forward-only motoring with a common scaling factor α:
P_model(α)=α Σ(τ_i ω_i/η_i) + α² Σ(1.5 R_i (τ_i/(G_i η_i Kt_i))²).
Select the minimum valid scale satisfying this assumed model, plus independent peak-q-axis current limits. No claim about battery DC demand, voltage, switching/iron losses, thermal behavior, gear no-load losses, regenerative operation or real car parameters.

Primary model reference: https://www.mathworks.com/help/sdl/ref/simplegear.html (gear power-transfer efficiency as output/input); https://www.mathworks.com/help/sdl/ref/simplegearwithvariableefficiency.html (gear efficiency can vary). Accessed 2026-10-13.

Verification: 18 new tests + 41 frozen predecessor tests = 59 passed in isolated CPython standard-library execution; 500 deterministic scenarios, plus an intentionally failing negative control of the older wheel-only calculation. No STM32F405, HIL or vehicle testing, and no full current-repository suite. The implementation/test/negative-control package is held as an external portable handoff; **do not treat this note as code integrated into PR #66**. TC-01R/S must be independently reviewed before integration.

Next: obtain verified gearbox efficiency/ratio and motor Kt, winding resistance, inverter current-convention and voltage limits, and reviewed real interface contracts. No automatic merge, runtime changes or vehicle command authorization.