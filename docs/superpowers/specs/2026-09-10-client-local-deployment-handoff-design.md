# Client Local Deployment Handoff Design

**Date:** 2026-09-10  
**Status:** Design approved in chat; pending written-spec review

## Goal

Prepare a complete handoff package so the client can install and run the VHL Biology system on a Windows server with Conda, expose the dashboard inside the client LAN, and operate it without requiring the original development environment.

The handoff is for self-hosted local/LAN use. Docker, public Internet deployment, reverse proxies, and production-grade public API exposure are explicitly out of scope for this release.

## Runtime Architecture

The client runs two local processes:

1. FastAPI backend on `0.0.0.0:8000`.
2. Streamlit dashboard on `0.0.0.0:8501`.

The dashboard calls the backend through `BACKEND_URL`. Users on the client LAN open:

```text
http://<server-ip>:8501
```

Port 8000 remains an internal service port and is not required as the user-facing URL. The deployment guide will explain the minimal Windows Firewall rule for port 8501 and the optional LAN access rule for port 8000 when debugging is needed.

The existing production flow remains authoritative:

```text
TXT upload
  -> peak extraction
  -> classification
  -> phase detection
  -> toxicity calculation
  -> dashboard results
```

No new public API contract is introduced. The backend remains an internal implementation boundary used by the dashboard.

## Handoff Package

The release package will contain:

```text
vhl-biology-client-release/
├── app.py
├── backend/
├── src/
├── model/
├── .streamlit/
├── requirements.txt
├── requirements-frontend.txt
├── runtime.txt
├── sample-data/
├── training-artifacts/
├── scripts/
├── .env.example
├── RELEASE_MANIFEST.json
├── CLIENT_DEPLOYMENT.md
├── OPERATIONS_RUNBOOK.md
├── MODEL_CARD.md
├── API_INTERNAL.md
├── CHANGELOG.md
└── LICENSE
```

Production runtime code and model files are kept directly usable by the existing application. Sample data and training artifacts are separated from runtime files so the client can distinguish operational inputs from retraining material.

The release must exclude:

- `temp.txt` and `temp.xlsx`
- frontend log files
- `.venv`, `__pycache__`, `.pytest_cache`, and generated build/cache output
- local secrets and populated `.env` files
- unrelated personal or development-only files

Legacy scripts and notebooks are included only when they are required for client retraining or auditability. Otherwise, they are excluded from the runtime release and referenced separately as optional research material.

## Environment and Configuration

The handoff will provide one reproducible Windows/Conda setup path. It will pin or record the versions required by the current runtime, including Python, TensorFlow/Keras, CatBoost, NumPy, SciPy, pandas, scikit-learn, Plotly, Streamlit, and FastAPI dependencies.

`.env.example` documents:

- `BACKEND_URL`
- backend host and port
- dashboard host and port
- any required model/data path overrides
- safe placeholder values only

No credential, token, or machine-specific path is committed.

## Operational Documentation

`CLIENT_DEPLOYMENT.md` will cover:

1. Windows and Miniconda prerequisites.
2. Release extraction and directory layout.
3. Conda environment creation/activation.
4. Dependency installation and verification.
5. Configuration from `.env.example`.
6. Model and sample-data verification.
7. Starting backend and dashboard.
8. Windows Firewall/LAN access.
9. Finding the server IP and opening the dashboard URL.
10. Smoke-test execution.
11. Safe shutdown and restart.

`OPERATIONS_RUNBOOK.md` will cover:

- normal start/stop/restart
- log locations and interpretation
- model/data backup
- replacing a model release
- rollback to a previous release
- common dependency, port, file-encoding, and model-loading failures
- escalation information to provide when reporting an issue

`MODEL_CARD.md` will identify each runtime model, its purpose, expected input, training/evaluation context, limitations, and exact file/checksum.

`API_INTERNAL.md` will document only the backend endpoints consumed by the dashboard, their request/response shapes, health check, and local troubleshooting guidance. It will not promise a supported external integration API.

## Release Integrity

`RELEASE_MANIFEST.json` will record:

- release version
- source commit or source version
- Python and dependency versions
- runtime model filenames
- model checksums
- build date
- baseline sample and expected smoke-test outputs

The manifest is the reference for identifying exactly what the client is running.

## Validation and Acceptance

Before delivery, the release must pass:

1. Clean-environment installation on a Windows/Conda machine.
2. Backend health check.
3. Dashboard startup and LAN access.
4. Smoke test using a representative UTF-16 TXT sample.
5. End-to-end result generation for peaks, classification, and toxicity.
6. Comparison with the documented baseline result within an agreed tolerance.
7. Verification that runtime does not depend on the developer's absolute paths, local virtual environment, logs, or uncommitted secrets.

Acceptance is complete when the client can start both processes from the documented commands, access the dashboard at the server LAN URL, and reproduce the baseline pipeline result.

## Out of Scope

- Docker image or Docker Compose as a delivery requirement
- Kubernetes or cloud deployment
- public Internet exposure
- authentication, quota, and audit logging for a public API
- changing model behavior or retraining models as part of packaging
- unrelated refactoring of the analysis pipeline
