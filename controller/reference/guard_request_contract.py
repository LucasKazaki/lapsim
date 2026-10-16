"""Compatibility names for callers of the former TC-02BS request adapter.

The shared boundary now lives in allocation_contract and the base guard enforces
it directly. There is no second policy to drift out of sync.
"""
from allocator import AllocationResult
from allocation_contract import allocation_contract_fault
from command_guard import (CommandGuardConfig, CommandGuardInput,
                           CommandGuardResult, CommandGuardState, apply_command_guard)


def request_contract_fault(candidate: object) -> str | None:
    return allocation_contract_fault(candidate)


def apply_request_checked_guard(candidate: AllocationResult, inp: CommandGuardInput,
                                cfg: CommandGuardConfig,
                                state: CommandGuardState) -> CommandGuardResult:
    return apply_command_guard(candidate, inp, cfg, state)
