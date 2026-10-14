# Quality gates and audit evidence

This suite distinguishes observable correctness from appearance and from model validation. A passing workflow is not an Apple certification or proof that the vehicle model matches a real car.

## Five complementary review tools

- **Ruff 0.17.0:** broad Python bug-pattern/hygiene report plus a blocking syntax, undefined-name, and invalid-control-flow gate. Broad stylistic findings and formatter differences remain visible in artifacts; they are not automatically rewritten across scientific code.
- **Pyright 1.1.414:** full `src` type analysis. Existing findings are compared with main at `1e8e35a` in the same dependency environment. New diagnostic fingerprints, including added copies of an existing diagnostic, block integration. Existing type debt is not a clean result and needs a separately reviewed contract-refactoring pass.
- **Semgrep CE 1.180.0:** Python and JavaScript security rules. Findings, parse errors, and failed scans block the check. This is not dependency, secret-history, or penetration testing. The registry rules may evolve; tool versions and raw results are retained.
- **Hypothesis 6.169.1:** deterministic generated input contracts for controls, interpolation, periodic seams, battery power balance, and combined tire-force bounds. Existing pytest tests run independently in six process-isolated partitions, including Tk tests under Xvfb.
- **Playwright 1.64.0 with axe-core 4.14.0:** Chromium and WebKit map/anatomy interaction checks; desktop/mobile sizes, system/manual themes, keyboard navigation, reduced motion, large-graph virtualization, and automated WCAG checks. A separate actual Pyodide browser test checks both supplied profiles and native replay of downloaded records. No mocked physics is used.

The Windows job rebuilds the portable executable with `requirements-build.lock` and executes its frozen self-test outside the checkout without Python/Git on PATH. It does not replace manual signed-release, Windows hardware, or assistive-technology testing.

## Evidence and limits

Every failing run retains its raw diagnostic files and screenshots. Native tests preserve all module reports, failures, errors, skips, and timeouts. A missing private team evidence bundle is recorded as a skip, not a pass. Browser traces are retained for debugging. CI source and runtime identities identify the actual tested revision.

The October 14 baseline found an accepted drive-to-regeneration profile that failed only when sampled, mismatched accessible names, and interactive SVGs hidden behind image-only semantics. The integration fixes those contracts and retains regression tests. The source map is regenerated from the actual Python code; CI rejects stale generated equations.

Manual acceptance still requires VoiceOver/NVDA and real-device testing, review of focus visibility and motion behavior, and calibrated vehicle/track data before claiming predictive lap times or validating torque control. A numerical test can check an equation's contract without establishing the physical validity of its assumptions.

## Reproduction

Install the repository in an isolated Python environment before running subprocess/CLI tests: `python -m pip install -e '.[dev]'`.

```sh
python -m pytest quality/test_properties.py --hypothesis-show-statistics
xvfb-run -a python quality/run_native_shard.py 0 6  # repeat shards 0 through 5
python quality/run_source_audit.py
python quality/run_browser_audit.py chromium
python quality/run_browser_audit.py webkit
python scripts/build_web.py --output-dir dist/web
pwsh -NoProfile -File scripts/stage_team_site.ps1 -OutputDirectory dist/web
python quality/run_web_runtime.py
```

Tool installation and platform requirements are specified in `.github/workflows/quality-audit.yml`. On Windows use `python scripts/build_windows.py` for the complete build-and-test path.

## Primary-source references

- Ruff: https://docs.astral.sh/ruff/
- Pyright: https://github.com/microsoft/pyright
- Semgrep CE: https://semgrep.dev/docs/semgrep-ce
- Hypothesis: https://hypothesis.readthedocs.io/
- Playwright accessibility and its limits: https://playwright.dev/docs/accessibility-testing
- Apple accessibility guidance: https://developer.apple.com/design/human-interface-guidelines/accessibility
