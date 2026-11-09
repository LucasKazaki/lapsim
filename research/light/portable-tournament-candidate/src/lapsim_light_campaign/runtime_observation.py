"""UNTESTED deferred observation primitives, not a portable SourceObserver.

Frozen behavior: no facts, paths or process state are observed on import. Only a
separately authorized owner may invoke these functions inside its original
admission/lease/deadline/cleanup controls. There is no CLI, registration, guard
substitute, observation permit or environment-v2 conversion. Unsupported required
facts raise explicitly; startup rounding and ABI traits never become inferred
current rounding, complete ABI or loaded-code identities.
"""

from hashlib import sha256, sha384, sha512
from pathlib import Path
import os
import stat

from . import raw_journal as journal
from .input_contracts import digest, encode


MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_OBSERVATION_BYTES = 4 * 1024 * 1024
_HASHERS = {"sha256": sha256, "sha384": sha384, "sha512": sha512}
API_FACTS = ("implementation", "language_version", "byte_order", "float_format",
             "startup_float_rounds", "reported_executable_path", "abi_info_traits")


class ObservationUnavailable(ValueError):
    pass


def _need(condition, message):
    if not condition:
        raise ObservationUnavailable(message)


def _absolute_regular_path(value):
    path = Path(value)
    _need(path.is_absolute() and not str(path).startswith(("\\\\", "//")), "Explicit ordinary absolute local path required")
    # Check aliases before and after lexical normalization of legal RECORD ../.
    journal._no_alias(path)
    path = Path(os.path.abspath(path))
    _need(not str(path).startswith(("\\\\", "//")), "UNC/device/extended paths are unsupported")
    journal._no_alias(path)
    return path


def _token(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _stable_file(path, before, stream):
    journal._no_alias(path)
    _need(_token(before) == _token(os.fstat(stream.fileno())) == _token(path.stat()),
          "File changed during observation; no atomic/hostile-writer guarantee is supplied")


def _read_snapshot(path, maximum):
    path = _absolute_regular_path(path)
    _need(path.is_file() and stat.S_ISREG(path.stat().st_mode), "Regular artifact file required")
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        _need(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= maximum, "Artifact exceeds byte/type profile")
        raw = stream.read(maximum + 1)
        _need(len(raw) == before.st_size and len(raw) <= maximum, "Artifact read size changed or exceeded its bound")
        _stable_file(path, before, stream)
    return raw


def _measure_stream(stream, maximum, algorithm="sha256"):
    _need(algorithm in _HASHERS, "Only SHA-256/384/512 RECORD hashes are supported")
    base = sha256()
    declared = base if algorithm == "sha256" else _HASHERS[algorithm]()
    total = 0
    while True:
        chunk = stream.read(min(256 * 1024, maximum - total + 1))
        if not chunk:
            break
        total += len(chunk)
        _need(total <= maximum, "Observed artifact exceeds its actual-read byte bound")
        base.update(chunk)
        if declared is not base:
            declared.update(chunk)
    return {"bytes": total, "sha256": base.hexdigest()}, declared.digest()


def _measure_file(path, maximum, algorithm="sha256"):
    path = _absolute_regular_path(path)
    _need(path.is_file() and stat.S_ISREG(path.stat().st_mode), "Regular installed file required")
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        _need(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= maximum, "Installed file exceeds byte/type profile")
        measured, declaration_digest = _measure_stream(stream, maximum, algorithm)
        _need(measured["bytes"] == before.st_size, "Installed file read size changed")
        _stable_file(path, before, stream)
    return measured, declaration_digest


def _version(value):
    result = {name: getattr(value, name) for name in ("major", "minor", "micro", "releaselevel", "serial")}
    _need(all(type(result[name]) is int and 0 <= result[name] <= 1000000
              for name in ("major", "minor", "micro", "serial")) and
          result["releaselevel"] in ("alpha", "beta", "candidate", "final"), "Unsupported runtime version fields")
    return result


def _observe_python_api_facts(required_facts):
    """Return actual selected sys API values, never a v2 environment or ABI tag.

    Required facts are explicit. In particular, native_abi, current_rounding,
    complete_stdlib, loaded_native_closure and authentication are unsupported.
    sys.abi_info is available only on supporting runtimes (documented in 3.15+);
    neither an absent attribute nor a different version is filled from config.
    """
    _need(type(required_facts) is tuple and 0 < len(required_facts) <= len(API_FACTS) and
          all(type(name) is str and 0 < len(name) <= 160 for name in required_facts) and
          len(set(required_facts)) == len(required_facts),
          "Explicit bounded unique required-fact tuple required")
    unsupported = set(required_facts) - set(API_FACTS)
    _need(not unsupported, "Required runtime facts have no supported observation here: " + ", ".join(sorted(unsupported)))
    import sys
    if "abi_info_traits" in required_facts:
        _need(hasattr(sys, "abi_info"), "Required sys.abi_info traits are unavailable; no ABI/config fallback")
    facts = {}
    for name in required_facts:
        if name == "implementation":
            _need(type(sys.implementation.name) is str and 0 < len(sys.implementation.name) <= 160 and
                  (sys.implementation.cache_tag is None or
                   type(sys.implementation.cache_tag) is str and len(sys.implementation.cache_tag) <= 160),
                  "Unsupported implementation API fields")
            facts[name] = {"name": sys.implementation.name, "version": _version(sys.implementation.version),
                           "cache_tag": sys.implementation.cache_tag}
        elif name == "language_version":
            facts[name] = _version(sys.version_info)
        elif name == "byte_order":
            _need(sys.byteorder in ("little", "big"), "Runtime did not expose a supported byte order")
            facts[name] = sys.byteorder
        elif name == "float_format":
            facts[name] = {field: getattr(sys.float_info, field) for field in ("radix", "mant_dig", "max_exp", "min_exp", "dig")}
            _need(all(type(value) is int for value in facts[name].values()) and
                  all(type(getattr(sys.float_info, field)) is float for field in ("epsilon", "max", "min")),
                  "Unsupported floating format API fields")
            facts[name].update({field + "_hex": float.hex(getattr(sys.float_info, field)) for field in ("epsilon", "max", "min")})
        elif name == "startup_float_rounds":
            _need(type(sys.float_info.rounds) is int, "Startup FLT_ROUNDS is unavailable")
            facts[name] = {"value": sys.float_info.rounds, "scope": "FLT_ROUNDS_AT_STARTUP_NOT_CURRENT_MODE_OR_TIE_RULE"}
        elif name == "reported_executable_path":
            _need(type(sys.executable) is str and 0 < len(sys.executable) <= 32768, "Interpreter did not report a bounded executable path")
            facts[name] = {"path": sys.executable, "scope": "SYS_REPORTED_PATH_NOT_LOADED_IMAGE_OR_FILE_HASH"}
        elif name == "abi_info_traits":
            value = sys.abi_info
            facts[name] = {field: getattr(value, field) for field in ("pointer_bits", "free_threaded", "debug", "byteorder")}
            _need(type(facts[name]["pointer_bits"]) is int and facts[name]["pointer_bits"] > 0 and
                  all(type(facts[name][field]) is bool for field in ("free_threaded", "debug")) and
                  facts[name]["byteorder"] in ("big", "little"), "Required ABI API traits are unsupported")
    body = {"schema": "lapsim.light-python-api-observation.raw.v1", "api_facts": facts,
            "scope": "SEQUENTIAL_CURRENT_INTERPRETER_API_READS_NOT_ATOMIC_OR_AUTHENTICATED",
            "complete_source_observer": False, "environment_v2_compatible": False,
            "current_rounding_or_complete_abi_established": False, "source_authentication_established": False,
            "qualification_or_execution_authority": False}
    _need(len(encode(body)) <= MAX_OBSERVATION_BYTES, "Runtime API observation exceeds bound")
    return {"observation": body, "observation_sha256": digest(body)}


def observe_python_api_facts(*, required_facts):
    """Read only explicitly requested supported API facts under the original owner.

    Missing/malformed runtime APIs refuse the entire observation; no partial
    record, complete ABI, current rounding rule or environment-v2 body is emitted.
    """
    try:
        return _observe_python_api_facts(required_facts)
    except ObservationUnavailable:
        raise
    except Exception as error:
        if type(error) not in (AttributeError, TypeError, ValueError, OverflowError, OSError):
            raise  # Unknown owner-control subclasses and MemoryError are untouched.
        raise ObservationUnavailable("Required Python API observation unavailable: " + str(error)) from error
