# VHL Biology — Internal API Reference

This is the API served by `backend.main:app` for the local Streamlit
dashboard. The default base URL is `http://127.0.0.1:8000`; the server binds
to `0.0.0.0:8000` when started by the supplied launcher. Session state is
in-memory and expires lazily after 7,200 seconds.

All endpoint paths below are relative to the backend base URL. A missing or
expired session consistently returns `404` with detail
`Session not found or expired`.

## `GET /health`

- **Prerequisite:** Backend process is running.
- **Success (`200`):** `{"status": "ok"}`.
- **Expected 4xx:** None is defined by the handler.

## `POST /session`

- **Prerequisite:** None.
- **Success (`200`):** `{"session_id": "<uuid>"}`.
- **Expected 4xx:** None is defined by the handler.

Use the returned ID for every following stage. A session is not persisted
across a backend restart.

## `POST /session/{session_id}/upload`

- **Prerequisite:** Existing session; multipart form field named `file`.
- **Success (`200`):**

  ```json
  {
    "sample_name": "sample",
    "signal_points": 9415,
    "do_min": 277.24,
    "do_max": 284.75,
    "do_array": [280.1, 280.2]
  }
  ```

  `do_array` contains the complete parsed DO signal; the example is
  abbreviated.
- **Expected 4xx:** `404` for an unknown/expired session. Multipart/schema
  validation can return FastAPI's `422`. The parser expects time and DO in
  the first two tab-separated columns and first attempts UTF-16.

Uploading a new file resets extracted peaks and classification for that
session.

## `POST /session/{session_id}/peaks`

- **Prerequisite:** Successful upload in the same session.
- **Success (`200`):** JSON array of peak records. Records include
  `No.peak`, `Tag`, `Doin (mV)`, `DOmin (mV)`, `DDO (mV)`, and `Sample Name`.
- **Expected 4xx:** `404` for an unknown/expired session; `409` with
  `Upload a file before extracting peaks` when no upload exists.

## `POST /session/{session_id}/classify`

- **Prerequisite:** Successful peak extraction.
- **Success (`200`):**

  ```json
  {"cls_pred": "GGA", "cls_prob": 0.784}
  ```

  The probability is the maximum value returned by the classifier.
- **Expected 4xx:** `404` for an unknown/expired session; `409` with
  `Extract peaks before classifying` when peaks are absent.

## `POST /session/{session_id}/phase`

- **Prerequisite:** Successful peak extraction and classification.
- **Success (`200`):** JSON array of peak records with `Tag` rewritten to
  phase labels (`phase1`, `transition`, or `phase2`) and a numeric
  `phase_confidence` field.
- **Expected 4xx:** `404` for an unknown/expired session; `409` with
  `Extract peaks before phase detection` or `Classify before phase detection`
  when prerequisites are missing.

## `POST /session/{session_id}/toxicity`

- **Prerequisite:** Successful phase detection.
- **Success (`200`):**

  ```json
  {
    "tox_val": 5.31,
    "stage1": "phase1",
    "stage2": "phase2",
    "s1_ddo": 5.84,
    "s2_ddo": 5.53
  }
  ```

  Nullable fields are permitted by the response schema.
- **Expected 4xx:** `404` for an unknown/expired session; `409` with
  `Run phase detection before toxicity` when phase output is absent.

## `POST /session/{session_id}/bod`

- **Prerequisite:** Successful phase detection with both `phase1` and
  `phase2` peaks.
- **Request JSON:**

  ```json
  {"bod1": 20.0, "ddo1": 11.3, "bod2": 15.0, "ddo2": 9.13}
  ```

- **Success (`200`):**

  ```json
  {"a": 0.434, "b": 2.62, "bod_phase1": 7.419, "bod_phase2": 6.7}
  ```

  Values above are shape examples; the endpoint computes them from the
  supplied calibration and session DDO values.
- **Expected 4xx:** `404` for an unknown/expired session; `409` for missing
  phase output or missing `phase1`/`phase2` peaks; `422` when the calibration
  BOD values are equal or the JSON body fails schema validation.

## `GET /session/{session_id}/export`

- **Prerequisite:** Successful peak extraction. Classification, toxicity, and
  BOD values are included when they exist; export does not require every later
  stage.
- **Success (`200`):** An XLSX download with media type
  `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` and a
  filename derived from the sample name.
- **Expected 4xx:** `404` for an unknown/expired session; `409` with
  `Nothing to export yet` when peaks are absent.

## Recommended call order

```text
POST /session
POST /session/{id}/upload
POST /session/{id}/peaks
POST /session/{id}/classify
POST /session/{id}/phase
POST /session/{id}/toxicity
POST /session/{id}/bod       (optional, requires calibration JSON)
GET  /session/{id}/export
```

The API is an internal LAN interface. Use the supplied dashboard and
PowerShell health check rather than treating these routes as a public service.
