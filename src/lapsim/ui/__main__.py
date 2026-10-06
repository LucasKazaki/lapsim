"""Run the native LapSim desktop app with ``python -m lapsim.ui``."""

import os

# The lap solver uses scalar numerical operations; extra BLAS worker threads
# add memory pressure without helping the desktop calculation.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

from .app import main

if __name__ == "__main__":
    main()
