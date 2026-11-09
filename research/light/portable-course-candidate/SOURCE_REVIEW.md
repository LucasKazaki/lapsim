# E05 FSI construction: source review record

Date: 5 November 2026. Status: **UNTESTED / NOT IMPORTED / NOT INTEGRATED**.
Only source/data inspection, byte hashing, text comparison and Git operations
were performed. No candidate parser, geometry function, application module, test suite,
simulation, inference, optimizer, import, build or installation was executed.
This record is a manual review, not an execution receipt or qualification.

## Inspected baseline and owner results

| Source | Observed identity and scope |
| --- | --- |
| Local and remote main | `07ccb4b84138aedcc5b9cb85c2e81d283d6c132e` |
| Issue #19 | Open; E05 course reproducibility is one bounded part of the incomplete delivery plan |
| PR #166 | Open, unmerged; head `eda45185a4debeae7239dce906b72cfdf3909da9`; portable plant and licensed FSI inputs, no course-construction module |
| Readiness source | PRs #167/#168/#169 are separate work; #169 head `83eadd434156a217506ba3767302b08fef464ce6` was fetched for source inventory only |
| Policy/guidance report | Reported owner `<PRIVATE_CONVERSATION_ID>`, commit `9cf2db6646d3cc293756d0612e81ebf9b9beb912`, branch `cloud/lite-policy-guidance-20261105`, patch SHA-256 `73172ccb8d20931878c12df091d6f0eb343d1c159f871280720b12bf60484952` |

The reported policy/guidance commit is absent from the local object database;
the named branch is absent from the inspected remote branch inventory; the
named patch is absent from local scratch/shared files. A room-message search
for its exact name returned no result. There is no supported cross-owner
workspace/thread reader in the available tools. Recovery is **unavailable**,
not an action denied in this task, and the patch contents remain unknown.
No policy/guidance compatibility or integration is claimed.

The independent worktree is `<COURSE_SOURCE_ROOT>`, branch
`cloud/lite-course-construction-20261105`, based directly on main. All writes
are confined to this new directory under `research/light/`. The original
`<BASE_SOURCE_ROOT>` worktree and other owners' source areas were not edited.
Existing plan/readiness documents were inspected but left to their owners;
this record supplies the current pins for the bounded tranche. Nothing was
pushed, published or posted to an issue, so no hosted CI was triggered here.

## Exact input pins

| Input | Bytes | SHA-256 |
| --- | ---: | --- |
| Main `configs/courses/amz_fssim_fsi_approx.json` | 58174 | `443abe03651008cfb2452dd36a2360f5e2695f6af5ef1d2f468f31297b36a976` |
| PR #166 processed FSI bundle | 60423 | `46ce29a898f4491d3dc6456f42325769474fa7790ce4227a86a8ab537dcc373e` |
| Main `configs/courses/upstream/amz-fssim/FSI.yaml` | 7377 | `7e0cfd65403406e3d6cf0e12aeeb605efb0163b35f3b6312250f871f0ee85134` |
| PR #166 FSI YAML | 7708 | `a70ef6bc168801e1b985964e13c2ffbf4a540007ffc9bf84b23434b1a682c4a2` |

The main-file hashes/counts were observed with `sha256sum` and `wc -c`.
PR #166 bytes were inspected through `git show origin/review-166:<path>`
and piped to the same tools. These match that PR's provenance document.
The new loader separately requires the common LF identity at future call
time. That normalization branch has not been called here.

The preserved geometry digest is
`4d0404480da3f1035a4a22f6d94ae6870278d010ca8b215f0160b8263156210d`.
It covers `closed`, `distance_m`, `x_m`, `y_m` and `curvature_per_m` using the
archive's canonical JSON convention. The source length pin is
`216.14860023596088` m. These values were read from the source registry;
no geometry calculation was executed to establish them in this task.

## Extraction and manual review passes

1. **Dependency and arithmetic review.** `_fsi_geometry.py` retains normalized
   text from archived `racing_geometry.py` lines 11–79 and 172–217 at main.
   Original full-file SHA-256:
   `5db3492dfdf4418a980179f1f7d548e8c2e90cb4d7c3b4ce1c1f2cf4606fa253`.
   A source-text `diff -u` between those ranges (CRLF converted to LF) and the
   new file after its 11-line header returned exit 0 with no difference.
   This preserves the parser, polygon crossing checks, 96-centre reconstruction,
   fillets, full-grid comparison, SE(2) transform and numerical tolerances.
   Unused optimizer/clearance functions and imports were excluded.
2. **Input and identity review.** Raw byte type, finite byte-count inventory
   and SHA-256 are checked before JSON/YAML decoding. Identity is fixed in
   source, never supplied by a candidate. Strict JSON key/constant handling,
   channel shape/finite-value checks and the original canonical geometry
   digest precede frame reconstruction. Metadata retains SI frame/direction,
   source provenance, absent surveyed boundaries and assumed 3 m half-width.
   Numbers are not coerced before hashing. No rounding enters identity.
3. **State and integration review.** Constructed track channels are tuples;
   metadata/frame projections are stored as immutable bytes and decoded to
   fresh dictionaries. The output has no admitted-reference field or runtime
   dispatch. Its status is always unqualified. Data classes are transport
   objects, not authentication tokens; direct construction confers no trust.
   Source-only imports are standard library plus one relative module; the
   initializer imports nothing. No host path or optional dependency fallback
   is present. This claim is based on reading source, not an import run.

The extraction reproduces the historical algorithm as written. Its approximate
cone pairing, floating-point screens and assumed width have not been newly
validated. Reconstructing a source frame is not proof of road clearance, spline
optimality or a dynamically feasible driving line. In particular it does not
replace the archive's missing externally authenticated producer bundle.

## Remaining blockers

- The policy/guidance patch needs actual supported transfer before its source
  can be integrated or its interfaces compared with this explicit contract.
- Package/build/interpreter identity and actual input/frame parity, rejection,
  immutability and isolated-import acceptance remain unrun at Lucas's request.
- Authenticated racing-line admission, the fixed-clock stepping bridge,
  guarded dispatch, complete continuation, verification, replay and export
  are separate unfinished modules. No tournament launch path is added here.
- Historical process-observation/admission restrictions were not retried or
  cleared. No resource probe, lease, vehicle actuation or security change was
  attempted. Original guard/owned-cleanup requirements remain applicable to
  any later authorized execution.

E05 is not complete. There is no new lap, tournament result or winner.
