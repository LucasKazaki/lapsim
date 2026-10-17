"""Control CLI evidence survives interrupted writes and bounded input reads."""

import io
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from lapsim.experiments import closed_loop, control_study


@pytest.fixture(params=(closed_loop, control_study), ids=("closed_loop", "control_study"))
def cli(request, monkeypatch):
    module = request.param
    run_name = "run_closed_loop" if module is closed_loop else "run_control_comparison"
    monkeypatch.setattr(module, run_name, lambda *args, **kwargs: {"result": "complete"})
    return module


@pytest.mark.parametrize("failure", ("partial_write", "replace"))
def test_cli_failed_output_preserves_existing_evidence(
    cli, tmp_path, monkeypatch, capsys, failure
):
    target = tmp_path / "saved.json"
    target.write_bytes(b"original verified evidence\n")
    before = target.read_bytes(), target.stat().st_mtime_ns
    original_write = Path.write_text

    def interrupted_write(path, text, **kwargs):
        original_write(path, text[:7], **kwargs)
        raise OSError("simulated full disk after partial write")

    def failed_replace(*args):
        raise OSError("simulated replace failure")

    if failure == "partial_write":
        monkeypatch.setattr(Path, "write_text", interrupted_write)
    else:
        monkeypatch.setattr(os, "replace", failed_replace)
    monkeypatch.setattr(sys, "argv", [cli.__name__, "--output", str(target)])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    message = capsys.readouterr().err
    assert "simulated" in message and "Traceback" not in message
    assert (target.read_bytes(), target.stat().st_mtime_ns) == before
    assert list(tmp_path.iterdir()) == [target]


def test_cli_success_keeps_serialization_and_replaces_output(cli, tmp_path, monkeypatch):
    target = tmp_path / "saved.json"
    target.write_bytes(b"prior evidence")
    monkeypatch.setattr(sys, "argv", [cli.__name__, "--output", str(target)])
    assert cli.main() == 0
    assert target.read_bytes() == ('{"result":"complete"}' + os.linesep).encode()
    assert list(tmp_path.iterdir()) == [target]


def test_cli_bounds_actual_read_after_file_metadata_changes(
    cli, tmp_path, monkeypatch
):
    source = tmp_path / "saved.json"
    source.write_bytes(b"{}")
    requested = []
    original_open = Path.open

    class ChangedFile(io.BytesIO):
        def read(self, size=-1):
            requested.append(size)
            return super().read(size)

    def changed_open(path, *args, **kwargs):
        if path == source:
            return ChangedFile(b"{invalid")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", changed_open)
    monkeypatch.setattr(sys, "argv", [cli.__name__, "--replay", str(source)])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    limit = 20_000_000 if cli is closed_loop else 40_000_000
    assert requested == [limit + 1]


@pytest.mark.parametrize("alias", ("same_path", "hard_link"))
def test_cli_replay_refuses_input_output_aliases(
    cli, tmp_path, monkeypatch, capsys, alias
):
    source = tmp_path / "saved.json"
    source.write_bytes(b"preserved replay evidence")
    target = source if alias == "same_path" else tmp_path / "alias.json"
    if alias == "hard_link":
        os.link(source, target)
    before = source.read_bytes(), source.stat().st_mtime_ns
    monkeypatch.setattr(
        sys,
        "argv",
        [cli.__name__, "--replay", str(source), "--output", str(target)],
    )
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    assert "output must not overwrite input" in capsys.readouterr().err
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before
    assert target.read_bytes() == before[0]


def test_bounded_reader_rejects_overflow_and_accepts_exact_byte_limit(tmp_path):
    from lapsim.experiments.record_io import read_json_bounded

    source = tmp_path / "record.json"
    encoded = b'{"value":1}'
    source.write_bytes(encoded)
    assert read_json_bounded(source, maximum_bytes=len(encoded)) == {"value": 1}
    source.write_bytes(encoded + b" ")
    with pytest.raises(ValueError, match="size limit"):
        read_json_bounded(source, maximum_bytes=len(encoded))


def test_concurrent_writers_have_distinct_temporaries_and_complete_results(
    tmp_path, monkeypatch
):
    from lapsim.experiments.record_io import write_text_atomic

    target = tmp_path / "record.json"
    original_write = Path.write_text
    barrier = Barrier(2)
    temporaries = []
    texts = ('{"run":"A"}\n', '{"run":"B"}\n')

    def overlapping_write(path, text, **kwargs):
        temporaries.append(path)
        result = original_write(path, text, **kwargs)
        barrier.wait(timeout=5)
        return result

    monkeypatch.setattr(Path, "write_text", overlapping_write)
    with ThreadPoolExecutor(max_workers=2) as executor:
        tasks = [executor.submit(write_text_atomic, target, text) for text in texts]
        errors = [task.exception(timeout=10) for task in tasks]
    # Windows may refuse one overlapping replacement. That writer must fail
    # cleanly while retaining a complete winner and cleaning only its own temp.
    assert any(error is None for error in errors)
    assert all(error is None or isinstance(error, OSError) for error in errors)
    assert len(set(temporaries)) == 2
    assert all(path.parent == target.parent and path != target for path in temporaries)
    assert target.read_text(encoding="utf-8") in texts
    assert json.loads(target.read_text(encoding="utf-8"))["run"] in ("A", "B")
    assert list(tmp_path.iterdir()) == [target]
