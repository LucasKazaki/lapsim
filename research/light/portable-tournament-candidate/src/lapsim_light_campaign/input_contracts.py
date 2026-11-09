"""UNTESTED bounded input serialization; no I/O or qualification on import."""
from hashlib import sha256
import json


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return sha256(encode(value)).hexdigest()


def is_sha256(value):
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def exact(value, keys, name):
    require(type(value) is dict and value.keys() == frozenset(keys), "Unexpected " + name + " fields")


def _pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "Duplicate input JSON key")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("Nonfinite input JSON constant: " + value)


def decode(raw, maximum_bytes, *, canonical=False):
    require(type(raw) is bytes and 0 < len(raw) <= maximum_bytes, "Bounded immutable input bytes required")
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
        encoded = encode(value)  # Also rejects overflow-to-infinity literals.
    except (TypeError, UnicodeError, OverflowError, RecursionError) as error:
        raise ValueError("Malformed bounded JSON input") from error
    require(len(encoded) <= maximum_bytes, "Canonical input exceeds bound")
    require(not canonical or encoded == raw, "Canonical JSON input required")
    return value
