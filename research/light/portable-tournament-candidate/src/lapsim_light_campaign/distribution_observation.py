"""UNTESTED deferred wheel/installed-RECORD observation, without payload imports.

Frozen profile v1: inspect the same bounded immutable wheel bytes that are
hashed; no extraction, installer, package import, discovery hook or CLI. Support
ordinary single-disk non-ZIP64 wheels with unrelocated root payload. Refuse
.data, editable/path-extension and signed-wheel profiles explicitly. Installed
RECORD paths may traverse to scripts only inside the reviewed installation root.
Measure every listed file, including blank-hash/self/generated records. This is
not complete installed/stdlib/loaded-native closure, provenance authentication,
an environment-v2 observation, a SourceObserver or execution permission.
Invocation still requires the original owner's admission/lease/deadline/cleanup.
"""

import base64
from binascii import Error as Base64Error
import csv
from email.parser import BytesHeaderParser
from hashlib import sha256
import io
from json import JSONDecodeError
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import zipfile

try:
    from zlib import error as DeflateError
except ImportError as error:
    if type(error) not in (ImportError, ModuleNotFoundError):
        raise
    DeflateError = None  # Stored wheels remain observable; deflated reads refuse.

from . import raw_journal as journal
from .input_contracts import decode, digest, encode, is_sha256
from .runtime_observation import (MAX_FILE_BYTES, MAX_OBSERVATION_BYTES, ObservationUnavailable,
                                  _absolute_regular_path, _measure_file, _measure_stream, _need, _read_snapshot)


MAX_WHEEL_BYTES = 128 * 1024 * 1024
MAX_CENTRAL_BYTES = 4 * 1024 * 1024
MAX_RECORD_BYTES = 1024 * 1024
MAX_METADATA_BYTES = 1024 * 1024
MAX_FILES = 4096
MAX_TOTAL_BYTES = 512 * 1024 * 1024
_DIGEST_BYTES = {"sha256": 32, "sha384": 48, "sha512": 64}
_DEVICE_NAMES = frozenset({"CON", "PRN", "AUX", "NUL"} |
                          {"COM" + str(i) for i in range(1, 10)} | {"LPT" + str(i) for i in range(1, 10)})
_KNOWN_ERRORS = (OSError, BlockingIOError, FileNotFoundError, FileExistsError,
                 IsADirectoryError, NotADirectoryError, PermissionError,
                 InterruptedError, TimeoutError, ValueError, TypeError, KeyError,
                 OverflowError, EOFError, NotImplementedError, RuntimeError,
                 UnicodeError, UnicodeDecodeError, UnicodeEncodeError, UnicodeTranslateError,
                 csv.Error, JSONDecodeError, Base64Error, struct.error, zipfile.BadZipFile, zipfile.LargeZipFile)
if DeflateError is not None:
    _KNOWN_ERRORS += (DeflateError,)


def _headers(raw):
    _need(0 < len(raw) <= MAX_METADATA_BYTES, "Required metadata is empty or oversized")
    headers = BytesHeaderParser().parsebytes(raw)
    _need(not headers.defects, "Malformed metadata header profile")
    return headers


def _one_header(headers, name):
    values = headers.get_all(name, [])
    _need(len(values) == 1 and type(values[0]) is str and 0 < len(values[0]) <= 160 and
          values[0].strip() == values[0], "Missing/unsupported metadata header: " + name)
    return values[0]


def _member_name(name):
    _need(type(name) is str and name.isascii() and 0 < len(name) <= 512 and
          not any(ord(char) < 32 or ord(char) == 127 or char in '\\:<>"|?*' for char in name), "Unsupported portable member path")
    path = PurePosixPath(name)
    _need(not path.is_absolute() and str(path) == name and
          all(part not in (".", "..") and not part.endswith((".", " ")) for part in path.parts),
          "Escaping or noncanonical portable member")
    _need(all(part.split(".", 1)[0].upper() not in _DEVICE_NAMES for part in path.parts),
          "Reserved device member path is unsupported")
    return path


def _record_hash(value):
    if value == "":
        return None
    _need("=" in value, "Malformed RECORD hash")
    algorithm, encoded = value.split("=", 1)
    _need(algorithm in _DIGEST_BYTES and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", encoded),
          "Unsupported RECORD hash profile; SHA-256/384/512 without padding required")
    raw = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
    _need(len(raw) == _DIGEST_BYTES[algorithm] and base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") == encoded,
          "Noncanonical RECORD digest")
    return algorithm, raw


def _records(raw):
    _need(0 < len(raw) <= MAX_RECORD_BYTES, "Bounded nonempty RECORD bytes required")
    result = {}
    for row in csv.reader(io.StringIO(raw.decode("utf-8"), newline=""), strict=True):
        _need(len(row) == 3 and 0 < len(row[0]) <= 512 and row[0] not in result, "Duplicate or malformed RECORD path")
        declared_size = None
        if row[2] != "":
            _need(row[2].isascii() and row[2].isdecimal() and len(row[2]) <= 12, "Unsupported RECORD byte count")
            declared_size = int(row[2])
            _need(declared_size <= MAX_FILE_BYTES, "RECORD file exceeds per-file profile")
        result[row[0]] = {"hash": _record_hash(row[1]), "size": declared_size,
                          "declared_hash": row[1], "declared_size": row[2]}
        _need(len(result) <= MAX_FILES, "RECORD file count exceeds profile")
    return result


def _match_record(measured, actual_digest, entry, *, hash_required):
    _need(not hash_required or entry["hash"] is not None, "Wheel payload lacks its required digest")
    if entry["hash"] is not None:
        _need(actual_digest == entry["hash"][1], "Actual file bytes differ from RECORD hash")
    if entry["size"] is not None:
        _need(measured["bytes"] == entry["size"], "Actual file size differs from RECORD")


def _zip_entries(raw):
    # Bound the ordinary ZIP central directory BEFORE ZipFile parses/allocates
    # it. ZIP64, comments, split archives and appended/prepended wrappers refuse.
    _need(len(raw) >= 22, "Wheel is too small for ordinary ZIP framing")
    signature, disk, start_disk, disk_entries, entries, size, offset, comment = struct.unpack("<4s4H2IH", raw[-22:])
    _need(signature == b"PK\x05\x06" and disk == start_disk == 0 and comment == 0 and
          0 < entries == disk_entries <= MAX_FILES and size <= MAX_CENTRAL_BYTES and
          offset + size == len(raw) - 22 and raw[:4] == b"PK\x03\x04",
          "Unsupported ZIP framing/count/central-directory profile")
    with zipfile.ZipFile(io.BytesIO(raw), "r") as zipped:
        infos = zipped.infolist()
        _need(len(infos) == entries, "ZIP entry count differs from bounded framing")
        files, seen, total = {}, set(), 0
        for info in infos:
            # CPython retains the original spelling separately; its normalized
            # filename may truncate NUL or rewrite separators. No fallback to
            # the normalized value when the original attribute is unavailable.
            original = getattr(info, "orig_filename", None)
            _need(type(original) is str and original == info.filename,
                  "Original ZIP member spelling unavailable or normalized/truncated")
            name = info.filename[:-1] if info.is_dir() else info.filename
            parts = _member_name(name)
            _need(name.casefold() not in seen, "Duplicate/case-colliding wheel member")
            seen.add(name.casefold())
            kind = stat.S_IFMT(info.external_attr >> 16)
            _need(kind in ((0, stat.S_IFDIR) if info.is_dir() else (0, stat.S_IFREG)) and not info.flag_bits & 1 and
                  info.extract_version <= 20 and info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                  "Unsupported alias/encryption/compression/ZIP64 member")
            _need(not parts.parts[0].lower().endswith(".data") and not name.lower().endswith((".pth", ".egg-link")),
                  "Wheel relocation/path-extension profile needs a separately reviewed mapping")
            _need(0 <= info.file_size <= MAX_FILE_BYTES, "Declared member exceeds byte bound")
            _need(not info.is_dir() or info.file_size == 0, "Directory member has unsupported nonempty payload")
            total += info.file_size
            _need(total <= MAX_TOTAL_BYTES, "Declared wheel expansion exceeds total byte bound")
            if not info.is_dir():
                files[name] = info
        prefixes = {PurePosixPath(name).parts[0] for name in files if PurePosixPath(name).parts[0].endswith(".dist-info")}
        _need(len(prefixes) == 1, "Exactly one wheel dist-info directory required")
        prefix = prefixes.pop()
        record_name = prefix + "/RECORD"
        _need({record_name, prefix + "/METADATA", prefix + "/WHEEL"} <= files.keys(), "Wheel metadata/RECORD is missing")
        _need(not any(name in files for name in (record_name + ".jws", record_name + ".p7s")),
              "Signed-wheel profile is unsupported; no signature provider is inferred")
        with zipped.open(files[record_name]) as stream:
            record_raw = stream.read(MAX_RECORD_BYTES + 1)
        records = _records(record_raw)
        _need(set(records) == set(files), "Wheel RECORD does not exactly name its payload")
        _need(records[record_name]["hash"] is None and records[record_name]["size"] is None, "Wheel RECORD self declaration must be blank")
        measured, metadata = {}, {}
        actual_total = 0
        for name, info in files.items():
            entry = records[name]
            algorithm = "sha256" if entry["hash"] is None else entry["hash"][0]
            with zipped.open(info) as stream:
                facts, actual_digest = _measure_stream(stream, min(MAX_FILE_BYTES, MAX_TOTAL_BYTES - actual_total), algorithm)
            actual_total += facts["bytes"]
            _need(facts["bytes"] == info.file_size, "Actual ZIP member size differs")
            _match_record(facts, actual_digest, entry, hash_required=name != record_name)
            measured[name] = facts
            if name in (prefix + "/METADATA", prefix + "/WHEEL"):
                with zipped.open(info) as stream:
                    metadata[name] = stream.read(MAX_METADATA_BYTES + 1)
                _need(len(metadata[name]) <= MAX_METADATA_BYTES, "Wheel metadata exceeds bound")
        return prefix, measured, metadata


def _installed_target(base, name, root):
    _need(not any(ord(char) < 32 or ord(char) == 127 for char in name), "Control character in installed RECORD path")
    _need("\\" not in name or os.name == "nt", "Non-native backslash RECORD paths are unsupported")
    spelling = name.replace("\\", "/")
    _need(not spelling.startswith("//"), "Network/device RECORD paths are unsupported")
    _need(":" not in spelling or (os.name == "nt" and re.match(r"^[A-Za-z]:/[^:]*$", spelling)),
          "Foreign drive or alternate-stream RECORD paths are unsupported")
    value = Path(spelling)
    lexical = value if value.is_absolute() else base / value
    target = Path(os.path.abspath(lexical))
    _need(target != root and target.is_relative_to(root), "Installed RECORD target escapes the reviewed installation root")
    # Refuse Windows trailing-dot/space/device spellings even on a different
    # review platform; distinct RECORD strings must not conceal the same path.
    _member_name(target.relative_to(root).as_posix())
    journal._no_alias(lexical)
    return _absolute_regular_path(target)


def _observe(wheel_path, dist_info_path, root, expected_wheel_sha256, expected_record_sha256):
    _need(is_sha256(expected_wheel_sha256) and is_sha256(expected_record_sha256), "Independently reviewed artifact/RECORD pins required")
    root, dist = _absolute_regular_path(root), _absolute_regular_path(dist_info_path)
    _need(root.is_dir() and dist.is_dir() and dist.is_relative_to(root) and dist.name.endswith(".dist-info"),
          "Explicit real installation root and contained dist-info directory required")
    wheel_raw = _read_snapshot(wheel_path, MAX_WHEEL_BYTES)
    _need(sha256(wheel_raw).hexdigest() == expected_wheel_sha256, "Wheel artifact bytes differ from expected pin")
    record_raw = _read_snapshot(dist / "RECORD", MAX_RECORD_BYTES)
    _need(sha256(record_raw).hexdigest() == expected_record_sha256, "Installed RECORD bytes differ from expected pin")
    prefix, wheel_files, wheel_metadata = _zip_entries(wheel_raw)
    _need(prefix == dist.name, "Wheel/installed dist-info spelling differs; no rename inference")
    metadata = _headers(wheel_metadata[prefix + "/METADATA"])
    name, version = _one_header(metadata, "Name"), _one_header(metadata, "Version")
    _need(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", name), "Unsupported metadata project name")
    normalize = lambda value: re.sub(r"[-_.]+", "-", value).lower()
    spelling = prefix[:-len(".dist-info")].rsplit("-", 1)
    _need(len(spelling) == 2 and normalize(spelling[0]) == normalize(name) and spelling[1] == version,
          "Unsupported metadata/name/version normalization profile")
    wheel_headers = _headers(wheel_metadata[prefix + "/WHEEL"])
    _need(_one_header(wheel_headers, "Wheel-Version") == "1.0" and
          _one_header(wheel_headers, "Root-Is-Purelib") in ("true", "false"), "Unsupported wheel metadata version/profile")
    records = _records(record_raw)
    paths, observed, total = {}, {}, 0
    for declared_name, entry in records.items():
        target = _installed_target(dist.parent, declared_name, root)
        logical = target.relative_to(root).as_posix()
        _need(logical.casefold() not in paths and not logical.lower().endswith((".pth", ".egg-link")),
              "Duplicate/aliased/path-extension installed RECORD entry")
        paths[logical.casefold()] = logical
        algorithm = "sha256" if entry["hash"] is None else entry["hash"][0]
        facts, actual_digest = _measure_file(target, min(MAX_FILE_BYTES, MAX_TOTAL_BYTES - total), algorithm)
        total += facts["bytes"]
        _match_record(facts, actual_digest, entry, hash_required=False)
        observed[logical] = {**facts, "record_path": declared_name, "declared_hash": entry["declared_hash"],
                             "declared_size": entry["declared_size"]}
    record_logical = (dist / "RECORD").relative_to(root).as_posix()
    _need(record_logical in observed and observed[record_logical]["sha256"] == expected_record_sha256,
          "Installed RECORD must list its own unchanged bytes")
    shared = []
    for name_in_wheel, facts in wheel_files.items():
        if name_in_wheel == prefix + "/RECORD":
            continue  # Installers rewrite RECORD; actual installed bytes are observed above.
        target = _installed_target(dist.parent, name_in_wheel, root)
        logical = target.relative_to(root).as_posix()
        _need(logical in observed and observed[logical]["sha256"] == facts["sha256"] and
              observed[logical]["bytes"] == facts["bytes"], "Missing or changed unrelocated wheel payload file")
        shared.append(logical)
    direct = dist / "direct_url.json"
    direct_logical = direct.relative_to(root).as_posix()
    journal._no_alias(direct)
    _need(not direct.exists() or direct_logical in observed, "Unrecorded direct-url metadata is unsupported")
    if direct_logical in observed:
        direct_raw = _read_snapshot(direct, MAX_METADATA_BYTES)
        _need(sha256(direct_raw).hexdigest() == observed[direct_logical]["sha256"], "Direct-url metadata changed")
        value = decode(direct_raw, MAX_METADATA_BYTES)
        _need(type(value) is dict and type(value.get("dir_info", {})) is dict and
              type(value.get("dir_info", {}).get("editable", False)) is bool and
              value.get("dir_info", {}).get("editable", False) is False, "Editable/malformed installation profile is unsupported")
    body = {
        "schema": "lapsim.light-wheel-record-observation.raw.v1", "declared_metadata_name": name,
        "declared_metadata_version": version, "wheel_bytes": len(wheel_raw), "wheel_sha256": expected_wheel_sha256,
        "installed_record_bytes": len(record_raw), "installed_record_sha256": expected_record_sha256,
        "wheel_file_inventory": wheel_files, "installed_record_inventory": observed,
        "installed_record_inventory_sha256": digest(observed), "shared_payload_paths": sorted(shared),
        "additional_recorded_paths": sorted(set(observed) - set(shared) - {record_logical}),
        "scope": "SEQUENTIAL_DISK_BYTES_UNDER_CALLER_WRITER_EXCLUSION_NOT_ATOMIC_OR_LOADED_CODE",
        "complete_installed_or_stdlib_or_native_closure": False, "wheel_install_provenance_authenticated": False,
        "source_authentication_established": False,
        "environment_v2_compatible": False, "complete_source_observer": False, "qualification_or_execution_authority": False,
    }
    _need(len(encode(body)) <= MAX_OBSERVATION_BYTES, "Disk observation exceeds output bound; no evidence is truncated")
    return {"observation": body, "observation_sha256": digest(body)}


def observe_wheel_installation(wheel_path, dist_info_path, *, installation_root,
                               expected_wheel_sha256, expected_installed_record_sha256):
    """Observe actual archive and installed bytes only when separately authorized.

    No discovery, observed-distribution/payload import, write, installer or
    process is invoked. Standard-library readers may load their own compression
    extensions; this result never establishes loaded-native closure.
    RECORD can omit bytecode/unlisted files: the result MUST NOT fill a complete
    v2 installed-manifest/native closure or authenticate where execution loaded.
    Original outer ownership, hard deadlines and cleanup remain mandatory.
    """
    try:
        return _observe(wheel_path, dist_info_path, installation_root,
                        expected_wheel_sha256, expected_installed_record_sha256)
    except ObservationUnavailable:
        raise
    except Exception as error:
        if type(error) not in _KNOWN_ERRORS:
            raise  # Preserve unknown owner control types/subclasses and MemoryError.
        raise ObservationUnavailable("Required wheel/install observation unavailable: " + str(error)) from error
