/* The UI must create this as a module worker. No physics is implemented here. */
const PYODIDE_VERSION = "314.0.7";
const INDEX_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
let initialization = null;
let runtime = null;
let running = false;
let activeRequest = null;
let lastProgressAt = 0;
let lastPhase = null;

function status(phase, message) {
  self.postMessage({ type: "status", phase, message });
}

async function initialize() {
  status("runtime", "Loading Python and the scientific runtime…");
  const { loadPyodide } = await import(`${INDEX_URL}pyodide.mjs`);
  runtime = await loadPyodide({ indexURL: INDEX_URL });
  status("packages", "Loading NumPy, SciPy, and run-record dependencies…");
  // Matplotlib's distribution metadata is required by the unchanged standard
  // record schema. We load its package without importing a GUI or Tk backend.
  await runtime.loadPackage(["numpy", "scipy", "matplotlib"]);
  status("model", "Loading the LapSim physics and course data…");
  const manifestResponse = await fetch(new URL("./assets/runtime-manifest.json", import.meta.url));
  if (!manifestResponse.ok) throw new Error(`Runtime manifest could not load (${manifestResponse.status}).`);
  const manifest = await manifestResponse.json();
  if (manifest.protocolVersion !== 1 || manifest.pyodideVersion !== PYODIDE_VERSION) {
    throw new Error("The worker and runtime manifest versions do not match; reload the page.");
  }
  const archiveResponse = await fetch(new URL("./assets/lapsim-runtime.zip", import.meta.url));
  if (!archiveResponse.ok) throw new Error(`LapSim source archive could not load (${archiveResponse.status}).`);
  const archive = await archiveResponse.arrayBuffer();
  if (archive.byteLength > 20 * 1024 * 1024 || archive.byteLength !== manifest.archiveBytes) {
    throw new Error("LapSim source archive size does not match the release manifest.");
  }
  const digest = await crypto.subtle.digest("SHA-256", archive);
  const actualHash = Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, "0")).join("");
  if (actualHash !== manifest.archiveSha256) throw new Error("LapSim source archive integrity check failed.");
  runtime.unpackArchive(archive, "zip", { extractDir: "/lapsim" });
  runtime.globals.set("_emit_progress_json", raw => {
    const update = JSON.parse(raw);
    const now = performance.now();
    if (update.phase !== lastPhase || now - lastProgressAt >= 80 || update.completedCells === update.totalCells) {
      self.postMessage({ type: "progress", requestId: activeRequest, ...update });
      lastProgressAt = now;
      lastPhase = update.phase;
    }
  });
  await runtime.runPythonAsync(`
import sys, json
sys.frozen = True
sys._MEIPASS = '/lapsim'
sys.path[:0] = ['/lapsim/bundle/vendor', '/lapsim/bundle/src', '/lapsim/bundle/web']
from bridge import capabilities, run_simulation_json
def _web_progress(update):
    _emit_progress_json(json.dumps(update, allow_nan=False))
`);
  const metadata = JSON.parse(runtime.runPython("json.dumps(capabilities(), allow_nan=False)"));
  self.postMessage({ type: "ready", capabilities: metadata });
  return runtime;
}

function ready() {
  if (!initialization) {
    initialization = initialize().catch(error => {
      initialization = null;
      runtime = null;
      throw error;
    });
  }
  return initialization;
}

self.onmessage = async event => {
  const message = event.data;
  const requestId = message?.requestId ?? null;
  let ownsRun = false;
  try {
    if (!message || typeof message !== "object") throw new Error("A worker request must be an object.");
    if (message.type === "init") {
      await ready();
      return;
    }
    if (message.type === "cancel") {
      // A queued message cannot interrupt synchronous Wasm. The client must
      // terminate this worker to cancel an active calculation immediately.
      self.postMessage({ type: "cancelled", requestId });
      return;
    }
    if (message.type !== "run") throw new Error("Unknown worker request type.");
    if (running) throw new Error("A calculation is already running in this worker.");
    if (!(typeof requestId === "string" || Number.isSafeInteger(requestId))) throw new Error("A run requires a requestId.");
    running = true;
    ownsRun = true;
    activeRequest = requestId;
    lastPhase = null;
    lastProgressAt = 0;
    const py = await ready();
    py.globals.set("_request_json", JSON.stringify(message.settings));
    const encoded = await py.runPythonAsync("run_simulation_json(_request_json, _web_progress)");
    self.postMessage({ type: "result", requestId, result: JSON.parse(encoded) });
  } catch (error) {
    self.postMessage({ type: "error", requestId, error: { kind: error.name ?? "Error", message: String(error.message ?? error) } });
  } finally {
    if (ownsRun) {
      running = false;
      activeRequest = null;
      runtime?.globals.delete("_request_json");
    }
  }
};
