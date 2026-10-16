# TC-03G — Base guard Cortex-M4 object annex

**The unchanged portable base guard compiles as a strict binary64 Cortex-M4 object under both candidate ABIs.** The four object builds, sixteen object inspections and six version/multilib calls all exited zero. Each ABI produced the same object hash in its two repetitions. This adds object feasibility for the guard introduced in [TC-03F](TC-03F-base-command-guard.md); it does not establish target runtime behavior.

## Fixed question and execution

The [protocol](TC-03G-base-guard-object-protocol.json), SHA-256 `6fd1aa2c1aab66d5fef12ccb46d727e233ecc1d4a531eb21e7148e55ad9b8d20`, was committed at `532e68dc9cbee4b67a6c2101aeb112e015b59c50` before implementing the annex driver. The source base is PR74 `611dfe43c60140465169fed3ca9b9558b3360a0e`. The driver and its nine software-only tests received source review before the single actual attempt.

Only `torque_guard.c`, `torque_guard.h` and the unchanged `torque_contract.h` were snapshotted. The matrix compiled only `torque_guard.c`: hard and softfp argument conventions, twice each. The old [TC-03E three-unit cohort](TC-03E-cortex-m4-object-feasibility.md), its protocol and every earlier receipt remain separate and unchanged. Neither the allocator nor another native unit was added to this experiment.

The attempt reused the retained official [Arm Toolchain for Embedded 22.1.0 Windows package](https://github.com/arm/arm-toolchain/releases/tag/release-22.1.0-ATfE). Before executing any tool, it freshly checked the 710,565,705-byte ZIP against SHA-256 `9db55e43d5fdb1619692259897bf1e64f61da82a558827aae6928a2ccb39d348` and all 48,211 existing extracted files against that ZIP. The fresh file-manifest hash is `e61db4e336f1727579b6a5581d07feaa859c3c472960187ec52fff794aa7aa0a`. There was no new download, extraction or global installation. Twenty-eight distinct packaged header dependencies were bound to this freshly verified tree.

The source's binary64 and unsafe-math guards stayed intact. Flags explicitly selected ARMv7E-M, Cortex-M4, Thumb, little endian, the FPv4 single-precision FPU, C11/O2, freestanding compilation, warning-as-error diagnostics, `--no-default-config`, `-fno-fast-math`, `-fno-finite-math-only`, `-ffp-contract=off` and `-fexcess-precision=standard`. The complete ordered flags, recorded arguments, stdout/stderr hashes and actual streams are retained in [the evidence](TC-03G-evidence/README.md). No linker or target program ran.

## Observed objects

| Candidate ABI | Object file | Berkeley text | Data | BSS | Largest emitted local frame |
| --- | ---: | ---: | ---: | ---: | ---: |
| hard | 6,572 B | 2,677 B | 0 B | 0 B | 72 B |
| softfp | 6,604 B | 2,709 B | 0 B | 0 B | 72 B |

The hard object SHA-256 is `125aed6d4048d37dbdfc2531c02d77af061b8e65e9acaaf8c79b0f4dd8ceae0f`; softfp is `de0c6e8b457f50e1658e8e540200734e9c5c9b8df75695ca701c56f2d8b90bb4`. Both repeated pairs matched exactly on this host with these inputs. This is observed repeatability, not a guarantee across compilers or environments.

Both files are little-endian ELF32 ARM relocatables. Their binary attributes report ARMv7E-M, M-profile, Thumb-2 and single-precision VFPv4-D16. Hard explicitly reports VFP argument passing (`Tag_ABI_VFP_args=1`); softfp omits that tag, whose default is the base convention (`0`). These remain candidate ABIs until the team's actual build is known. The [Arm ABI addenda](https://github.com/ARM-software/abi-aa/blob/2025Q4/addenda32/addenda32.rst) defines the attributes. The [existing ST source discussion](TC-03E-cortex-m4-object-feasibility.md#scope-and-fixed-build) explains why this FPU selection does not provide hardware double-precision arithmetic.

Both objects still reference `__aeabi_dadd`, `__aeabi_dmul`, four software double-comparison helpers, `__finite`, `memset`, `tc_contract_reason` and `tc_validate_allocation`. The final two references are expected: this annex deliberately does not compile or link the contract unit. Undefined references do not demonstrate successful library linkage, helper behavior, runtime cost or an executable controller.

The 72-byte `static` record belongs to `tc_apply_command_guard`; other emitted local frames are 0–16 bytes. Clang's local `.su` record excludes callees, software helpers, interrupts, FPU context, scheduler and whole-program nesting. Likewise, [llvm-size's Berkeley text accounting](https://llvm.org/docs/CommandGuide/llvm-size.html) includes read-only content beyond instructions. Object bytes and zero data/BSS exclude link layout, helpers, libraries, startup and runtime storage. No combined stack bound, firmware footprint, memory fit or timing budget is inferred.

## Review and reproduction

The full local reference suite passed **490 tests** in 19.324 seconds, including the nine new software-only annex guards. These guards forbid subprocess execution and cover frozen identity, changed sources/helpers/protocols, exact flag order, the single permitted unit, ABI scope, existing-attempt preservation, retained-attempt descendants and rejection before tools for an unverified archive. Host test duration is not a controller timing measurement.

An [independent file-only review](TC-03G-evidence/independent-artifact-review.json) found no actionable mismatch in the bounded experiment. It independently decoded all four ELF objects' sections, symbols and ARM attributes; reconciled all 26 exact argument/log pairs, dependency/stack records and both repeated pairs; and verified the archive plus 34 used package files against the ZIP, current tree and fresh manifest. It checked all 48,211 manifest paths and ZIP sizes; unused file contents rely on the source-bound full verification performed before execution. It also confirmed the old twelve objects, six native inputs, original protocol and old receipts remain unchanged. This review made zero executable/tool/target calls.

That artifact review is distinct from the pre-execution source review and from GitHub's host reference/parity checks. Generated ARM objects are retained locally with their source snapshots, dependencies, stack files and all original streams; no toolchain, ZIP or generated binary is committed.

From the repository root, run the software-only annex tests with:

```powershell
py -3.12 -B -m unittest discover -s projects/enme408-torque-control/reference -p test_guard_cortex_m4_objects.py -v
```

For a deliberately new object-only attempt, use the named retained package and a new output directory:

```powershell
py -3.12 -B projects/enme408-torque-control/reference/guard_cortex_m4_objects.py --toolchain-dir "$env:ARM_ATFE_ROOT" --archive "$env:ARM_ATFE_ARCHIVE" --output-dir .\artifacts\tc03g-new-attempt
```

The exact part, team toolchain/ABI/library/startup configuration, approved resource budgets and signal mapping remain unresolved. Review still needs a complete authorized link/map, target numerical parity including subnormals, measured timing/stack and staged bench evidence. This Codex-assisted object experiment makes no STM32 execution, WCET, HIL, CAN, firmware-fit, course-acceptance or vehicle-safety claim.
