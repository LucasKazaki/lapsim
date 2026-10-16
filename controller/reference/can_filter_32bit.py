"""TC-03B24 portable bxCAN 32-bit acceptance-filter geometry.

Synthetic/offline reference only.

RM0090 describes the 32-bit comparison word as:
    STID[10:0] | EXID[17:0] | IDE | RTR | 0

For a standard frame, the 11-bit identifier occupies bits 31:21, IDE=0, and
EXID bits are zero. For an extended frame, the 29-bit identifier occupies bits
31:3 and IDE=1. RTR is bit 1. Bit 0 is reserved/zero.

This module models only one 32-bit filter-bank comparison:
- identifier-mask mode: (frame & mask) == (filter_id & mask)
- identifier-list mode: frame == FR1 or frame == FR2

It does not model:
- 16-bit filters;
- bank activation/priority/FMI numbering;
- FIFO assignment;
- CAN1/CAN2 shared-bank ownership;
- actual Terps Racing identifiers or payloads;
- CAN timing, freshness, torque commands, or vehicle authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json

STD_ID_MAX = 0x7FF
EXT_ID_MAX = 0x1FFFFFFF
U16_MAX = 0xFFFF
U32_MAX = 0xFFFFFFFF

IDE_BIT = 1 << 2
RTR_BIT = 1 << 1
RESERVED_BIT = 1 << 0
STD_ID_SHIFT = 21
EXT_ID_SHIFT = 3

MODE_MASK = "mask"
MODE_LIST = "list"
SOURCE_KINDS = {"scenario", "team_verified"}


class CanFilter32Error(ValueError):
    pass


def _strict_bool(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise CanFilter32Error(f"{name} must be boolean")
    return value


def _uint(value: object, maximum: int, name: str) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise CanFilter32Error(f"{name} must be an integer in [0, {maximum}]")
    return value


def _source_kind(value: object) -> str:
    if value not in SOURCE_KINDS:
        raise CanFilter32Error("source_kind must be scenario or team_verified")
    return str(value)


@dataclass(frozen=True)
class CanFrame:
    identifier: int
    extended: bool
    remote: bool = False

    def checked(self) -> "CanFrame":
        extended = _strict_bool(self.extended, "extended")
        remote = _strict_bool(self.remote, "remote")
        maximum = EXT_ID_MAX if extended else STD_ID_MAX
        return CanFrame(
            identifier=_uint(self.identifier, maximum, "identifier"),
            extended=extended,
            remote=remote,
        )


@dataclass(frozen=True)
class Filter32:
    """One synthetic 32-bit filter bank.

    In mask mode:
      FR1 = identifier pattern
      FR2 = mask

    In list mode:
      FR1 = first exact identifier word
      FR2 = second exact identifier word
    """

    mode: str
    fr1: int
    fr2: int
    source_kind: str = "scenario"

    def checked(self) -> "Filter32":
        if self.mode not in {MODE_MASK, MODE_LIST}:
            raise CanFilter32Error("mode must be mask or list")
        return Filter32(
            mode=self.mode,
            fr1=_uint(self.fr1, U32_MAX, "fr1"),
            fr2=_uint(self.fr2, U32_MAX, "fr2"),
            source_kind=_source_kind(self.source_kind),
        )


@dataclass(frozen=True)
class FilterDecision:
    schema: str
    accepted: bool
    mode: str
    frame_word: int
    fr1: int
    fr2: int
    source_kind: str

    team_identifier_proven: bool = False
    team_fifo_assignment_proven: bool = False
    team_filter_bank_proven: bool = False
    vehicle_acceptance_proven: bool = False
    action_authority: bool = False

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


def encode_frame_word(frame: CanFrame) -> int:
    """Encode one standard/extended data or remote frame for 32-bit comparison."""
    f = frame.checked()
    if f.extended:
        word = (f.identifier << EXT_ID_SHIFT) | IDE_BIT
    else:
        word = f.identifier << STD_ID_SHIFT
    if f.remote:
        word |= RTR_BIT
    return word & U32_MAX


def join_halves(high: object, low: object) -> int:
    """Reconstruct the FR word written by STM32 HAL from high/low 16-bit fields."""
    hi = _uint(high, U16_MAX, "high")
    lo = _uint(low, U16_MAX, "low")
    return (hi << 16) | lo


def split_halves(word: object) -> tuple[int, int]:
    value = _uint(word, U32_MAX, "word")
    return ((value >> 16) & U16_MAX, value & U16_MAX)


def evaluate_filter(frame: CanFrame, filter32: Filter32) -> FilterDecision:
    f = filter32.checked()
    word = encode_frame_word(frame)
    if f.mode == MODE_MASK:
        accepted = (word & f.fr2) == (f.fr1 & f.fr2)
    else:
        accepted = word == f.fr1 or word == f.fr2
    return FilterDecision(
        schema="enme408-tc03b24-bxcan-filter32/v1",
        accepted=accepted,
        mode=f.mode,
        frame_word=word,
        fr1=f.fr1,
        fr2=f.fr2,
        source_kind=f.source_kind,
    )


def standard_exact_mask(std_id: object, *, remote: bool = False) -> Filter32:
    """Build a scenario filter that distinguishes standard ID, IDE, and RTR."""
    ident = _uint(std_id, STD_ID_MAX, "std_id")
    rtr = _strict_bool(remote, "remote")
    frame = CanFrame(ident, extended=False, remote=rtr)
    mask = (STD_ID_MAX << STD_ID_SHIFT) | IDE_BIT | RTR_BIT
    return Filter32(MODE_MASK, encode_frame_word(frame), mask, "scenario")


def frozen_frame_class_collision() -> dict[str, object]:
    """Show why an ID-only mask does not prove standard/data frame class."""
    base_std_id = 0x321
    standard = CanFrame(base_std_id, extended=False, remote=False)
    extended = CanFrame(
        (base_std_id << 18) | 0x15555,
        extended=True,
        remote=False,
    )

    id_only = Filter32(
        MODE_MASK,
        encode_frame_word(standard),
        STD_ID_MAX << STD_ID_SHIFT,
        "scenario",
    )
    strict_standard = standard_exact_mask(base_std_id, remote=False)

    return {
        "schema": "enme408-tc03b24-frame-class-collision/v1",
        "scenario_only": True,
        "standard_word": encode_frame_word(standard),
        "extended_word": encode_frame_word(extended),
        "id_only_mask": id_only.fr2,
        "id_only_accepts_standard": evaluate_filter(standard, id_only).accepted,
        "id_only_accepts_extended": evaluate_filter(extended, id_only).accepted,
        "strict_standard_mask": strict_standard.fr2,
        "strict_accepts_standard": evaluate_filter(standard, strict_standard).accepted,
        "strict_accepts_extended": evaluate_filter(extended, strict_standard).accepted,
        "team_identifier_proven": False,
        "vehicle_acceptance_proven": False,
        "action_authority": False,
    }
