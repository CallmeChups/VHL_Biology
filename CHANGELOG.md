# Changelog

## 1.0.0-client — First Windows LAN client release

This release is the first documented client handoff for a Windows workstation
with Miniconda. It includes:

- PowerShell launchers for the FastAPI backend and Streamlit dashboard.
- A health check, release builder, smoke test, and SHA-256 release manifest.
- Client deployment, operations, model, and internal API documentation.

### Compatibility assumptions

- Windows PowerShell can run the supplied `.ps1` scripts.
- Miniconda provides an environment named `vhl` with Python 3.11.
- Dependencies are installed from `requirements.txt` and
  `backend\requirements.txt`.
- The release directory remains intact and is the working directory for both
  processes.
- Client browsers reach the host over a private LAN on TCP port 8501.
- Input samples are instrument TXT files with time and DO in the first two
  tab-separated columns; UTF-16 is the primary encoding.

### Known limitations

- This is a LAN-only client handoff. Public hosting is not part of the
  supported operating model.
- Session state is in memory and expires after two hours; it is lost when the
  backend restarts.
- Uploaded source files are not a durable server archive. Export reports and
  client-generated records must be backed up separately.
- The smoke test does not cover BOD calibration or Excel export.
- The approved README baseline and the latest manifest observation currently
  differ: the manifest records `acceptance_status: failed` because probability
  and toxicity do not match the approved historical values. Client acceptance
  requires review rather than an assumed pass.
