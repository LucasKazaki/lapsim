# TC-03E — Cortex-M4 object feasibility

**The unchanged contract, clock and pedal C files cross-compiled as ARM Cortex-M4 objects under both hard and softfp ABI candidates. Both variants retain software double-precision dependencies.** This is object-build evidence, not target firmware, measured behavior or a memory/timing approval for the car.

## Scope and fixed build

The owner identifies the existing custom board as STM32F405. The exact part, team compiler, ABI, startup, library configuration and approved resource budgets remain unknown. [ST DS8626 Rev12, sections 2/3.1](https://www.st.com/resource/en/datasheet/dm00037051.pdf) and [AN4044 Rev2, section 3/Table 6](https://www.st.com/resource/en/application_note/dm00047230-floating-point-unit-demonstration-on-stm32-microcontrollers-stmicroelectronics.pdf) describe a single-precision FPU. Binary64 data storage or VFP argument passing does not imply double-precision arithmetic hardware.

The [protocol](TC-03E-cortex-m4-object-protocol.json), SHA-256 `c1c8117a1c8a1e765afb8c2e44ab0362af7cbd296806a07498c348505fbf8f2a`, was reviewed before ARM compiler calls. It binds the six C/H sources from PR71 `b1646b666187172443f25189ea4aa14d88ba811c`, two ABI candidates and two repetitions, for twelve objects. No native C/H, floating-point policy, runtime behavior or previous PR head changed.

Arm's official GNU guide was read, but its ordinary downloads page returned Access Denied. The permitted fallback was the [official Arm Toolchain for Embedded 22.1.0 Windows release](https://github.com/arm/arm-toolchain/releases/tag/release-22.1.0-ATfE). The 710,565,705-byte archive was below the frozen 1 GiB cap; SHA-256 `9db55e43d5fdb1619692259897bf1e64f61da82a558827aae6928a2ccb39d348` matched both release metadata and the published checksum. Disk space was checked before acquisition. The archive was streamed, verified and extracted under the workspace; nothing was globally installed. All 48,211 extracted files were then compared serially against the verified ZIP before tool execution. Package version/license provenance and exact tool hashes are retained in [the evidence](TC-03E-evidence/summary.json). No archive, toolchain or generated object is committed.

The explicit target was `--target=armv7em-none-eabi -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mlittle-endian`, with `-mfloat-abi=hard` or `softfp`. C11/O2, freestanding compilation, warning-as-error diagnostics, `-fno-fast-math`, `-fno-finite-math-only`, `-ffp-contract=off` and `-fexcess-precision=standard` preserve the declared binary64 policy. The source's binary64/unsafe-math guards remain intact. No Omax/Osize config, linker, startup, HAL, board mapping, target emulator, flash command or actuation was used.

The [official release README](https://github.com/arm/arm-toolchain/blob/release-22.1.0-ATfE/arm-software/embedded/README.md) explains automatic multilib selection from target/FPU flags and warns that Omax enables fast-math. With `--no-default-config`, the actual driver selected `armv7m_hard_fpv4_sp_d16_exn_rtti_unaligned_size` for hard and `armv7m_soft_fpv4_sp_d16_exn_rtti_unaligned_size` for softfp. That library-directory naming is reported verbatim; it does not replace the explicit CPU flags or the checked ARMv7E-M object attributes. The driver found the packaged headers without a guessed sysroot. Twenty-eight distinct toolchain dependencies were matched to the manifest verified before calls.

## Actual object evidence

Every compilation and all 48 object-inspection commands exited zero. Each of the six ABI/unit pairs produced identical object hashes in its two repetitions on this host, with this source/toolchain/flag set.

| Unit | Hard text | Softfp text | Data, each | BSS, each | Largest emitted local frame, hard / softfp |
| --- | ---: | ---: | ---: | ---: | ---: |
| `torque_contract.c` | 3,877 B | 3,901 B | 0 B | 0 B | 104 / 112 B |
| `torque_clock.c` | 978 B | 970 B | 0 B | 0 B | 432 / 432 B |
| `torque_pedal.c` | 1,460 B | 1,484 B | 0 B | 0 B | 48 / 48 B |
| Unlinked object sums | 6,315 B | 6,355 B | 0 B | 0 B | No combined-stack bound inferred |

“Text” is [llvm-size's Berkeley object accounting](https://llvm.org/docs/CommandGuide/llvm-size.html), which includes read-only content beyond instruction bytes. The full ELF section tables and SysV reports are retained. These sums exclude linked helpers/libraries, startup, application integration, linker layout/alignment and runtime storage. Zero `.data`/`.bss` here does not imply zero RAM use or a complete firmware footprint. No exact-part memory capacity or fit percentage is assumed.

All objects are little-endian ELF32 ARM relocatables. Their attributes report ARMv7E-M, M-profile, Thumb-2, VFPv4-D16 plus single-precision-only use. Hard objects explicitly carry `Tag_ABI_VFP_args=1`; softfp objects omit that tag, whose default is the base convention (`0`). These are two candidate calling conventions, not evidence of the team's ABI. [Arm's ABI addenda](https://github.com/ARM-software/abi-aa/blob/2025Q4/addenda32/addenda32.rst) defines these tags; [llvm-readobj](https://llvm.org/docs/CommandGuide/llvm-readobj.html) retained the compiler's decoded attributes alongside the binary checks.

The contract objects reference `__aeabi_dadd`, `__aeabi_dsub`, `__aeabi_dmul` and double comparisons. The clock adds `__aeabi_ddiv` and `__aeabi_ui2d`; the pedal predicates also reference double comparisons. Both ABI variants retain these dependencies, along with libc/math references such as `__finite`, `fabs`, `fmax`, `frexp`, `ldexp`, memory/string functions and the clock's external `tc_decide`. These are unresolved object references, not measured helper cost, successful library linkage or validated library edge-case behavior.

[Clang's `-fstack-usage`](https://clang.llvm.org/docs/ClangCommandLineReference.html) emitted `.su` entries with `static` qualifiers. `tc_clocked_decide` has a 432-byte local frame in both variants, including its fixed cycle copy; `tc_validate_allocation` has 104/112 bytes. These are compiler-local frames. Called function/helper frames, interrupt/FPU context, task nesting, scheduler behavior and complete call-chain stack use remain unmeasured. The result is not GCC stack evidence or a whole-program stack bound.

## Retained metadata failure and post-run repair

The original build harness correctly kept its overall `failed_retained` status: after successful compile/inspection it fed Windows `.d` paths to a POSIX shell lexer, which removed literal backslashes. All twelve rows therefore reported `metadata_error`. The [exact original receipt](TC-03E-evidence/original-receipt.json), executed source and original artifacts remain unchanged.

A post-run make-dependency lexer preserves the observed literal drive paths, escaped spaces and continuations. A separate [file-only reaccount](TC-03E-evidence/file-only-reaccount.json) rechecked all twelve existing objects, all 66 original command logs, source snapshots, ARM attributes, sections, stack data, dependency hashes and repeat hashes. It made **zero new compiler or inspection-tool calls**. The old failure is not rewritten as a clean original run.

Independent review also tightened the helper API to require the exact frozen flag list and order. The original twelve commands already came from the hash-pinned protocol, so their math/target flags were unaffected. The active driver is a distinct post-run source hash; it must not be presented as the exact source executed for those objects. Seventeen focused tests cover identity, path containment, protocol/source changes, tool tampering, ABI tags, malformed metadata, local-stack qualifiers, literal Windows paths, escaped spaces, and flag additions/removals/reordering.

A separate [independent file-only review](TC-03E-evidence/independent-file-review.json) found no actionable mismatch in this frozen cohort. It parsed all twelve ELF headers, section tables and symbol tables independently; reconciled raw sections, undefined symbols, ARM attributes and stack records; checked all 66 command/log pairs, six source snapshots, 28 pre-call-verified headers, four current tool hashes and six repeated object pairs. It also exercised eight dependency strings, 45 rejected flag mutations and six canonical commands without compiler, target or model calls. This is a bounded source/artifact review, not authentication of arbitrary receipts or approval of firmware, timing or hardware behavior.

The first GitHub Windows reference job then exposed a separate path-alias bug: the runner's `RUNNER~1` temporary path resolved to `runneradmin`, while relative-path accounting still used the unresolved owner. A later one-line repair canonicalizes both dependency roots; its test also compares canonical output paths. An added noncanonical `..` owner regression reproduces the same mismatch on any host. The old helper fails that case; the repaired helper passes, and all eighteen focused checks pass. [The repair receipt](TC-03E-evidence/ci-canonical-path-repair.json) preserves the exact failed head/log binding and distinct new source/test hashes. No compiler, protocol, native source, object or original audit was changed. The initial seventeen-check evidence remains historical rather than being relabeled.

## Reproduce deliberately

From the Studio repository root, ordinary Python 3.12 runs the software-only guards:

```powershell
py -3.12 -B -m unittest discover -s projects/enme408-torque-control/reference -p test_cortex_m4_objects.py -v
```

Acquire and verify the named official archive, retain its notices, and extract it to an otherwise unchanged directory. Set `ARM_ATFE_ROOT` to that extracted top-level directory and `ARM_ATFE_ARCHIVE` to the ZIP. Then a **new** object-only attempt can be made with:

```powershell
py -3.12 -B projects/enme408-torque-control/reference/cortex_m4_objects.py --toolchain-dir "$env:ARM_ATFE_ROOT" --archive "$env:ARM_ATFE_ARCHIVE" --output-dir .\artifacts\tc03e-new-attempt
```

The utility verifies the archive/tree, rejects existing attempts and changed sources, snapshots code/protocol/input bytes, records commands before launching tools, and retains failures. The original two build repetitions used the archived original driver; the active post-run driver has passed software guards and file-only inspection but has not generated replacement objects. Existing retained artifacts can be reaccounted without any tool call using `cortex_m4_reaccount.py --run <original-attempt> --output <new-audit.json>`.

Team review still needs the actual part/build/ABI/library configuration and resource budgets, a complete link/map, base guard/slew integration, runtime parity on target, measured timing and stack, signal ownership and staged hardware evidence. No target timing, WCET, HIL, CAN behavior, firmware fit, course acceptance or vehicle-safety claim follows from this object-only result. This is Codex-assisted engineering evidence for review, not an activation or deployment.
