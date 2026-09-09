# VHL Biology — Windows LAN Client Deployment

This handoff is for a Windows workstation running the Streamlit dashboard and
FastAPI backend from the same release directory. It is a private-LAN
installation: the dashboard is reachable on TCP port `8501`, while the
backend listens on `8000` for the dashboard's local requests.

## 1. Prerequisites

Open Windows PowerShell and verify Miniconda:

```powershell
conda --version
conda info --envs
```

If the `vhl` environment does not exist, create it with the runtime declared
by this release:

```powershell
conda create -n vhl python=3.11 -y
conda activate vhl
python --version
```

From the release directory, install the pinned packages:

```powershell
conda run -n vhl python -m pip install -r .\requirements.txt
conda run -n vhl python -m pip install -r .\backend\requirements.txt
```

The backend requirements add FastAPI, Uvicorn, multipart upload support, and
the backend's inference dependencies. Keep the release directory as the
current working directory when running the application.

## 2. Environment file

Create a local configuration copy:

```powershell
Copy-Item .\.env.example .\.env
Get-Content .\.env
```

The supplied PowerShell launchers do not parse `.env` automatically. Their
parameters are authoritative. The example values are:

```text
BACKEND_URL=http://127.0.0.1:8000
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
DASHBOARD_HOST=0.0.0.0
DASHBOARD_PORT=8501
```

Do not put credentials or client data in `.env`; it is not included by the
release builder.

## 3. Start the two processes

Use two PowerShell windows, both opened in the release directory. Start the
backend first:

```powershell
.\scripts\start_backend.ps1
```

This invokes `conda run -n vhl uvicorn backend.main:app` with bind address
`0.0.0.0` and port `8000`. To override a value, use the launcher parameters:

```powershell
.\scripts\start_backend.ps1 -BindHost 0.0.0.0 -Port 8000 -EnvironmentName vhl
```

Start the dashboard in the second window:

```powershell
.\scripts\start_dashboard.ps1
```

The dashboard launcher uses `streamlit run app.py`, binds to `0.0.0.0:8501`,
and passes `BACKEND_URL=http://127.0.0.1:8000` to the dashboard process. The
explicit form is:

```powershell
.\scripts\start_dashboard.ps1 `
  -BindHost 0.0.0.0 `
  -Port 8501 `
  -BackendUrl http://127.0.0.1:8000 `
  -EnvironmentName vhl
```

Keep both windows open. Each launcher returns a non-zero exit code if Conda or
the application fails to start.

## 4. Validate the services

From a third PowerShell window in the release directory:

```powershell
.\scripts\health_check.ps1
```

The check requests `http://127.0.0.1:8000/health` and
`http://127.0.0.1:8501/`. Both must return a 2xx status. To check explicit
URLs:

```powershell
.\scripts\health_check.ps1 `
  -BackendUrl http://127.0.0.1:8000 `
  -DashboardUrl http://127.0.0.1:8501
```

For a release smoke test, use the packaged representative sample:

```powershell
conda run -n vhl python .\scripts\smoke_test.py `
  --base-url http://127.0.0.1:8000 `
  --sample .\sample-data\representative-sample.txt `
  --manifest .\RELEASE_MANIFEST.json
```

The smoke test exercises session creation, upload, peak extraction,
classification, phase detection, and toxicity. It updates the manifest and
fails when the approved baseline or declared Python minor version is not
verified. It does not exercise BOD calibration or Excel export.

## 5. Allow LAN browser access

Run the following in an elevated PowerShell window on the host workstation:

```powershell
New-NetFirewallRule `
  -DisplayName "VHL Biology Dashboard 8501" `
  -Direction Inbound `
  -Protocol TCP `
  -LocalPort 8501 `
  -Action Allow `
  -Profile Private
```

Confirm the rule:

```powershell
Get-NetFirewallRule -DisplayName "VHL Biology Dashboard 8501"
```

The dashboard makes backend requests from the host process, so only port
`8501` is needed for normal LAN browser access. Do not expose port `8000`
unless a separate, approved client must call the internal API directly.

Discover the host's private IPv4 address:

```powershell
Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object {
    $_.IPAddress -notlike "127.*" -and
    $_.IPAddress -notlike "169.254.*" -and
    $_.PrefixOrigin -ne "WellKnown"
  } |
  Select-Object IPAddress, InterfaceAlias
```

From another device on the same LAN, open:

```text
http://<server-ip>:8501
```

Replace `<server-ip>` with the address shown for the active private network
adapter.

## 6. Stop and restart

The normal stop command for either foreground window is `Ctrl+C`.

If a window was closed without stopping its process, identify the process by
its command line, then stop the displayed PID:

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match "uvicorn backend\.main:app" } |
  Select-Object ProcessId, CommandLine
Stop-Process -Id <backend-pid>
```

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match "streamlit run app\.py" } |
  Select-Object ProcessId, CommandLine
Stop-Process -Id <dashboard-pid>
```

Restart in order by rerunning `start_backend.ps1` and then
`start_dashboard.ps1`, followed by `health_check.ps1`.

## 7. Clean-machine checklist

- [ ] Windows PowerShell can run `.ps1` files and Miniconda is installed.
- [ ] `conda --version` succeeds and the `vhl` environment uses Python 3.11.
- [ ] Both requirements files install without errors.
- [ ] The release directory contains `RELEASE_MANIFEST.json`, `model\`, and
      `sample-data\representative-sample.txt`.
- [ ] `.env` was copied from `.env.example` and contains no secret.
- [ ] Backend starts on `0.0.0.0:8000`.
- [ ] Dashboard starts on `0.0.0.0:8501`.
- [ ] `health_check.ps1` reports 2xx for both services.
- [ ] The Windows Firewall rule allows TCP 8501 on the Private profile.
- [ ] A second LAN device can open `http://<server-ip>:8501`.
- [ ] A representative analysis and report export have been checked by the
      client.

## Related handoff documents

- [Operations runbook](OPERATIONS_RUNBOOK.md)
- [Model card](MODEL_CARD.md)
- [Internal API reference](API_INTERNAL.md)
- [Release history](CHANGELOG.md)
