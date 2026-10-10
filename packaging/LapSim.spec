# Build with scripts/build_windows.py, which stages verified read-only assets.
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata

root = Path(SPECPATH).parent
metadata = []
for package in ('numpy', 'scipy', 'matplotlib', 'python-lapsim'):
    metadata += copy_metadata(package)
a = Analysis(
    [str(root / 'scripts/portable_entry.py')],
    pathex=[str(root / 'src')],
    binaries=[],
    datas=[(str(root / 'build/assets'), 'bundle')] + metadata,
    hiddenimports=['matplotlib.backends.backend_tkagg'],
    hookspath=[], hooksconfig={'matplotlib': {'backends': ['TkAgg', 'Agg']}},
    runtime_hooks=[], excludes=['pytest', 'asammdf'], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='LapSim', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False, disable_windowed_traceback=False,
)
