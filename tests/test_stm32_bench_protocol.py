"""Frozen byte order, frame budget, integrity and finite binary64 input."""

import struct
from dataclasses import replace

import pytest

from lapsim.experiments.controller_backend import PythonController
from lapsim.experiments.stm32_backend import decode_frame, encode_frame, encode_sample


def test_session_frame_matches_frozen_little_endian_crc32_vector():
    raw = encode_frame(2, 0x0102030405060708, 0)
    assert raw.hex() == "4c5343310102000008070605040302010000000094700251"
    assert decode_frame(raw) == (2, 0x0102030405060708, 0, b"")


def test_frame_budget_crc_and_truncation_fail_explicitly():
    raw = encode_frame(1, 1, 1, bytes(488))
    assert len(raw) == 512 and len(decode_frame(raw)[3]) == 488
    with pytest.raises(ValueError, match="oversized"):
        encode_frame(1, 1, 1, bytes(489))
    for broken in (raw[:-1], raw + b"x", raw[:8], raw[:-1] + b"x"):
        with pytest.raises(ValueError):
            decode_frame(broken)


@pytest.mark.parametrize(
    "args",
    [(True, 1, 1), (1, -1, 1), (256, 1, 1), (1, 2**64, 1), (1, 1, 2**32), (1, 1, 1.0)],
)
def test_header_integers_are_bounded_and_do_not_accept_booleans(args):
    with pytest.raises(ValueError, match="unsigned"):
        encode_frame(*args)


def test_sample_preserves_binary64_and_rejects_nonfinite_or_wrong_units():
    controller = PythonController()
    sample = controller.sample(
        30,
        20,
        123.1234567890123,
        (0.0, 0.0, 200.0, 200.0),
        (False, False, True, True),
        0.7,
        False,
        True,
        True,
    )
    raw = encode_sample(sample)
    assert len(raw) == 78
    values = struct.unpack("<QQ7d6B", raw)
    assert values[:2] == (30, 20) and values[4] == 123.1234567890123
    for bad in (float("nan"), float("inf"), True, 10**400):
        with pytest.raises(ValueError):
            encode_sample(
                replace(sample, allocation=replace(sample.allocation, request_nm=bad))
            )
    with pytest.raises(ValueError):
        encode_sample(
            replace(sample, allocation=replace(sample.allocation, torque_unit="lb*ft"))
        )
