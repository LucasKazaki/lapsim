"""PyInstaller entry for the public, synthetic-data-only distribution."""

from __future__ import annotations


def _configure_public_course_catalog() -> None:
    """Remove courses whose publication authority is unresolved.

    The source checkout can still expose separately authorized team courses to
    UMD users. The public Windows artifact intentionally offers only analytic
    synthetic courses, so merely building the executable cannot redistribute
    the excluded GNSS/IMU files.
    """

    from lapsim.ui import course_catalog

    public_options = tuple(
        spec for spec in course_catalog.COURSE_OPTIONS if spec.synthetic
    )
    if not public_options:
        raise RuntimeError("Public distribution has no synthetic course")
    course_catalog.COURSE_OPTIONS = public_options


_configure_public_course_catalog()

from lapsim.desktop import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
