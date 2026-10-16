# Reproduce the controller from LapSim only

`controller/UPSTREAM.md` and `controller/import-manifest.json` identify the
scoped import. The original source is unchanged. All Python dependencies are
standard-library/local modules; the normal simulator environment is sufficient.
The default desktop demo does not require a native compiler or emulator.

From a fresh LapSim checkout, with no Studio checkout on the import path:

```text
python scripts/check_controller_import.py
python -B -m unittest discover -s controller/reference -p "test_*.py" -q
python -B controller/reference/bench_replay.py controller/reference/bench-scenario.example.json --output replay.json --csv trace.csv
```

For actual five-owner native C execution, install a GCC/Clang-compatible host
compiler under its own license and put it on PATH, set CC, or pass `--cc`:

```text
python -B controller/reference/native_bench_replay.py --example --output-dir /absolute/new/attempt --cc gcc
python scripts/export_bench_viewer.py --receipt /absolute/new/attempt/viewer-receipt.json --output native-review.html
```

On Windows replace the example output path with a new absolute Windows path
and use the compiler's executable name or full path. The retained upstream
runner rejects outputs under its source-root ancestor, requires a new attempt
directory and never overwrites an old receipt. An external temporary/evidence
directory is appropriate; the parent directory must already exist. Missing
compilers fail explicitly. There is no Python fallback labeled as C.

The native runner compiles and loads all five C owners, compares actual results
with Python, retains commands/binary/source identities and emits a viewer
receipt. The supplied 18-cycle synthetic fixture expects 9 allowed cycles,
9 held cycles and 5 recovery-pending cycles. An allowed cycle can still command
zero; these are state/command observations, not achieved tire forces.

`research/TC-03I-evidence/` and the earlier ARM object cohorts are immutable
historical evidence. A fresh successful host run establishes relocation/native
SIL behavior only. Closed-loop plant integration, a linked bench image,
STM32 emulation and physical PIL retain separate acceptance gates in issue #19.
