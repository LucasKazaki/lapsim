"""Enforce Developer Certificate of Origin trailers on post-adoption PR commits."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SIGN_OFF = re.compile(
    r"^Signed-off-by:\s*(?P<name>.+?)\s*<(?P<email>[^<>\s]+)>\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def policy_exists_at(ref: str) -> bool:
    return (
        git(
            "cat-file",
            "-e",
            f"{ref}:CONTRIBUTING.md",
            check=False,
        ).returncode
        == 0
    )


def normalized_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        required=True,
        help="Pull-request base commit SHA",
    )
    parser.add_argument(
        "--head",
        required=True,
        help="Pull-request head commit SHA",
    )
    args = parser.parse_args()

    # The PR that first adopts this policy is the explicit bootstrap exception.
    # Every later PR has CONTRIBUTING.md on its base and is enforced.
    if not policy_exists_at(args.base):
        print(
            "DCO policy is not present on the base commit; "
            "bootstrap PR exempt."
        )
        return 0

    commits = [
        sha
        for sha in git(
            "rev-list",
            "--reverse",
            f"{args.base}..{args.head}",
        ).stdout.splitlines()
        if sha
    ]
    failures: list[str] = []
    for sha in commits:
        record = git(
            "show",
            "-s",
            "--format=%an%x00%ae%x00%B",
            sha,
        ).stdout
        try:
            author_name, author_email, message = record.split("\x00", 2)
        except ValueError as error:
            raise RuntimeError(
                f"Could not parse commit metadata for {sha}"
            ) from error

        matching_sign_off = any(
            normalized_name(match.group("name"))
            == normalized_name(author_name)
            and match.group("email").casefold()
            == author_email.strip().casefold()
            for match in SIGN_OFF.finditer(message)
        )
        if not matching_sign_off:
            failures.append(
                f"{sha[:12]} by {author_name} <{author_email}> lacks a "
                "matching Signed-off-by trailer; amend with "
                "`git commit --amend -s` or rebase and sign the commit."
            )

    if failures:
        raise SystemExit(
            "DCO sign-off check failed:\n- " + "\n- ".join(failures)
        )

    print(f"DCO sign-off check passed for {len(commits)} commit(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
