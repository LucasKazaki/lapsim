"""Run independent audit gates without hiding failures or stopping at the first one."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'audit'
OUT.mkdir(exist_ok=True)
os.chdir(ROOT)
results = []


def run(name: str, command: list[str], timeout: int = 300) -> None:
    start = time.monotonic()
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        code, output = completed.returncode, completed.stdout + completed.stderr
    except subprocess.TimeoutExpired as exc:
        code, output = 124, f'TIMEOUT after {timeout}s\n{exc.stdout!r}\n{exc.stderr!r}'
    except OSError as exc:
        code, output = 127, str(exc)
    (OUT / f'{name}.log').write_text(output, encoding='utf-8')
    results.append({'gate': name, 'command': command, 'exit_code': code, 'duration_s': round(time.monotonic()-start, 3)})
    print(f'{name}: exit {code}, {results[-1]["duration_s"]} seconds', flush=True)
    # Full diagnostics remain in the artifact; emit a compact reviewable tail.
    print(output[-5000:], flush=True)


(OUT / 'commit.txt').write_text(subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True))
(OUT / 'python-environment.txt').write_text(subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True))
(OUT / 'semgrep-environment.txt').write_text(subprocess.check_output(['/tmp/lapsim-semgrep/bin/pip', 'freeze'], text=True))
subprocess.run(['git', 'archive', '--format=zip', '-o', str(OUT/'source-snapshot.zip'), 'HEAD'], check=True)
run('ruff', ['ruff', 'check', '.', '--select', 'E4,E7,E9,F,B,SIM,C4,PIE,UP,RUF', '--output-format', 'json'])
run('format', ['ruff', 'format', '--check', '.'])
run('pyright', ['pyright', 'src', '--pythonversion', '3.11', '--outputjson'])
run('semgrep', ['/tmp/lapsim-semgrep/bin/semgrep', 'scan', '--config', 'p/python', '--config', 'p/javascript', '--metrics=off', '--error', '--json', '--output', str(OUT/'semgrep.json'), '.'], 600)
os.environ['MPLBACKEND'] = 'Agg'
pytest = [sys.executable, '-m', 'pytest', 'tests', '--cov=lapsim', '--cov-branch', '--cov-report=term', '--cov-report=json:audit/coverage.json', '--junitxml=audit/pytest.xml', '-q', '-ra']
if shutil.which('xvfb-run'):
    pytest = ['xvfb-run', '-a', *pytest]
run('pytest', pytest, 900)
run('hypothesis', [sys.executable, '-m', 'pytest', 'quality/test_properties.py', '-v', '--hypothesis-show-statistics', '--junitxml=audit/hypothesis.xml'], 300)
(OUT / 'summary.json').write_text(json.dumps(results, indent=2))
print(json.dumps(results, indent=2), flush=True)
sys.exit(any(result['exit_code'] != 0 for result in results))
