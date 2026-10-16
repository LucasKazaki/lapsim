# Guard object annex evidence

This directory describes the single new four-object experiment. The historical TC-03E twelve-object attempt and its retained metadata failure are unchanged.

- `actual-receipt.json` is the exact original completed receipt: SHA-256 `b03ac8621d127153d4b0b354d00e9d8a3dd673d8735cd86527be89e47077ceb8`.
- `executed-driver.py.txt` preserves the exact driver bytes that ran. The active shared helper and all three native inputs are separately hash-bound by the receipt and frozen protocol.
- `command-logs.json` contains all 52 original UTF-8 stdout/stderr streams. Encoding each `utf8` value reconstructs its original bytes and stated hash.
- `retained-artifact-manifest.json` binds all 72 original local files, including four ELF objects, four dependency files, four local-stack files, source/protocol/driver snapshots and the fresh 48,211-file toolchain manifest. The generated binaries, full toolchain manifest and package are deliberately not committed.
- `summary.json` extracts the observed sizes, attributes, unresolved symbols and repetition results. It preserves the source/tool identities and explicit limits.
- `software-tests.txt` is the actual full-suite output: 490 passing reference tests. Expected error messages come from deliberate CLI rejection regressions.
- `independent-artifact-review.json` is the exact independent file-only review receipt, SHA-256 `97a80a90464ac841cd5916b5a603a5319021fc6c7fe38e0e562c00007c6fe0bc`. It states the independently checked files and the limits of unused package-file verification.

The full attempt remains at `work/enme408-guard-cortex-m4-v1` in the overnight workspace. A retained artifact hash is an identity check, not evidence that arbitrary replacement files are authentic. Review conclusions are bounded to the supplied source and actual local artifacts. No linking, target execution, hardware, GPU or model call took place in this annex.
