# Client Local Deployment Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a clean, reproducible Windows/Conda release package that the client can run on its LAN and operate through the Streamlit URL.

**Architecture:** Keep the existing two-process boundary: FastAPI serves the internal analysis API on port 8000 and Streamlit serves the user-facing dashboard on port 8501. Add Windows-oriented launch, health, release-manifest, and packaging helpers around the current runtime without changing model behavior or introducing Docker as a delivery requirement.

**Tech Stack:** Python 3.11, Conda, FastAPI/Uvicorn, Streamlit, PowerShell, existing pinned Python dependencies, SHA-256 release checksums.

**Spec:** `docs/superpowers/specs/2026-09-10-client-local-deployment-handoff-design.md`

## Global Constraints

- The handoff targets self-hosted Windows/Conda and client LAN access.
- Docker, Kubernetes, public Internet exposure, reverse proxies, and a supported external API are out of scope.
- The backend runs on `0.0.0.0:8000`; the dashboard runs on `0.0.0.0:8501`.
- The dashboard uses `BACKEND_URL` to call the backend.
- Runtime behavior and model outputs must remain unchanged.
- Do not package `temp.txt`, `temp.xlsx`, logs, caches, virtual environments, secrets, or unrelated development files.
- The release must identify source version, dependency versions, runtime model files, SHA-256 checksums, build date, and baseline smoke-test output.
- Every validation must cover TXT upload through peaks, classification, phase detection, and toxicity.

---

## File Map

- Create: `scripts/start_backend.ps1` — launch the internal FastAPI service with configurable host/port.
- Create: `scripts/start_dashboard.ps1` — launch the Streamlit dashboard with configurable host/port and backend URL.
- Create: `scripts/health_check.ps1` — verify backend health and dashboard reachability.
- Create: `scripts/build_release.ps1` — assemble an allowlisted client release and generate its manifest/checksums.
- Create: `scripts/smoke_test.py` — run the representative end-to-end pipeline against the local backend.
- Create: `.env.example` — document safe local runtime configuration.
- Create: `RELEASE_MANIFEST.json` — generated release metadata format/example.
- Create: `CLIENT_DEPLOYMENT.md` — clean Windows/Conda installation and LAN deployment guide.
- Create: `OPERATIONS_RUNBOOK.md` — daily operation, backup, upgrade, rollback, and troubleshooting guide.
- Create: `MODEL_CARD.md` — runtime model inventory, inputs, evaluation context, limitations, and checksums.
- Create: `API_INTERNAL.md` — internal dashboard-to-backend endpoint contract and health check.
- Create: `CHANGELOG.md` — client release history and compatibility notes.
- Modify: `.gitignore` — exclude generated logs and release output while keeping release source files intentional.
- Modify: `README.md` — link the client handoff documents and state the Windows LAN run path.
- Test/validate: `backend/tests/` and existing `tests/` — preserve current test coverage and add only focused checks needed for release tooling.

## Task 1: Add Windows Runtime Configuration and Launch Scripts

**Files:**
- Create: `scripts/start_backend.ps1`
- Create: `scripts/start_dashboard.ps1`
- Create: `scripts/health_check.ps1`
- Create: `.env.example`
- Modify: `.gitignore`

**Interfaces:**
- `start_backend.ps1` accepts optional `-Host`, `-Port`, and `-EnvironmentName` parameters and runs `uvicorn backend.main:app`.
- `start_dashboard.ps1` accepts optional `-Host`, `-Port`, `-BackendUrl`, and `-EnvironmentName` parameters and runs Streamlit with `BACKEND_URL`.
- `health_check.ps1` accepts optional backend/dashboard URLs and exits non-zero when either expected HTTP check fails.

- [ ] **Step 1: Write the script contract checks**

Create a PowerShell validation block in the task work session that checks each script exposes the documented parameters and contains no Unix-only startup command:

```powershell
$scripts = @(
  "scripts\start_backend.ps1",
  "scripts\start_dashboard.ps1",
  "scripts\health_check.ps1"
)
foreach ($script in $scripts) {
  if (-not (Test-Path $script)) { throw "Missing $script" }
  $content = Get-Content $script -Raw
  if ($content -match "bash|/bin/sh|docker run") {
    throw "Windows script contains a non-Windows launcher: $script"
  }
}
```

- [ ] **Step 2: Run the checks before implementation**

Run:

```powershell
pwsh -NoProfile -Command "& { <validation block from Step 1> }"
```

Expected: FAIL because the three scripts do not exist yet.

- [ ] **Step 3: Implement the backend launcher**

Use a parameterized PowerShell script with explicit defaults:

```powershell
param(
  [string]$Host = "0.0.0.0",
  [int]$Port = 8000,
  [string]$EnvironmentName = "vhl"
)

conda run -n $EnvironmentName uvicorn backend.main:app --host $Host --port $Port
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

The script must resolve paths relative to the repository/release root and fail with a clear message if `conda` is unavailable.

- [ ] **Step 4: Implement the dashboard launcher**

Set `BACKEND_URL` for the child process and launch Streamlit with LAN-safe defaults:

```powershell
param(
  [string]$Host = "0.0.0.0",
  [int]$Port = 8501,
  [string]$BackendUrl = "http://127.0.0.1:8000",
  [string]$EnvironmentName = "vhl"
)

$env:BACKEND_URL = $BackendUrl
conda run -n $EnvironmentName streamlit run app.py `
  --server.address $Host `
  --server.port $Port `
  --server.headless true
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

- [ ] **Step 5: Implement health checks and configuration template**

The health script must call `GET /health`, call the dashboard root URL, print both response statuses, and exit non-zero on connection or HTTP failure. `.env.example` must contain placeholders for `BACKEND_URL`, `BACKEND_HOST`, `BACKEND_PORT`, `DASHBOARD_HOST`, and `DASHBOARD_PORT`, with no secrets or machine-specific paths.

- [ ] **Step 6: Add generated-output ignores and rerun validation**

Ignore release archives, generated manifests/checksums, runtime logs, and local environment files without ignoring the checked-in scripts or documentation. Run the contract checks and PowerShell syntax validation:

```powershell
pwsh -NoProfile -Command "& { Get-Command .\scripts\start_backend.ps1 -ErrorAction Stop; Get-Command .\scripts\start_dashboard.ps1 -ErrorAction Stop; Get-Command .\scripts\health_check.ps1 -ErrorAction Stop }"
```

Expected: all scripts parse and are discoverable.

- [ ] **Step 7: Commit**

```powershell
git add scripts .env.example .gitignore
git commit -m "feat: add Windows local runtime launchers"
```

## Task 2: Add Release Assembly, Manifest, and Smoke Test

**Files:**
- Create: `scripts/build_release.ps1`
- Create: `scripts/smoke_test.py`
- Create: `RELEASE_MANIFEST.json`
- Modify: `.gitignore`

**Interfaces:**
- `build_release.ps1 -Version <version> -OutputDirectory <path>` creates an allowlisted release directory/archive and writes `RELEASE_MANIFEST.json`.
- The manifest contains `release_version`, `source_commit`, `build_date_utc`, `python_version`, `dependencies`, `runtime_models`, `checksums`, and `baseline`.
- `smoke_test.py --base-url <url> --sample <path>` creates a session, uploads one TXT file, runs peaks/classification/phase/toxicity, and exits non-zero on any failed stage.

- [ ] **Step 1: Define the manifest fixture and failing parser test**

Create a focused test in `backend/tests/test_release_manifest.py` that loads a generated manifest and asserts required fields and model checksum shape:

```python
import json
from pathlib import Path


def test_release_manifest_has_runtime_identity(tmp_path: Path):
    manifest = {
        "release_version": "1.0.0",
        "source_commit": "abc123",
        "build_date_utc": "2026-09-10T00:00:00Z",
        "python_version": "3.11",
        "dependencies": {"catboost": "1.2.8"},
        "runtime_models": ["model/catboost_model.cbm"],
        "checksums": {"model/catboost_model.cbm": "a" * 64},
        "baseline": {"sample": "sample.txt", "status": "passed"},
    }
    path = tmp_path / "RELEASE_MANIFEST.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert set(("release_version", "source_commit", "build_date_utc",
                "python_version", "dependencies", "runtime_models",
                "checksums", "baseline")) <= loaded.keys()
    assert len(loaded["checksums"]["model/catboost_model.cbm"]) == 64
```

- [ ] **Step 2: Run the fixture test**

Run:

```powershell
pytest backend/tests/test_release_manifest.py -q
```

Expected: FAIL because the test file and release tooling do not exist.

- [ ] **Step 3: Implement allowlisted release assembly**

`build_release.ps1` must copy only runtime files, model files, selected sample data, selected training artifacts, scripts, and client documentation. It must explicitly reject `temp.txt`, `temp.xlsx`, logs, caches, `.venv`, `.env`, and untracked secrets. Use `Get-FileHash -Algorithm SHA256` for model files and `git rev-parse HEAD` for source identity. Do not copy the entire repository recursively.

- [ ] **Step 4: Implement manifest generation**

Write the manifest with stable UTF-8 JSON and include each runtime model's relative path and checksum. Read dependency versions from the pinned requirements files and record the Python runtime from `runtime.txt` plus the active interpreter when building. The baseline must identify the representative TXT sample and the expected smoke-test result rather than inventing new accuracy values.

- [ ] **Step 5: Implement the smoke-test client**

Use the existing internal endpoint sequence:

```python
session = post("/session").json()["session_id"]
post(f"/session/{session}/upload", files={"file": sample_file})
post(f"/session/{session}/peaks")
post(f"/session/{session}/classify")
post(f"/session/{session}/phase")
toxicity = post(f"/session/{session}/toxicity").json()
assert toxicity["tox_val"] is not None
```

Print a concise stage-by-stage result and raise on non-2xx responses or missing required response fields. Do not alter `src/` model or pipeline behavior to make the smoke test pass.

- [ ] **Step 6: Run focused tests and a local smoke test**

Run:

```powershell
pytest backend/tests/test_release_manifest.py backend/tests/test_main.py backend/tests/test_pipeline.py -q
python scripts\smoke_test.py --base-url http://127.0.0.1:8000 --sample <representative-utf16-sample.txt>
```

Expected: manifest test passes; smoke test passes only while the backend is running and reports peaks, classification, phase, and toxicity.

- [ ] **Step 7: Commit**

```powershell
git add scripts\build_release.ps1 scripts\smoke_test.py backend\tests\test_release_manifest.py RELEASE_MANIFEST.json .gitignore
git commit -m "feat: add client release manifest and smoke test"
```

## Task 3: Write Client Deployment and Operations Documentation

**Files:**
- Create: `CLIENT_DEPLOYMENT.md`
- Create: `OPERATIONS_RUNBOOK.md`
- Create: `MODEL_CARD.md`
- Create: `API_INTERNAL.md`
- Create: `CHANGELOG.md`
- Modify: `README.md`

**Interfaces:**
- Documentation commands must match the scripts from Task 1 exactly.
- API endpoint names and response expectations must match `backend/main.py`, `backend/pipeline.py`, and `backend/schemas.py`.
- Model names and runtime paths must match the files used by the production backend.

- [ ] **Step 1: Inventory actual commands, endpoints, and models**

Before writing prose, extract the current endpoint list from `backend/pipeline.py`, model paths from the runtime code, and dependency commands from the requirements files. Record the representative sample and baseline output already documented in `README.md`; do not create a contradictory baseline.

- [ ] **Step 2: Write the installation/deployment guide**

`CLIENT_DEPLOYMENT.md` must give copyable PowerShell commands for Miniconda verification, environment creation, dependency installation, `.env` setup, backend start, dashboard start, health checks, Windows Firewall port 8501, server-IP discovery, and LAN browser access. Include a clean-machine checklist and explicit commands for stopping/restarting each process.

- [ ] **Step 3: Write the operations runbook**

Document normal operation, log capture, backups of `model/` and client-generated data, release replacement, rollback by restoring the prior release directory, and fixes for backend-unreachable, port-in-use, model-load, UTF-16 parsing, and missing-dependency failures. Every troubleshooting entry must name the observable symptom, a concrete command/check, and the recovery action.

- [ ] **Step 4: Write the model and internal API references**

`MODEL_CARD.md` must list each runtime model, file path, role, input expectations, training/evaluation context, known limitations, and checksum source. `API_INTERNAL.md` must document `/health`, session creation, upload, peaks, classify, phase, toxicity, BOD, and export endpoints with method, prerequisite, success shape, and expected 4xx behavior.

- [ ] **Step 5: Update the root README and changelog**

Add a clearly labeled Windows LAN client handoff section to `README.md` linking the four client documents and the release scripts. `CHANGELOG.md` must identify the first client release, compatibility assumptions, and any known limitations without claiming Docker/public deployment support.

- [ ] **Step 6: Validate documentation references**

Run searches that fail on stale or unsupported instructions:

```powershell
rg -n "docker|render|railway|localhost:3000|temp\.xlsx|temp\.txt" CLIENT_DEPLOYMENT.md OPERATIONS_RUNBOOK.md MODEL_CARD.md API_INTERNAL.md
```

Expected: no Docker/cloud instructions in the client deployment docs; temporary files appear only when explicitly listed as excluded; endpoint and port references match the approved LAN design.

- [ ] **Step 7: Commit**

```powershell
git add CLIENT_DEPLOYMENT.md OPERATIONS_RUNBOOK.md MODEL_CARD.md API_INTERNAL.md CHANGELOG.md README.md
git commit -m "docs: add client deployment and operations handoff"
```

## Task 4: Validate the Clean Release and Handoff Acceptance

**Files:**
- Validate: release output produced by `scripts/build_release.ps1`
- Validate: `scripts/health_check.ps1`, `scripts/smoke_test.py`
- Validate: existing `backend/tests/` and `tests/`

**Interfaces:**
- The release must run without the developer's absolute paths, `.venv`, logs, or populated `.env`.
- The client URL must be `http://<server-ip>:8501`.

- [ ] **Step 1: Run the existing targeted backend tests**

Run:

```powershell
pytest backend/tests tests -q
```

Expected: all existing tests pass; any failure caused by the handoff changes must be fixed before packaging.

- [ ] **Step 2: Build a versioned release from a clean output directory**

Run:

```powershell
Remove-Item -Recurse -Force .\release-test -ErrorAction SilentlyContinue
.\scripts\build_release.ps1 -Version 1.0.0-client -OutputDirectory .\release-test
```

Expected: the output contains only the allowlisted runtime, models, sample/training artifacts, scripts, manifest, and client documents.

- [ ] **Step 3: Audit release exclusions and path portability**

Run:

```powershell
if (Get-ChildItem .\release-test -Recurse -Force -File |
    Where-Object { $_.Name -in @("temp.txt","temp.xlsx",".env") -or $_.FullName -match "__pycache__|\.venv|pytest_cache|frontend_logs" }) {
  throw "Forbidden release file found"
}
rg -n "D:\\|C:\\Users|/home/|/workspace/" .\release-test
```

Expected: no forbidden files and no developer-specific absolute paths.

- [ ] **Step 4: Perform clean-environment installation**

Create or use a fresh Conda environment, install from the release dependency files, start the backend and dashboard with the release scripts, and run:

```powershell
.\scripts\health_check.ps1
python .\scripts\smoke_test.py --base-url http://127.0.0.1:8000 --sample .\sample-data\<sample>.txt
```

Expected: backend health, dashboard reachability, and all four pipeline stages pass.

- [ ] **Step 5: Verify LAN access**

From a second machine on the same LAN, open `http://<server-ip>:8501`, upload the representative TXT file, and confirm the displayed result matches the documented baseline. Confirm port 8000 is not required for ordinary users.

- [ ] **Step 6: Record final manifest and acceptance evidence**

Update the generated manifest baseline with the verified sample result, record the environment/package versions used, save the exact release version, and attach the command outputs/screenshots required by the client acceptance checklist.

- [ ] **Step 7: Commit final handoff metadata**

```powershell
git add RELEASE_MANIFEST.json CHANGELOG.md
git commit -m "chore: record validated client release"
```

## Self-Review Checklist

- [ ] Spec coverage: runtime architecture, package exclusions, Windows/Conda setup, operational docs, model/API references, manifest checksums, smoke test, LAN acceptance, and out-of-scope Docker/public deployment are all represented above.
- [ ] Placeholder scan: no step relies on “TBD”, “TODO”, or unspecified validation.
- [ ] Interface consistency: script names, ports, `BACKEND_URL`, endpoint sequence, manifest keys, and release paths match across tasks.
- [ ] Scope check: all work is one handoff subsystem; no independent model retraining or public API project is included.
