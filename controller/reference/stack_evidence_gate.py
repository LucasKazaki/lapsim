"""TC-03B8 portable stack-usage evidence gate.

This reference parses GCC .su stack-usage output and combines it with an
explicit, reviewed call-path and stack-region budget. It is synthetic host-side
evidence only; it does not compile or execute Terps Racing firmware.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Iterable

SOURCE_KINDS = {"scenario", "team_verified"}
STACK_KINDS = {"MSP", "PSP"}
QUALIFIERS = {"static", "dynamic", "bounded"}


class StackEvidenceError(ValueError):
    pass


def _text(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StackEvidenceError(f"{path} must be a non-empty string")
    return value.strip()


def _hex(value: object, n: int, path: str) -> str:
    value = _text(value, path).lower()
    if len(value) != n or any(ch not in "0123456789abcdef" for ch in value):
        raise StackEvidenceError(f"{path} must be {n}-hex")
    return value


def _source(value: object, path: str) -> str:
    if value not in SOURCE_KINDS:
        raise StackEvidenceError(f"{path} must be scenario or team_verified")
    return str(value)


def _nonnegative_int(value: object, path: str) -> int:
    if type(value) is not int or value < 0:
        raise StackEvidenceError(f"{path} must be a non-negative integer")
    return value


def _positive_int(value: object, path: str) -> int:
    if type(value) is not int or value <= 0:
        raise StackEvidenceError(f"{path} must be a positive integer")
    return value


@dataclass(frozen=True)
class StackUsageEntry:
    source_location: str
    mangled_name: str
    bytes: int
    qualifiers: tuple[str, ...]

    def validated(self) -> "StackUsageEntry":
        location = _text(self.source_location, "entry.source_location")
        mangled = _text(self.mangled_name, "entry.mangled_name")
        size = _nonnegative_int(self.bytes, "entry.bytes")
        if not isinstance(self.qualifiers, tuple) or not self.qualifiers:
            raise StackEvidenceError("entry.qualifiers must be a non-empty tuple")
        q = tuple(_text(x, "entry.qualifiers[]") for x in self.qualifiers)
        unknown = [x for x in q if x not in QUALIFIERS]
        if unknown:
            raise StackEvidenceError(f"unsupported stack qualifier(s): {unknown}")
        if "static" in q and "dynamic" in q:
            raise StackEvidenceError("entry cannot be both static and dynamic")
        if "bounded" in q and "dynamic" not in q:
            raise StackEvidenceError("bounded qualifier requires dynamic")
        return StackUsageEntry(location, mangled, size, q)

    @property
    def bounded(self) -> bool:
        q = set(self.qualifiers)
        return "static" in q or ("dynamic" in q and "bounded" in q)


def parse_gcc_stack_usage(text: str) -> tuple[StackUsageEntry, ...]:
    """Parse current GCC four-field .su format.

    Fields are tab-separated:
      source-location/function, mangled-name, bytes, qualifier(s)
    """
    if not isinstance(text, str):
        raise StackEvidenceError("stack usage text must be a string")
    entries: list[StackUsageEntry] = []
    seen: set[str] = set()
    for lineno, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        fields = raw.rstrip("\n").split("\t")
        if len(fields) != 4:
            raise StackEvidenceError(
                f"line {lineno}: expected four tab-separated fields, got {len(fields)}"
            )
        location, mangled, byte_text, qualifier_text = fields
        try:
            size = int(byte_text, 10)
        except ValueError as exc:
            raise StackEvidenceError(f"line {lineno}: stack byte count is not decimal") from exc
        qualifiers = tuple(x for x in qualifier_text.replace(",", " ").split() if x)
        entry = StackUsageEntry(location, mangled, size, qualifiers).validated()
        if entry.mangled_name in seen:
            raise StackEvidenceError(
                f"line {lineno}: duplicate mangled function name {entry.mangled_name}"
            )
        seen.add(entry.mangled_name)
        entries.append(entry)
    if not entries:
        raise StackEvidenceError("no stack-usage entries found")
    return tuple(entries)


@dataclass(frozen=True)
class BuildStackReceipt:
    source_commit: str
    artifact_sha256: str
    toolchain: str
    optimization: str
    stack_usage_command: str
    stack_usage_sha256: str
    build_source_kind: str
    artifact_matches_baseline: bool

    def validated(self) -> "BuildStackReceipt":
        return BuildStackReceipt(
            _hex(self.source_commit, 40, "build.source_commit"),
            _hex(self.artifact_sha256, 64, "build.artifact_sha256"),
            _text(self.toolchain, "build.toolchain"),
            _text(self.optimization, "build.optimization"),
            _text(self.stack_usage_command, "build.stack_usage_command"),
            _hex(self.stack_usage_sha256, 64, "build.stack_usage_sha256"),
            _source(self.build_source_kind, "build.build_source_kind"),
            bool(self.artifact_matches_baseline)
            if type(self.artifact_matches_baseline) is bool
            else (_ for _ in ()).throw(
                StackEvidenceError("build.artifact_matches_baseline must be bool")
            ),
        )


@dataclass(frozen=True)
class CallPath:
    name: str
    functions: tuple[str, ...]

    def validated(self) -> "CallPath":
        name = _text(self.name, "call_path.name")
        if not isinstance(self.functions, tuple) or not self.functions:
            raise StackEvidenceError("call_path.functions must be a non-empty tuple")
        functions = tuple(_text(x, "call_path.functions[]") for x in self.functions)
        if len(functions) != len(set(functions)):
            raise StackEvidenceError(
                "call_path contains a repeated function; recursion/cycle must be resolved explicitly"
            )
        return CallPath(name, functions)


@dataclass(frozen=True)
class CallGraphEvidence:
    paths: tuple[CallPath, ...]
    complete_for_control_path: bool
    indirect_calls_resolved: bool
    recursion_absent_or_bounded: bool
    source_kind: str
    source_label: str

    def validated(self) -> "CallGraphEvidence":
        if not isinstance(self.paths, tuple) or not self.paths:
            raise StackEvidenceError("call_graph.paths must be a non-empty tuple")
        paths = tuple(p.validated() for p in self.paths)
        if type(self.complete_for_control_path) is not bool:
            raise StackEvidenceError("call_graph.complete_for_control_path must be bool")
        if type(self.indirect_calls_resolved) is not bool:
            raise StackEvidenceError("call_graph.indirect_calls_resolved must be bool")
        if type(self.recursion_absent_or_bounded) is not bool:
            raise StackEvidenceError("call_graph.recursion_absent_or_bounded must be bool")
        return CallGraphEvidence(
            paths,
            self.complete_for_control_path,
            self.indirect_calls_resolved,
            self.recursion_absent_or_bounded,
            _source(self.source_kind, "call_graph.source_kind"),
            _text(self.source_label, "call_graph.source_label"),
        )


@dataclass(frozen=True)
class StackBudget:
    stack_kind: str
    region_bytes: int
    exception_reserve_bytes: int
    required_margin_bytes: int
    region_source_kind: str
    exception_reserve_source_kind: str
    margin_source_kind: str
    source_label: str

    def validated(self) -> "StackBudget":
        if self.stack_kind not in STACK_KINDS:
            raise StackEvidenceError("stack_kind must be MSP or PSP")
        return StackBudget(
            self.stack_kind,
            _positive_int(self.region_bytes, "budget.region_bytes"),
            _nonnegative_int(
                self.exception_reserve_bytes, "budget.exception_reserve_bytes"
            ),
            _nonnegative_int(
                self.required_margin_bytes, "budget.required_margin_bytes"
            ),
            _source(self.region_source_kind, "budget.region_source_kind"),
            _source(
                self.exception_reserve_source_kind,
                "budget.exception_reserve_source_kind",
            ),
            _source(self.margin_source_kind, "budget.margin_source_kind"),
            _text(self.source_label, "budget.source_label"),
        )


@dataclass(frozen=True)
class WatermarkReceipt:
    stack_kind: str
    observed_peak_bytes: int
    source_kind: str
    source_label: str

    def validated(self) -> "WatermarkReceipt":
        if self.stack_kind not in STACK_KINDS:
            raise StackEvidenceError("watermark.stack_kind must be MSP or PSP")
        return WatermarkReceipt(
            self.stack_kind,
            _nonnegative_int(
                self.observed_peak_bytes, "watermark.observed_peak_bytes"
            ),
            _source(self.source_kind, "watermark.source_kind"),
            _text(self.source_label, "watermark.source_label"),
        )


@dataclass(frozen=True)
class StackGateResult:
    schema: str
    function_entry_count: int
    all_function_entries_bounded: bool
    unbounded_functions: tuple[str, ...]
    call_graph_complete: bool
    call_graph_team_verified: bool
    missing_functions_in_usage: tuple[str, ...]
    maximum_static_path_bytes: int | None
    maximum_static_path_name: str | None
    stack_kind: str
    region_bytes: int
    exception_reserve_bytes: int
    required_margin_bytes: int
    computed_required_bytes: int | None
    computed_headroom_bytes: int | None
    budget_sources_team_verified: bool
    artifact_matches_baseline: bool
    watermark_team_verified: bool | None
    watermark_within_region: bool | None
    ready_for_team_stack_review: bool
    whole_program_stack_proven: bool = False
    worst_case_stack_proven: bool = False
    independent_review_proven: bool = False
    vehicle_acceptance_proven: bool = False
    action_authority: bool = False

    def to_json(self) -> str:
        return json.dumps(
            asdict(self),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )


def evaluate_stack_gate(
    stack_usage_entries: Iterable[StackUsageEntry],
    build: BuildStackReceipt,
    call_graph: CallGraphEvidence,
    budget: StackBudget,
    *,
    watermark: WatermarkReceipt | None = None,
    watermark_required: bool,
    watermark_requirement_source_kind: str,
) -> StackGateResult:
    entries = tuple(x.validated() for x in stack_usage_entries)
    if not entries:
        raise StackEvidenceError("stack_usage_entries must not be empty")
    build = build.validated()
    call_graph = call_graph.validated()
    budget = budget.validated()
    req_kind = _source(
        watermark_requirement_source_kind,
        "watermark_requirement_source_kind",
    )
    if type(watermark_required) is not bool:
        raise StackEvidenceError("watermark_required must be bool")

    by_name = {x.mangled_name: x for x in entries}
    unbounded = tuple(sorted(x.mangled_name for x in entries if not x.bounded))

    graph_complete = (
        call_graph.complete_for_control_path
        and call_graph.indirect_calls_resolved
        and call_graph.recursion_absent_or_bounded
    )
    graph_verified = call_graph.source_kind == "team_verified"

    missing: set[str] = set()
    path_sizes: list[tuple[str, int]] = []
    for path in call_graph.paths:
        total = 0
        for function in path.functions:
            entry = by_name.get(function)
            if entry is None:
                missing.add(function)
            else:
                total += entry.bytes
        if not missing.intersection(path.functions):
            path_sizes.append((path.name, total))

    max_name = None
    max_bytes = None
    if path_sizes:
        max_name, max_bytes = max(path_sizes, key=lambda pair: (pair[1], pair[0]))

    budget_verified = (
        budget.region_source_kind == "team_verified"
        and budget.exception_reserve_source_kind == "team_verified"
        and budget.margin_source_kind == "team_verified"
    )
    computed_required = (
        None
        if max_bytes is None
        else max_bytes
        + budget.exception_reserve_bytes
        + budget.required_margin_bytes
    )
    headroom = (
        None
        if computed_required is None
        else budget.region_bytes - computed_required
    )

    wm_verified = None
    wm_within_region = None
    if watermark is not None:
        watermark = watermark.validated()
        if watermark.stack_kind != budget.stack_kind:
            raise StackEvidenceError(
                "watermark stack_kind must match budget stack_kind"
            )
        wm_verified = watermark.source_kind == "team_verified"
        wm_within_region = watermark.observed_peak_bytes <= budget.region_bytes

    watermark_ok = (
        req_kind == "team_verified"
        and (
            (not watermark_required)
            or (
                watermark is not None
                and wm_verified is True
                and wm_within_region is True
            )
        )
    )

    ready = (
        build.build_source_kind == "team_verified"
        and build.artifact_matches_baseline
        and not unbounded
        and graph_complete
        and graph_verified
        and not missing
        and max_bytes is not None
        and budget_verified
        and computed_required is not None
        and computed_required <= budget.region_bytes
        and watermark_ok
    )

    return StackGateResult(
        schema="enme408-tc03b8-stack-evidence/v1",
        function_entry_count=len(entries),
        all_function_entries_bounded=not unbounded,
        unbounded_functions=unbounded,
        call_graph_complete=graph_complete,
        call_graph_team_verified=graph_verified,
        missing_functions_in_usage=tuple(sorted(missing)),
        maximum_static_path_bytes=max_bytes,
        maximum_static_path_name=max_name,
        stack_kind=budget.stack_kind,
        region_bytes=budget.region_bytes,
        exception_reserve_bytes=budget.exception_reserve_bytes,
        required_margin_bytes=budget.required_margin_bytes,
        computed_required_bytes=computed_required,
        computed_headroom_bytes=headroom,
        budget_sources_team_verified=budget_verified,
        artifact_matches_baseline=build.artifact_matches_baseline,
        watermark_team_verified=wm_verified,
        watermark_within_region=wm_within_region,
        ready_for_team_stack_review=ready,
    )
