# VHL Biology — Operations Runbook

## Operating assumptions

- The application runs from one Windows release directory in the `vhl` Conda
  environment.
- The backend is `backend.main:app` on `0.0.0.0:8000`.
- The Streamlit dashboard is `app.py` on `0.0.0.0:8501`.
- Analysis session state is in memory. `backend/session_store.py` expires
  sessions lazily after 7,200 seconds; uploads are not a durable server
  archive.
- Keep source releases separate. Do not overwrite a known-good release while
  it is running.

## Normal start and stop

1. Open two PowerShell windows in the release directory.
2. Run `.\scripts\start_backend.ps1`.
3. Run `.\scripts\start_dashboard.ps1`.
4. From a third window, run `.\scripts\health_check.ps1`.
5. Browse to `http://<server-ip>:8501` from the client LAN.
6. Stop each foreground process with `Ctrl+C` when maintenance is required.

After stopping, restart the backend first, then the dashboard, and rerun the
health check. Keep the application windows visible during a client session so
startup and runtime errors are not missed.

## Log capture

The launchers write application output to their PowerShell host; there is no
application log service in this release. Capture a maintenance run explicitly:

```powershell
New-Item -ItemType Directory -Path .\operations -Force | Out-Null
.\scripts\start_backend.ps1 *>&1 |
  Tee-Object -FilePath (".\operations\backend-" + (Get-Date -Format yyyyMMdd-HHmmss) + ".log")
```

Run the equivalent command for the dashboard in its own window:

```powershell
.\scripts\start_dashboard.ps1 *>&1 |
  Tee-Object -FilePath (".\operations\dashboard-" + (Get-Date -Format yyyyMMdd-HHmmss) + ".log")
```

Stop with `Ctrl+C`; preserve the captured files with the incident or release
record. Do not copy captured logs into a release package.

## Backups

The release builder packages model files and code, but not local secrets,
temporary upload targets, caches, or log files. Back up the complete `model`
directory and client-generated reports separately:

```powershell
New-Item -ItemType Directory -Path .\backups -Force | Out-Null
Compress-Archive -Path .\model -DestinationPath (
  ".\backups\model-" + (Get-Date -Format yyyyMMdd-HHmmss) + ".zip"
)
```

Copy exported `.xlsx` reports and any client-maintained analysis records into
a dated backup directory. Verify the archive can be opened before deleting an
older copy. The in-memory session store is not recoverable after a restart, so
export reports before planned maintenance.

## Release replacement

### Maintainer-side release building

Only a maintainer with the complete source repository should run the release
builder. It reads source-repository data, including the representative sample
under `data\GGA\...`, and records the source Git commit; a deployed client
release does not contain those source paths and must not be used to build
another release.

From the **source repository root**, a maintainer can assemble a new release
into a new or empty directory:

```powershell
.\scripts\build_release.ps1 `
  -Version 1.0.0-client `
  -OutputDirectory .\releases\1.0.0-client
```

The builder writes `RELEASE_MANIFEST.json`, SHA-256 model checksums, runtime
metadata, and the expected representative baseline. The maintainer should run
the backend, dashboard, health check, and smoke test against the assembled
directory before supplying it to the client.

### Client-side replacement from a supplied release

The client receives an already assembled release directory. Do not run
`build_release.ps1` on the client. Keep the current release unchanged and copy
the supplied directory to a new path, for example:

Run these replacement snippets from a workspace directory that contains the
`incoming` and `releases` folders.

```powershell
$ReleaseWorkspace = (Get-Location).Path
$SuppliedRelease = Join-Path $ReleaseWorkspace "incoming\1.0.1-client"
$NewRelease = Join-Path $ReleaseWorkspace "releases\1.0.1-client"
if (-not (Test-Path "$SuppliedRelease\RELEASE_MANIFEST.json" -PathType Leaf)) {
  throw "Supplied release is missing RELEASE_MANIFEST.json"
}
if (-not (Test-Path "$SuppliedRelease\scripts\start_backend.ps1" -PathType Leaf)) {
  throw "Supplied release is missing its launcher scripts"
}
if (Test-Path $NewRelease) {
  throw "New release directory already exists; choose a new path"
}
New-Item -ItemType Directory -Path $NewRelease -Force | Out-Null
Copy-Item -Path (Join-Path $SuppliedRelease "*") `
  -Destination $NewRelease -Recurse -Force
$SuppliedRelease = $NewRelease
```

Stop the processes in the current release, then start the supplied release
without deleting the prior directory:

```powershell
# In each running application window:
# Ctrl+C

$NewRelease = Join-Path (Get-Location).Path "releases\1.0.1-client"
Set-Location $NewRelease
.\scripts\start_backend.ps1
```

In a second PowerShell window:

```powershell
$NewRelease = Join-Path (Get-Location).Path "releases\1.0.1-client"
Set-Location $NewRelease
.\scripts\start_dashboard.ps1
```

From a third window, validate the replacement before directing users to it:

```powershell
$NewRelease = Join-Path (Get-Location).Path "releases\1.0.1-client"
Set-Location $NewRelease
.\scripts\health_check.ps1
conda run -n vhl python .\scripts\smoke_test.py `
  --base-url http://127.0.0.1:8000 `
  --sample .\sample-data\representative-sample.txt `
  --manifest .\RELEASE_MANIFEST.json
```

Keep the previous release directory until the client accepts the replacement.
The active release is the directory whose launcher windows are running.

## Rollback

1. Stop the backend and dashboard in the active release.
2. Record the failing release version and preserve its manifest and logs.
3. Set a variable to the prior, known-good release directory and verify its
   manifest:

   ```powershell
   $PriorRelease = "C:\VHL\releases\1.0.0-client"
   Test-Path "$PriorRelease\RELEASE_MANIFEST.json" -PathType Leaf
   ```

4. In one PowerShell window, change to that directory and start its backend:

   ```powershell
   Set-Location "C:\VHL\releases\1.0.0-client"
   .\scripts\start_backend.ps1
   ```

   In a second window, start its dashboard:

   ```powershell
   Set-Location "C:\VHL\releases\1.0.0-client"
   .\scripts\start_dashboard.ps1
   ```

5. In a third window, run the health check and a representative analysis from
   the prior directory:

   ```powershell
   Set-Location "C:\VHL\releases\1.0.0-client"
   .\scripts\health_check.ps1
   conda run -n vhl python .\scripts\smoke_test.py `
     --base-url http://127.0.0.1:8000 `
     --sample .\sample-data\representative-sample.txt `
     --manifest .\RELEASE_MANIFEST.json
   ```
6. Restore client reports from the backup if they were created in the failed
   release directory.

Rollback is a directory switch; do not copy model files selectively between
versions unless the manifest and checksums are revalidated.

## Alternate dashboard port

If port `8501` is unavailable, choose one dashboard port and use it in every
dashboard-facing setting. The backend port can remain `8000`; the dashboard
launcher passes `-BackendUrl` to the app as `BACKEND_URL`:

In the backend PowerShell window:

```powershell
.\scripts\start_backend.ps1 -Port 8000
```

In the dashboard PowerShell window:

```powershell
.\scripts\start_dashboard.ps1 `
  -Port 8851 `
  -BackendUrl "http://127.0.0.1:8000"
```

In a third PowerShell window, the matching health-check URLs are:

```powershell
.\scripts\health_check.ps1 `
  -BackendUrl "http://127.0.0.1:8000" `
  -DashboardUrl "http://127.0.0.1:8851"
```

Run the matching firewall rule in elevated PowerShell:

```powershell
$DashboardPort = 8851
New-NetFirewallRule `
  -DisplayName "VHL Biology Dashboard $DashboardPort" `
  -Direction Inbound `
  -Protocol TCP `
  -LocalPort $DashboardPort `
  -Action Allow `
  -Profile Private
```

If the backend port is also changed, pass the same new value to
`start_backend.ps1 -Port`, `start_dashboard.ps1 -BackendUrl
http://127.0.0.1:<backend-port>`, and `health_check.ps1 -BackendUrl`; update
any approved backend firewall rule separately. Clients must browse to
`http://<server-ip>:<dashboard-port>` (for example,
`http://192.168.1.20:8851`), not port `8501`.

## Troubleshooting

### Backend unreachable

- **Symptom:** The dashboard reports that the backend is unavailable, or
  `health_check.ps1` cannot get `/health`.
- **Check:** `Invoke-WebRequest http://127.0.0.1:8000/health -UseBasicParsing`.
- **Recovery:** Start `.\scripts\start_backend.ps1` from the release directory
  in the `vhl` environment. If a non-default port was selected, restart the
  dashboard with `-BackendUrl http://127.0.0.1:<port>` and rerun the health
  check with the same URL.

### Port already in use

- **Symptom:** Uvicorn or Streamlit exits with an address/port-in-use error.
- **Check:** `Get-NetTCPConnection -LocalPort 8000,8501 -State Listen |
  Select-Object LocalPort,OwningProcess`.
- **Recovery:** Inspect the owning PID with
  `Get-Process -Id <pid>`. Stop only the confirmed stale process with
  `Stop-Process -Id <pid>`, or choose another port and pass the matching
  `-Port`/`-BackendUrl` values to the launchers.

### Model-load failure

- **Symptom:** Classification or phase detection fails while the backend is
  running, commonly with a missing-file or model deserialization error.
- **Check:** `Test-Path .\model\catboost_model.cbm`,
  `Test-Path .\model\label_encoder_classes.npy`, and
  `Test-Path .\model\phase_detector_metal.pkl`. Compare
  `Get-FileHash .\model\catboost_model.cbm -Algorithm SHA256` with the
  corresponding entry in `RELEASE_MANIFEST.json`.
- **Recovery:** Stop both processes, restore the complete `model` directory
  from the prior release or a verified backup, start from the release root,
  and rerun the smoke test.

### UTF-16 parsing failure

- **Symptom:** Upload succeeds but signal parsing or peak extraction fails, or
  the sample reports no usable signal.
- **Check:** Confirm the file is tab-separated with time in column 1 and DO in
  column 2; inspect the first bytes with
  `Format-Hex .\sample-data\representative-sample.txt -Count 16`.
- **Recovery:** Re-export the instrument file as UTF-16 tab-separated text with
  numeric time and DO columns, upload it again, and rerun the pipeline from a
  new session. The parser has a fallback for files without a Unicode header,
  but it still requires two numeric columns.

### Missing dependency

- **Symptom:** A launcher cannot import FastAPI, Uvicorn, Streamlit, CatBoost,
  or another required module.
- **Check:** `conda run -n vhl python -c "import fastapi, uvicorn, streamlit, catboost; print('imports ok')"`
- **Recovery:** From the release directory, rerun
  `conda run -n vhl python -m pip install -r .\requirements.txt` and
  `conda run -n vhl python -m pip install -r .\backend\requirements.txt`.
  Restart both processes and run the health check.

## Baseline and acceptance note

The approved historical README baseline for the representative sample is 20
peaks, classification `GGA` at probability 0.784, and toxicity 5.31%.
`RELEASE_MANIFEST.json` records the latest smoke observation separately. Its
current observation is 20 peaks, classification `gga`, probability
0.7018118473814843, and toxicity 10.05%, with acceptance status `failed`
because the probability and toxicity do not match the approved baseline and
the runtime check is unverified. Treat that release as requiring review; do
not report it as a passed client acceptance.
