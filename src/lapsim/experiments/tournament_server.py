"""Loopback-only static replay / single-worker batch launcher. No hardware I/O."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import threading
from urllib.parse import urlsplit,parse_qs,unquote
import uuid

from .tournament_sweep import PARAMETERS, axes_from
from .record_io import read_json_bounded, write_text_atomic
from lapsim.resources import repository_root
from lapsim.torque_configurator.api import confined_file, resolve_work_directory

ROOT = repository_root()  # Immutable checkout or installed resource tree.
JOB = None
JOB_LOCK = threading.Lock()


def stop_owned_worker(process, *, windows=None):
    """Stop the exact owned process tree, including Windows venv launchers.

    Terminating only the venv shim leaves its Python child simulating and able
    to overwrite saved results. Never match executable names or other jobs.
    """
    if process.poll() is not None:
        return
    is_windows = windows if windows is not None else os.name == "nt"
    if is_windows:
        subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                       check=True, capture_output=True, timeout=10,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        process.terminate()
    process.wait(timeout=10)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, resource_root=None, work_dir=None, **kwargs):
        self.resource_root = Path(ROOT if resource_root is None else resource_root).resolve()
        self.work_dir = resolve_work_directory(work_dir, resource_root=self.resource_root)
        super().__init__(*args, directory=str(self.resource_root), **kwargs)

    def translate_path(self, path):
        decoded = unquote(urlsplit(path).path, errors='strict')
        if not decoded.startswith('/') or decoded.startswith('//'):
            raise ValueError('Unsupported local resource URL')
        parts = decoded[1:].split('/')
        if len(parts) < 2:
            raise ValueError('Choose an explicit resource file')
        if parts[0] == 'web':
            return str(confined_file(self.resource_root / 'web', parts[1:]))
        if parts[0] == 'work':
            return str(confined_file(self.work_dir, parts[1:]))
        raise ValueError('Only local web assets and selected work files are served')

    def send_head(self):
        try:
            path = Path(self.translate_path(self.path))
            if not path.is_file():
                raise ValueError('Resource file is unavailable')
        except (ValueError, OSError):
            self.send_error(404)
            return None
        return super().send_head()

    def json_response(self, value, code=200):
        data = json.dumps(value, allow_nan=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == '/api/course/catalog':
            from lapsim.courses.library import course_library
            try:self.json_response(course_library())
            except (OSError,ValueError) as error:self.json_response({'error':str(error)},400)
            return
        if urlsplit(self.path).path == '/api/torque/example':
            from lapsim.torque_configurator import example_profile
            try:
                query=parse_qs(urlsplit(self.path).query,keep_blank_values=True,max_num_fields=2)
                if not query:value=example_profile()
                elif set(query)=={'architecture','experimental'} and query['experimental']==['1'] and len(query['architecture'])==1:
                    from lapsim.torque_configurator.policy import experimental_profile
                    value=experimental_profile(query['architecture'][0])
                elif set(query)=={'architecture'} and len(query['architecture'])==1:
                    value=example_profile(query['architecture'][0])
                else:raise ValueError('One supported architecture query is required')
                self.json_response(value.to_dict())
            except ValueError as error:self.json_response({'error':str(error)},400)
            return
        if self.path == "/api/status":
            value = {"active": False, "parameters": PARAMETERS}
            if JOB:
                alive = JOB["process"].poll() is None
                value.update(active=alive, kind=JOB["kind"], output=JOB["relative"],
                             cancelled=JOB.get("cancelled", False), exit_code=JOB["process"].poll())
                try:
                    file = confined_file(self.work_dir, (JOB['output'].name,
                        "sweep.json" if JOB["kind"] == "sweep" else "checkpoint.json"))
                    saved = read_json_bounded(file, maximum_bytes=25_000_000)
                    value["completed"] = len(saved.get("rows", saved.get("runs", {})))
                    value["total"] = saved.get("total")
                    value["saved_status"] = saved["status"]
                except (OSError, ValueError):
                    pass
            self.json_response(value)
            return
        return super().do_GET()

    def do_POST(self):
        with JOB_LOCK:
            return self.post_locked()

    def post_locked(self):
        global JOB
        origin = self.headers.get("Origin")
        port=getattr(self.server,'server_port',None)
        if type(port) is not int:raise ValueError('HTTP server port is unavailable')
        if origin and origin != f"http://127.0.0.1:{port}":
            self.json_response({"error": "Origin rejected"}, 403)
            return
        try:
            size = int(self.headers.get("Content-Length", 0))
            if not 0 < size <= 4_300_000:
                raise ValueError("bounded JSON body required")
            body = json.loads(self.rfile.read(size))
            if type(body) is not dict:
                raise ValueError("JSON object required")
            if self.path.startswith('/api/torque/'):
                from lapsim.torque_configurator.api import action
                name=self.path.rsplit('/',1)[-1]
                if name in ('preview','export','compare','export-result') and JOB and JOB['process'].poll() is None:
                    raise ValueError('Wait for the active simulator batch before running a controller preview/export')
                self.json_response(action(name,body,work_dir=self.work_dir))
                return
            if self.path == "/api/course/validate":
                from .tournament_rollout import Case, course_for
                from lapsim.courses.course_bundle import CourseBundle
                case = Case("import", course="bundle", course_bundle=body)
                bundle = CourseBundle.from_dict(body)
                track = course_for(case)
                self.json_response({"label": bundle.label, "length_m": track.length_m,
                    "geometry_sha256": bundle.geometry_sha256, "bundle_sha256": bundle.bundle_sha256})
                return
            if self.path == "/api/cancel":
                if JOB and JOB["process"].poll() is None:
                    stop_owned_worker(JOB["process"])
                    JOB["cancelled"] = True
                    # The worker is stopped, so its final atomic save can no
                    # longer race this update. Preserve every completed row/run
                    # and a completed result if it finished during cancellation.
                    saved_path = confined_file(self.work_dir, (JOB['output'].name,
                        "sweep.json" if JOB["kind"] == "sweep" else "checkpoint.json"))
                    if saved_path.exists():
                        saved = read_json_bounded(saved_path, maximum_bytes=25_000_000)
                        if saved.get("status") == "running":
                            saved["status"] = "cancelled"
                            write_text_atomic(saved_path, json.dumps(saved, allow_nan=False))
                self.json_response({"cancelled": True})
                return
            if self.path != "/api/run":
                raise ValueError("unknown action")
            if JOB and JOB["process"].poll() is None:
                raise ValueError("one batch at a time; cancel or wait")
            if getattr(sys, 'frozen', False):
                raise ValueError('Batch workers require an installed Python environment; no frozen-app module worker is available')
            kind = body["kind"]
            output = confined_file(self.work_dir, ("gui-" + uuid.uuid4().hex[:10],))
            if kind == "sweep":
                axes_from(body)
                from .tournament_rollout import Case
                Case("validate", course=body.get("course", "stadium"), course_bundle=body.get("course_bundle"),
                     reverse=body.get("reverse", False), mirror=body.get("mirror", False))
                module = "lapsim.experiments.tournament_sweep"
                args = ["--config", str(output / "request.json"), "--output", str(output)]
            elif kind == "search":
                module = "lapsim.experiments.controller_tournament"
                from .controller_tournament import specification
                spec = specification(body.get("seed", 4082025), body.get("population", 6), body.get("generations", 3), body.get("profile", "synthetic_awd"),
                    course=body.get("course", "stadium"), course_bundle=body.get("course_bundle"),
                    reverse=body.get("reverse", False), mirror=body.get("mirror", False),laps=body.get('laps',10))
                args = ["--output", str(output), "--seed", str(spec["seed"]), "--population", str(spec["population"]),
                        "--generations", str(spec["generations"]), "--profile", spec["profile"], "--wall-seconds", "600",
                        "--course", body.get("course", "stadium"),"--laps",str(body.get('laps',10))]
                if body.get("reverse", False):
                    args.append("--reverse")
                if body.get("mirror", False):
                    args.append("--mirror")
                if body.get("course_bundle") is not None:
                    args += ["--course-bundle", str(output / "course.json")]
            else:
                raise ValueError("unknown batch kind")
            output.mkdir(parents=True)
            if body.get("course_bundle") is not None:
                (output / "course.json").write_text(json.dumps(body["course_bundle"], allow_nan=False), encoding="utf-8")
            (output / "request.json").write_text(json.dumps(body), encoding="utf-8")
            env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
            source = self.resource_root / 'src'
            checkout = (source / 'lapsim/experiments/tournament_server.py').resolve() == Path(__file__).resolve()
            if checkout:
                env['PYTHONPATH'] = str(source)
            else:
                # Installed Python resolves its own distribution; a copied source
                # snapshot under _resources must not shadow the installed code.
                env.pop('PYTHONPATH', None)
            flags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS if os.name == "nt" else 0
            python = [sys.executable] + ([] if checkout else ['-I'])
            with (output / "batch.log").open("w", encoding="utf-8") as log:
                process = subprocess.Popen([*python, "-u", "-m", module, *args], cwd=self.work_dir, env=env,
                                           stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
            JOB = {"process": process, "kind": kind, "output": output,
                   "relative": 'work/' + output.relative_to(self.work_dir).as_posix()}
            self.json_response({"started": True, "output": JOB["relative"]})
        except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
            self.json_response({"error": str(error)}, 400)


def main(argv=None, *, page='web/tournament.html'):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument('--work-dir', type=Path,
                        help='Absolute writable study directory; required outside a source checkout')
    args = parser.parse_args(argv)
    if page not in ('web/tournament.html','web/torque-configurator.html'):
        raise ValueError('Unknown local entry page')
    work = resolve_work_directory(args.work_dir, resource_root=ROOT, create=True)
    handler = partial(Handler, resource_root=ROOT, work_dir=work)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"LapSim listening: http://127.0.0.1:{server.server_port}/{page}", flush=True)
    try:
        server.serve_forever()
    finally:
        try:
            if JOB and JOB["process"].poll() is None:
                stop_owned_worker(JOB["process"])
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
