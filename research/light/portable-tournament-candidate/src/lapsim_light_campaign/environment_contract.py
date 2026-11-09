"""UNTESTED exact environment declarations/observation matching; no probes.

This does not authenticate an observation or inspect an executing process.
The reviewed external owner supplies and authenticates both provenance and
actual measurements; no environment is certified by this local comparison.
"""
import re

from .input_contracts import decode, digest, encode, exact, is_sha256, require


SCHEMA = "lapsim.light-exact-environment.v2"
NUMERICAL_CONTENT_SCHEMA = "lapsim.light-numerical-environment-content.v1"
MAX_ENVIRONMENT_BYTES = 1024 * 1024
MAX_NUMERICAL_CONTENT_BYTES = MAX_ENVIRONMENT_BYTES - 1024
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,159}\Z")


def _text(value):
    return type(value) is str and 0 < len(value) <= 160 and value.strip() == value


def validate_numerical_environment(value, *, expected_verifier_sha256):
    """Return E from source-independent exact numeric content; never observe it.

    Actual static artifacts must be independently reviewed. Generated source
    bindings/certificates must not be fed back into this content's own closure.
    """
    exact(value, {"schema", "interpreter", "platform", "numeric_contract", "artifacts",
                  "dependencies", "verifier_implementation_sha256"}, "numerical environment content")
    require(value["schema"] == NUMERICAL_CONTENT_SCHEMA and is_sha256(expected_verifier_sha256) and
            value["verifier_implementation_sha256"] == expected_verifier_sha256,
            "Numerical content schema or verifier binding differs")
    interpreter = value["interpreter"]
    exact(interpreter, {"implementation", "version", "abi", "executable_sha256",
                        "stdlib_manifest_sha256"}, "interpreter identity")
    require(all(_text(interpreter[k]) for k in ("implementation", "version", "abi")) and
            re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:(?:a|b|rc)[0-9]+)?(?:\+[A-Za-z0-9._-]+)?",
                         interpreter["version"]) and
            is_sha256(interpreter["executable_sha256"]) and
            is_sha256(interpreter["stdlib_manifest_sha256"]), "Exact interpreter/standard-library identity required")
    platform = value["platform"]
    exact(platform, {"system", "machine", "byte_order"}, "platform identity")
    require(_text(platform["system"]) and _text(platform["machine"]) and
            platform["byte_order"] in ("little", "big"), "Exact platform identity required")
    require(value["numeric_contract"] == {"float_radix": 2, "float_mant_dig": 53,
                                         "float_max_exp": 1024, "rounding": "nearest_ties_to_even"} and
            all(type(value["numeric_contract"][k]) is int for k in
                ("float_radix", "float_mant_dig", "float_max_exp")),
            "Explicit binary64 numeric recipe required")
    artifacts = value["artifacts"]
    require(type(artifacts) is dict and 3 <= len(artifacts) <= 8192 and
            {"python_executable", "stdlib_manifest", "admission_verifier"} <= artifacts.keys(),
            "Complete bounded artifact inventory required")
    for name, artifact in artifacts.items():
        require(type(name) is str and _NAME.fullmatch(name) and ".." not in name.split("/"),
                "Logical artifact names only; no host paths")
        exact(artifact, {"bytes", "sha256", "role"}, "environment artifact")
        require(type(artifact["bytes"]) is int and artifact["bytes"] > 0 and
                is_sha256(artifact["sha256"]) and _text(artifact["role"]),
                "Exact artifact bytes/hash/role required")
    require(artifacts["python_executable"]["sha256"] == interpreter["executable_sha256"] and
            artifacts["stdlib_manifest"]["sha256"] == interpreter["stdlib_manifest_sha256"] and
            artifacts["admission_verifier"]["sha256"] == expected_verifier_sha256,
            "Environment artifacts disagree with interpreter/verifier identities")
    dependencies = value["dependencies"]
    require(type(dependencies) is dict and len(dependencies) <= 256, "Bounded exact dependency inventory required")
    for name, dependency in dependencies.items():
        require(_text(name) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name),
                "Explicit distribution identifier required")
        exact(dependency, {"version", "distribution_sha256", "installed_manifest_sha256"}, "dependency identity")
        require(_text(dependency["version"]) and
                re.fullmatch(r"[0-9][A-Za-z0-9._+!-]*", dependency["version"]) and
                is_sha256(dependency["distribution_sha256"]) and
                is_sha256(dependency["installed_manifest_sha256"]), "Exact dependency version and file identities required")
    require(len(encode(value)) <= MAX_NUMERICAL_CONTENT_BYTES, "Numerical content exceeds envelope-reserved bound")
    return digest(value)


def validate_environment_recipe(value, *, expected_source_sha256, expected_verifier_sha256):
    """Check the separate v2 source binding; return ONLY numerical-content E.

    E is computed first. The source observer then hashes its unchanged body
    containing E to obtain S. This envelope binds that S without hashing it back
    into E. V1 recipes are refused; their full-envelope digest is not reinterpreted.
    """
    exact(value, {"schema", "source_sha256", "numerical_environment"}, "source-bound v2 environment envelope")
    require(value["schema"] == SCHEMA and is_sha256(expected_source_sha256) and
            value["source_sha256"] == expected_source_sha256,
            "Environment envelope schema or separately pinned source binding differs")
    require(len(encode(value)) <= MAX_ENVIRONMENT_BYTES, "Environment envelope exceeds bound")
    return validate_numerical_environment(value["numerical_environment"],
                                           expected_verifier_sha256=expected_verifier_sha256)


def require_environment_match(recipe_raw, observation_raw, *, expected_numerical_environment_sha256,
                              expected_source_sha256, expected_verifier_sha256):
    require(is_sha256(expected_numerical_environment_sha256), "Independently pinned numerical-content digest required")
    recipe = decode(recipe_raw, MAX_ENVIRONMENT_BYTES)
    observation = decode(observation_raw, MAX_ENVIRONMENT_BYTES)
    observed = validate_environment_recipe(recipe, expected_source_sha256=expected_source_sha256,
                                           expected_verifier_sha256=expected_verifier_sha256)
    validate_environment_recipe(observation, expected_source_sha256=expected_source_sha256,
                                expected_verifier_sha256=expected_verifier_sha256)
    require(observed == expected_numerical_environment_sha256 and encode(observation) == encode(recipe),
            "Observed numerical content or complete source-bound v2 envelope differs")
    return {"status": "EXACT_DECLARATION_MATCH_PENDING_EXTERNAL_AUTHENTICATION",
            "environment_sha256": observed, "environment_identity_scope": NUMERICAL_CONTENT_SCHEMA,
            "source_binding_sha256": expected_source_sha256, "qualification_or_execution_authority": False,
            "runtime_probe_performed": False}
