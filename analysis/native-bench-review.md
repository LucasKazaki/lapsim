# Open a compiled C replay in the bench viewer

The viewer can present the separately generated ENME408 native host replay. The committed `web/examples/enme408-native-c-replay.json` is the exact 18-cycle synthetic receipt produced by the five compiled C owners and compared with the unchanged Python reference. Its title and provenance identify that source; it is not a measured vehicle capture.

To embed that receipt in one local HTML file:

```text
python scripts/export_bench_viewer.py --receipt web/examples/enme408-native-c-replay.json --output NEW_REVIEW_HTML
```

Open the HTML and select **Load embedded replay**. The example contains 9 allowed commands, 9 held commands and 5 recovery cycles. Arrow keys select individual cycles; fault-table buttons select their matching event. The paired immutable native run and its exact source/build hashes belong to the Studio evidence bundle. The receipt binds that run's SHA-256, and a separate bundle manifest binds the exported HTML.

`--receipt` accepts a supplied strict finite JSON file. Duplicate keys, nonfinite constants, malformed encodings, excessive size and output paths that alias a source or the supplied input are rejected before output writes. The embedded data uses ASCII JSON and escapes `<`; label/provenance text remains data. The actual shipped JavaScript remains responsible for receipt/gate consistency checks when loaded.

The default export still uses the original Python synthetic example. Existing viewer policy, chart calculations, styles, accessibility controls and all simulation physics are unchanged. Generic embedded-file wording also works for custom receipts with a different cycle count.

The viewer is a presentation tool. It does not authenticate source claims, rerun C, send commands or connect to a target. Native reproduction requires the matching recorded controller source and host compiler from the paired run. Independent review, local browser evidence and final CI status accompany the review candidate.
