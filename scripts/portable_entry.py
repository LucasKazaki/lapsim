"""PyInstaller entry; the implementation stays in the importable package."""
from lapsim.desktop import main

if __name__ == "__main__":
    raise SystemExit(main())
