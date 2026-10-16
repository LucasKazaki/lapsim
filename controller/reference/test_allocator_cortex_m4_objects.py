"""Software-only annex checks. Real subprocess/toolchain execution is forbidden."""
from contextlib import contextmanager
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile

import allocator_cortex_m4_objects as annex


def symbol_text():
    return "\n".join("Symbol {\n Name: " + name + " (1)\n Binding: Global (0x1)\n"
                     " Type: Function (0x2)\n Section: .text." + name + " (1)\n}"
                     for name in annex.PUBLIC)


def disassembly_text(group="00 bf"):
    return "\n".join("00000000 <" + name + ">:\n       0: " + group + " nop" for name in annex.PUBLIC)


class AllocatorObjectTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="allocator-object-software-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        patch = mock.patch.object(annex.subprocess, "run", side_effect=AssertionError("ARM/tools forbidden"))
        self.forbidden = patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self.forbidden.assert_not_called)

    def test_frozen_protocol_sources_baseline_and_public_raw_object_policy(self):
        plan = annex.load_protocol()
        self.assertEqual(plan["base_commit"], "17715fc698a4bc7b3a7807d0d6f869045fdab5a4")
        self.assertEqual(plan["source_review_checkpoint"]["pr"], 76)
        self.assertEqual(set(annex.source_facts(annex.REFERENCE / "native", plan)), set(annex.SOURCES))
        self.assertEqual(len(annex.load_baseline(plan)["historical_attempts"]), 2)
        self.assertIn("public raw", plan["publication_policy"]["generated_objects"])
        self.assertIn("remain local", plan["publication_policy"]["toolchain"])

    def test_changed_protocol_helper_and_source_rejected_before_execution(self):
        changed = self.root / "plan.json"
        changed.write_bytes(annex.PROTOCOL.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "frozen allocator object protocol"):
            annex.load_protocol(changed)
        plan = annex.load_protocol()
        plan["shared_helper"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "shared helper changed"):
            annex.load_shared(plan)
        for name in annex.SOURCES:
            shutil.copyfile(annex.REFERENCE / "native" / name, self.root / name)
        (self.root / "torque_allocator.c").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "source changed"):
            annex.source_facts(self.root, plan)

    def test_changed_baseline_does_not_rebase_old_artifacts(self):
        plan = annex.load_protocol()
        plan["frozen_research_baseline"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "historical baseline"):
            annex.load_baseline(plan)
        path = self.root / "old-receipt.json"
        path.write_bytes(b"original")
        base = {"historical_anchors": [{"path": str(path), "bytes": 8, "sha256": annex.digest(path)}],
                "historical_attempts": []}
        annex.historical_facts(base)
        path.write_bytes(b"modified")
        with self.assertRaisesRegex(ValueError, "historical anchor"):
            annex.historical_facts(base)

    def test_historical_directory_addition_and_changed_file_are_rejected(self):
        old = self.root / "old"
        old.mkdir()
        path = old / "receipt.json"
        path.write_bytes(b"original")
        files = [{"path": "receipt.json", "bytes": 8, "sha256": annex.digest(path)}]
        base = {"historical_anchors": [], "historical_attempts": [{"root": str(old), "files": files}]}
        annex.historical_facts(base)
        (old / "extra").write_bytes(b"new")
        with self.assertRaisesRegex(ValueError, "historical attempt"):
            annex.historical_facts(base)
        (old / "extra").unlink()
        path.write_bytes(b"modified")
        with self.assertRaisesRegex(ValueError, "historical attempt"):
            annex.historical_facts(base)

    def test_exact31_command_schedule_and_four_row_order(self):
        plan = annex.load_protocol()
        slots, rows = annex.schedule(plan, self.root / "tools", self.root / "new")
        self.assertEqual(len(slots), 31)
        self.assertEqual([(r["repeat"], r["abi"]) for r in rows], [(1, "hard"), (1, "softfp"), (2, "hard"), (2, "softfp")])
        self.assertEqual([r["compile_slot"] for r in rows], [7, 13, 19, 25])
        self.assertEqual([Path(r["argv"][0]).name for r in slots[:5]], list(annex.TOOLS))
        self.assertTrue(all(r["status"] == "not_run" for r in slots))
        self.assertEqual(sum("-c" in r["argv"] for r in slots), 4)
        for row in rows:
            last = slots[row["inspection_slots"][-1]]["argv"]
            self.assertIn("--no-debuginfod", last)
            self.assertIn("--triple=thumbv7em-none-eabi", last)
            self.assertIn("--mcpu=cortex-m4", last)
            self.assertIn("--reloc", last)
            self.assertNotIn("--source", last)

    def test_command_plan_and_flags_cannot_be_extended_or_reordered(self):
        plan = annex.load_protocol()
        flags = plan["compile_common_flags"]
        variants = [flags[:i] + flags[i+1:] for i in range(len(flags))]
        variants += [list(reversed(flags)), flags + ["-shared"], flags + ["-ffast-math"], flags + ["--config=Omax.cfg"]]
        for changed in variants:
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, "exact frozen"):
                annex.compile_args(Path("clang.exe"), changed, "hard", "torque_allocator", self.root / "a.o")
        for abi, unit in (("soft", "torque_allocator"), ("hard", "torque_guard"), ("hard", "../../unit")):
            with self.subTest(abi=abi, unit=unit), self.assertRaises(ValueError):
                annex.compile_args(Path("clang.exe"), flags, abi, unit, self.root / "a.o")
        plan["version_commands_in_order"].append(["link.exe", "--version"])
        with self.assertRaisesRegex(ValueError, "exact frozen command plan"):
            annex.schedule(plan, self.root, self.root / "a")

    def test_output_rejects_existing_overlap_alias_and_retained_descendant(self):
        protected = self.root / "protected"
        protected.mkdir()
        (protected / "nested").mkdir()
        for target in (protected, self.root, protected / "new", protected / "nested/../new"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                annex.attempt_path(target, [protected])
        (self.root / "receipt.json").write_text("preserve")
        with self.assertRaisesRegex(ValueError, "outside retained"):
            annex.attempt_path(self.root / "new", [])
        self.assertEqual((self.root / "receipt.json").read_text(), "preserve")

    def tiny_tools(self):
        root = self.root / "toolchain"
        (root / "bin").mkdir(parents=True)
        pins = {}
        archive = self.root / "tools.zip"
        with zipfile.ZipFile(archive, "w") as z:
            for tool in annex.TOOLS:
                raw = ("FAKE NONEXECUTABLE " + tool).encode()
                z.writestr("toolchain/bin/" + tool, raw)
                path = root / "bin" / tool
                path.write_bytes(raw)
                pins[tool] = {"path": "bin/" + tool, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        manifest = self.root / "manifest.jsonl"
        manifest.write_text("".join(json.dumps(row) + "\n" for row in pins.values()))
        verification = {"manifest_sha256": annex.digest(manifest), "verified_file_count": 48211,
            "tools": {name: {"path": str(root / "bin" / name), "sha256": pins[name]["sha256"]} for name in annex.TOOLS[:-1]}}
        plan = annex.load_protocol()
        plan["toolchain"]["five_proposed_tool_pins"] = pins
        return root, archive, manifest, verification, plan

    def test_fifth_tool_is_bound_to_fresh_manifest_actual_file_and_zip_without_mutating_helper_tools(self):
        root, archive, manifest, verification, plan = self.tiny_tools()
        shared = annex.load_shared(plan)
        before = shared.TOOLS
        tools = annex.verify_five_tools(archive, root, plan, verification, manifest)
        self.assertEqual(set(tools), set(annex.TOOLS))
        self.assertEqual(shared.TOOLS, before)
        self.assertNotIn("llvm-objdump.exe", shared.TOOLS)
        (root / "bin/llvm-objdump.exe").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "unverified tool"):
            annex.verify_five_tools(archive, root, plan, verification, manifest)

    def test_missing_duplicate_or_stale_manifest_and_wrong_original_identity_rejected(self):
        root, archive, manifest, verification, plan = self.tiny_tools()
        original = manifest.read_bytes()
        manifest.write_bytes(original + original.splitlines()[0] + b"\n")
        with self.assertRaisesRegex(ValueError, "manifest mismatch"):
            annex.verify_five_tools(archive, root, plan, verification, manifest)
        verification["manifest_sha256"] = annex.digest(manifest)
        with self.assertRaisesRegex(ValueError, "duplicate selected"):
            annex.verify_five_tools(archive, root, plan, verification, manifest)
        manifest.write_bytes(b"\n".join(original.splitlines()[:-1]) + b"\n")
        verification["manifest_sha256"] = annex.digest(manifest)
        with self.assertRaisesRegex(ValueError, "missing selected"):
            annex.verify_five_tools(archive, root, plan, verification, manifest)
        manifest.write_bytes(original)
        verification["manifest_sha256"] = annex.digest(manifest)
        verification["tools"]["clang.exe"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "original tool identity"):
            annex.verify_five_tools(archive, root, plan, verification, manifest)

    def test_fifth_zip_member_must_match_even_if_manifest_and_local_file_agree(self):
        root, archive, manifest, verification, plan = self.tiny_tools()
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("toolchain/bin/llvm-objdump.exe", b"different")
        with self.assertRaisesRegex(ValueError, "fifth tool ZIP member mismatch"):
            annex.verify_five_tools(archive, root, plan, verification, manifest)

    def test_disassembly_requires_all_functions_instruction_bytes_and_no_unknown(self):
        for grouping in ("00 bf", "bf00", "f04f 0000", "e12fff1e"):
            self.assertEqual(annex.disassembly_facts(disassembly_text(grouping))["public_labels"], list(annex.PUBLIC))
        for text in ("", disassembly_text() + "\n <unknown>", disassembly_text().replace(annex.PUBLIC[0], "missing"),
                     "\n".join("<" + name + ">:" for name in annex.PUBLIC)):
            with self.subTest(text=text), self.assertRaises(ValueError):
                annex.disassembly_facts(text)

    def test_public_symbols_must_be_defined_global_functions(self):
        self.assertEqual(annex.public_symbols(symbol_text()), list(annex.PUBLIC))
        for text in (symbol_text().replace("Global", "Local", 1), symbol_text().replace("Function", "Object", 1),
                     symbol_text().replace("Section: .text", "Section: Undefined", 1), symbol_text() + symbol_text(), ""):
            with self.subTest(text=text), self.assertRaises(ValueError):
                annex.public_symbols(text)

    def test_size_total_cannot_hide_missing_or_negative_fields(self):
        self.assertEqual(annex.berkeley_size("text data bss dec\n 5 2 3 10 0xa fake.o"), {"text": 5, "data": 2, "bss": 3, "total": 10})
        for text in ("5 2 3 9", "5 -2 3 6", "5 2", "no size"):
            with self.subTest(text=text), self.assertRaises((ValueError, IndexError)):
                annex.berkeley_size(text)

    def test_dependency_cannot_drift_from_verified_manifest(self):
        snapshot, toolchain = self.root / "native", self.root / "toolchain"
        snapshot.mkdir()
        toolchain.mkdir()
        (snapshot / "unit.c").write_bytes(b"source")
        path = toolchain / "math.h"
        path.write_bytes(b"header")
        manifest = self.root / "files.jsonl"
        manifest.write_text(json.dumps({"path": "math.h", "sha256": annex.digest(path), "bytes": 6}) + "\n")
        deps = [{"owner": "native_snapshot", "path": "unit.c", "sha256": annex.digest(snapshot / "unit.c")},
                {"owner": "verified_toolchain", "path": "math.h", "sha256": annex.digest(path)}]
        annex.verify_dependencies(deps, manifest, snapshot, toolchain)
        path.write_bytes(b"different")
        deps[1]["sha256"] = annex.digest(path)
        with self.assertRaisesRegex(ValueError, "differs from fresh"):
            annex.verify_dependencies(deps, manifest, snapshot, toolchain)

    def recorder(self):
        output = self.root / "recorder"
        output.mkdir()
        (output / "logs").mkdir()
        entry = {"slot": 0, "label": "fake-only", "status": "not_run", "argv": ["NEVER EXECUTE"], "cwd": str(output)}
        receipt = {"command_slots": [entry], "commands": []}
        return annex.Recorder(output, receipt, annex.load_shared(annex.load_protocol()), {}), receipt

    def test_recorder_logs_before_fake_call_and_preserves_actual_nonzero_exit(self):
        recorder, receipt = self.recorder()
        def fake(argv, **options):
            stored = json.loads((recorder.output / "receipt.json").read_text())
            self.assertEqual(stored["command_slots"][0]["status"], "prepared")
            self.assertEqual(stored["actual_commands"], 0)
            self.assertEqual(stored["uncertain_command_slots"], [0])
            self.assertEqual(options["timeout"], 60)
            return SimpleNamespace(returncode=17, stdout=b"partial\x00output", stderr=b"failed")
        with mock.patch.object(annex.subprocess, "run", side_effect=fake) as call:
            self.assertEqual(recorder.run(0), (17, "partial\x00output"))
        self.assertEqual(call.call_count, 1)
        self.assertEqual(receipt["commands"][0]["exit_code"], 17)
        self.assertEqual(receipt["actual_commands"], 1)
        self.assertEqual(receipt["prepared_commands"], 1)
        self.assertEqual(receipt["uncertain_command_slots"], [])
        self.assertEqual((recorder.output / receipt["commands"][0]["stdout"]).read_bytes(), b"partial\x00output")
        with self.assertRaisesRegex(ValueError, "already used"):
            recorder.run(0)

    def test_recorder_retains_owned_run_timeout_or_launch_error_and_partial_bytes(self):
        recorder, receipt = self.recorder()
        error = subprocess.TimeoutExpired(["NEVER EXECUTE"], 60, output=b"partial", stderr=b"timeout")
        with mock.patch.object(annex.subprocess, "run", side_effect=error):
            with self.assertRaises(subprocess.TimeoutExpired):
                recorder.run(0)
        self.assertEqual(receipt["commands"][0]["status"], "launch_or_timeout_error")
        self.assertEqual((recorder.output / receipt["commands"][0]["stdout"]).read_bytes(), b"partial")

    def test_pre_call_persistence_failure_is_prepared_but_never_an_actual_request(self):
        recorder, receipt = self.recorder()
        with mock.patch.object(recorder.shared, "save", side_effect=PermissionError("before call")):
            with self.assertRaises(PermissionError):
                recorder.run(0)
        self.assertEqual(len(receipt["commands"]), 1)
        self.assertEqual(receipt["prepared_commands"], 1)
        self.assertEqual(receipt["actual_commands"], 0)
        self.assertEqual(receipt["uncertain_command_slots"], [])
        self.assertEqual(receipt["not_run_command_slots"], [0])
        self.assertEqual(receipt["commands"][0]["status"], "not_launched_artifact_error")
        self.assertEqual(receipt["artifact_errors"][0]["stage"], "before_launch_receipt")

    def test_known_return_survives_output_write_failure_without_claiming_output_file(self):
        recorder, receipt = self.recorder()
        returned = SimpleNamespace(returncode=17, stdout=b"known stdout", stderr=b"known stderr")
        with mock.patch.object(annex.subprocess, "run", return_value=returned), \
             mock.patch.object(Path, "write_bytes", side_effect=PermissionError("stdout storage blocked")):
            with self.assertRaises(PermissionError):
                recorder.run(0)
        entry = receipt["commands"][0]
        self.assertEqual((entry["status"], entry["exit_code"], entry["launch_state"]), ("completed", 17, "confirmed_return"))
        self.assertEqual(receipt["actual_commands"], 1)
        self.assertEqual(entry["stdout_observed_sha256"], hashlib.sha256(b"known stdout").hexdigest())
        self.assertEqual(entry["stderr_observed_sha256"], hashlib.sha256(b"known stderr").hexdigest())
        self.assertNotIn("stdout", entry)
        self.assertEqual(entry["artifact_status"], "failed_retained")
        self.assertEqual(entry["artifact_errors"][0]["stage"], "stdout_artifact")

    def test_interruption_retains_uncertainty_instead_of_claiming_a_known_launch_count(self):
        recorder, receipt = self.recorder()
        with mock.patch.object(annex.subprocess, "run", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                recorder.run(0)
        entry = receipt["commands"][0]
        self.assertEqual(entry["status"], "interrupted_unconfirmed")
        self.assertEqual(receipt["actual_commands"], 0)
        self.assertEqual(receipt["uncertain_command_slots"], [0])
        self.assertTrue(receipt["actual_commands_is_confirmed_lower_bound"])
        self.assertEqual(json.loads((recorder.output / "receipt.json").read_text())["uncertain_command_slots"], [0])

    @contextmanager
    def fake_build(self, fail=None, mutate=None):
        """Synthetic files/returns only; does not validate a real ARM object or toolchain."""
        tools = self.root / "fake-tools"
        (tools / "bin").mkdir(parents=True, exist_ok=True)
        identities = {}
        for tool in annex.TOOLS:
            path = tools / "bin" / tool
            path.write_bytes(b"NOT EXECUTABLE")
            identities[tool] = {"path": str(path), "bytes": 14, "sha256": annex.digest(path)}
        shared = annex.load_shared(annex.load_protocol())
        events = []
        def verify(*args):
            events.append("full-verification-FAKE")
            args[3].write_text("")
            return {"manifest_sha256": annex.digest(args[3]), "verified_file_count": 48211}
        def fifth(*args):
            events.append("five-identities-FAKE")
            if fail == "fifth":
                raise ValueError("unverified fifth tool")
            if mutate is not None:
                mutate(args[-1].parent)
            return identities
        def fake_run(argv, **kwargs):
            self.assertEqual(events[:2], ["full-verification-FAKE", "five-identities-FAKE"])
            self.assertNotIn("DEBUGINFOD_URLS", kwargs["env"])
            events.append("fake-call")
            text, code = "", 0
            name = Path(argv[0]).name
            if fail == "preflight" and argv[1:] == ["--version"]:
                code = 17
            elif "-c" in argv:
                obj = Path(argv[-1])
                if fail == "compile" and obj.parts[-3:-1] == ("repeat-1", "hard"):
                    code = 7
                else:
                    obj.write_bytes(b"FAKE OBJECT NEVER EXECUTED")
                    obj.with_suffix(".d").write_text("fake.o: torque_allocator.c torque_allocator.h torque_contract.h\n")
                    obj.with_suffix(".su").write_text("torque_allocator.c:1:tc_allocate_propulsive_torque\t80\tstatic\n")
            elif name == "llvm-readobj.exe" and "--version" not in argv:
                if fail == "inspection" and "repeat-1" in argv[-1] and "hard" == Path(argv[-1]).parent.name:
                    code = 3
                text = symbol_text()
            elif "--format=berkeley" in argv:
                text = "text data bss dec hex file\n1 0 0 1 1 fake.o\n"
            elif "--format=sysv" in argv:
                text = "FAKE section report\n"
            elif name == "llvm-objdump.exe" and "--version" not in argv:
                text = disassembly_text()
                if fail == "metadata" and "repeat-1" in argv[-1] and "hard" == Path(argv[-1]).parent.name:
                    text += "\n<unknown>"
            return SimpleNamespace(returncode=code, stdout=text.encode(), stderr=b"")
        with mock.patch.object(shared, "verify_toolchain", side_effect=verify), \
             mock.patch.object(shared, "read_elf", return_value={"arm_attribute_tags": {6:13, 7:77, 9:2, 10:6, 27:1}}), \
             mock.patch.object(shared, "validate_abi"), \
             mock.patch.object(annex, "historical_facts", return_value={"FAKE": "unchanged"}), \
             mock.patch.object(annex, "load_shared", return_value=shared), \
             mock.patch.object(annex, "verify_five_tools", side_effect=fifth), \
             mock.patch.object(annex.subprocess, "run", side_effect=fake_run) as calls:
            yield tools, calls, events

    def test_synthetic_success_records31_calls_and_four_rows_without_real_tool_execution(self):
        with self.fake_build() as (tools, calls, events):
            receipt = annex.build(tools, self.root / "FAKE-archive", self.root / "attempt")
        self.assertEqual(receipt["status"], "passed", receipt)
        self.assertEqual(calls.call_count, 31)
        self.assertEqual(receipt["actual_commands"], 31)
        self.assertEqual(receipt["not_run_command_slots"], [])
        self.assertEqual(receipt["metadata_status"], "passed")
        self.assertTrue(all(row["status"] == "inspected" for row in receipt["objects"]))
        self.assertEqual(receipt["independent_artifact_review"], "pending_separate_receipt")
        self.assertEqual(len(events), 33)

    def test_fifth_identity_failure_leaves_all31_slots_and_four_rows_not_run(self):
        with self.fake_build("fifth") as (tools, calls, _):
            receipt = annex.build(tools, self.root / "FAKE-archive", self.root / "attempt")
        self.assertEqual(calls.call_count, 0)
        self.assertEqual(receipt["status"], "failed_retained")
        self.assertEqual(receipt["not_run_command_slots"], list(range(31)))
        self.assertTrue(all(row["status"] == "not_run" for row in receipt["objects"]))

    def test_snapshot_or_retained_copy_drift_during_verification_rejects_before_any_call(self):
        names = ("native/torque_allocator.c", "native/torque_allocator.h", "native/torque_contract.h", "protocol.json",
                 "executed-allocator_cortex_m4_objects.py", "executed-shared-helper.py", "historical-baseline.json")
        for index, name in enumerate(names):
            def mutate(output):
                (output / name).write_bytes((output / name).read_bytes() + b"changed during verification")
            with self.subTest(name=name), self.fake_build(mutate=mutate) as (tools, calls, _):
                receipt = annex.build(tools, self.root / "FAKE-archive", self.root / ("drift-attempt-" + str(index)))
            self.assertEqual(calls.call_count, 0)
            self.assertEqual(receipt["status"], "failed_retained")
            self.assertEqual(receipt["actual_commands"], 0)
            self.assertEqual(receipt["not_run_command_slots"], list(range(31)))

    def test_build_pre_call_save_failure_retains_zero_actual_requests_and_all_not_run(self):
        with self.fake_build() as (tools, calls, _):
            shared = annex.load_shared(annex.load_protocol())
            save = shared.save
            def fail_pre_call(path, value):
                if value["commands"] and value["commands"][0]["status"] == "prepared":
                    raise PermissionError("pre-call receipt unavailable")
                save(path, value)
            with mock.patch.object(shared, "save", side_effect=fail_pre_call):
                receipt = annex.build(tools, self.root / "FAKE-archive", self.root / "attempt")
        self.assertEqual(calls.call_count, 0)
        self.assertEqual(receipt["actual_commands"], 0)
        self.assertEqual(receipt["prepared_commands"], 1)
        self.assertEqual(receipt["tool_status"], "not_run")
        self.assertEqual(receipt["not_run_command_slots"], list(range(31)))
        disk = json.loads((self.root / "attempt/receipt.json").read_text())
        self.assertEqual(disk["actual_commands"], 0)

    def test_known_return_and_log_failure_are_persisted_separately_by_build(self):
        with self.fake_build("preflight") as (tools, calls, _):
            write = Path.write_bytes
            def fail_logs(path, raw):
                if path.parent.name == "logs":
                    raise PermissionError("known return but log unavailable")
                return write(path, raw)
            with mock.patch.object(Path, "write_bytes", autospec=True, side_effect=fail_logs):
                receipt = annex.build(tools, self.root / "FAKE-archive", self.root / "attempt")
        self.assertEqual(calls.call_count, 1)
        self.assertEqual(receipt["actual_commands"], 1)
        self.assertEqual(receipt["commands"][0]["exit_code"], 17)
        self.assertEqual(receipt["commands"][0]["status"], "completed")
        self.assertEqual(receipt["artifact_errors"][0]["stage"], "stdout_artifact")
        disk = json.loads((self.root / "attempt/receipt.json").read_text())
        self.assertEqual(disk["commands"][0]["exit_code"], 17)

    def test_known_return_survives_persistent_receipt_failure_in_structured_stderr(self):
        stderr = io.StringIO()
        with self.fake_build("preflight") as (tools, calls, _):
            shared = annex.load_shared(annex.load_protocol())
            save = shared.save
            def fail_after_return(path, value):
                if value["commands"] and "exit_code" in value["commands"][0]:
                    raise PermissionError("all post-return receipts unavailable")
                save(path, value)
            with mock.patch.object(shared, "save", side_effect=fail_after_return), mock.patch.object(annex.sys, "stderr", stderr):
                receipt = annex.build(tools, self.root / "FAKE-archive", self.root / "attempt")
        self.assertEqual(calls.call_count, 1)
        self.assertFalse(receipt["final_receipt_persisted"])
        self.assertEqual(receipt["status"], "failed_retained")
        fallback = json.loads(stderr.getvalue())
        self.assertEqual(fallback["event"], "allocator_annex_receipt_write_failed")
        self.assertEqual(fallback["receipt"]["commands"][0]["exit_code"], 17)
        self.assertEqual(fallback["receipt"]["actual_commands"], 1)
        self.assertEqual([x["stage"] for x in receipt["artifact_errors"]], ["after_return_receipt", "final_receipt"])

    def test_preflight_failure_does_not_claim_unrun_rows_or_hide_denominator(self):
        with self.fake_build("preflight") as (tools, calls, _):
            receipt = annex.build(tools, self.root / "FAKE-archive", self.root / "attempt")
        self.assertEqual(calls.call_count, 1)
        self.assertEqual(receipt["planned_commands"], 31)
        self.assertEqual(receipt["not_run_command_slots"], list(range(1, 31)))
        self.assertEqual(receipt["tool_status"], "failed_or_not_completed")
        self.assertTrue(all(row["status"] == "not_run" for row in receipt["objects"]))

    def test_compile_failure_preserves_row_and_skips_only_its_inspections(self):
        with self.fake_build("compile") as (tools, calls, _):
            receipt = annex.build(tools, self.root / "FAKE-archive", self.root / "attempt")
        self.assertEqual(calls.call_count, 26)
        self.assertEqual(receipt["not_run_command_slots"], [8, 9, 10, 11, 12])
        self.assertEqual(receipt["objects"][0]["status"], "compile_error")
        self.assertTrue(all(row["status"] == "inspected" for row in receipt["objects"][1:]))
        self.assertEqual(receipt["status"], "failed_retained")

    def test_inspection_failure_preserves_unrun_slots_and_continues_other_rows(self):
        with self.fake_build("inspection") as (tools, calls, _):
            receipt = annex.build(tools, self.root / "FAKE-archive", self.root / "attempt")
        self.assertEqual(calls.call_count, 27)
        self.assertEqual(receipt["not_run_command_slots"], [9, 10, 11, 12])
        self.assertEqual(receipt["objects"][0]["status"], "inspection_error")
        self.assertTrue(all(row["status"] == "inspected" for row in receipt["objects"][1:]))

    def test_metadata_failure_is_separate_from_successful_tool_exit_status(self):
        with self.fake_build("metadata") as (tools, calls, _):
            receipt = annex.build(tools, self.root / "FAKE-archive", self.root / "attempt")
        self.assertEqual(calls.call_count, 31)
        self.assertEqual(receipt["tool_status"], "passed")
        self.assertEqual(receipt["metadata_status"], "failed_retained")
        self.assertEqual(receipt["objects"][0]["status"], "metadata_error")
        self.assertEqual(receipt["status"], "failed_retained")


if __name__ == "__main__":
    unittest.main()
