"""Installed entrypoint for the existing skidpad analysis command."""

import runpy
import sys

from lapsim.resources import repository_root


def main(argv=None):
    """Use the captured source command and restore the caller's import path."""
    root = repository_root().resolve()
    script = root / "analysis/events/skidpad_points.py"
    if (not script.is_file() or script.is_symlink()
            or not script.resolve().is_relative_to(root)):
        raise RuntimeError("The installed skidpad command resource is unavailable")
    previous_path = list(sys.path)
    try:
        command = runpy.run_path(str(script), run_name="_lapsim_skidpad_command")
        return command["main"](argv)
    finally:
        sys.path[:] = previous_path


if __name__ == "__main__":
    raise SystemExit(main())
