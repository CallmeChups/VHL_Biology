"""Run the client handoff pipeline against a running local backend."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import requests


def _json_response(response: requests.Response, stage: str) -> Any:
    if not 200 <= response.status_code < 300:
        detail = response.text.strip().replace("\n", " ")
        raise RuntimeError(f"{stage}: HTTP {response.status_code} ({detail[:200]})")
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(f"{stage}: response was not valid JSON") from exc


def _require_fields(body: Any, fields: tuple[str, ...], stage: str) -> None:
    if not isinstance(body, dict):
        raise RuntimeError(f"{stage}: expected a JSON object")
    missing = [field for field in fields if field not in body]
    if missing:
        raise RuntimeError(f"{stage}: missing response field(s): {', '.join(missing)}")


def _post(base_url: str, path: str, stage: str, **kwargs: Any) -> Any:
    try:
        response = requests.post(f"{base_url}{path}", timeout=120, **kwargs)
    except requests.RequestException as exc:
        raise RuntimeError(f"{stage}: request failed ({exc})") from exc
    return _json_response(response, stage)


def run_smoke_test(base_url: str, sample_path: Path) -> None:
    base_url = base_url.rstrip("/")
    if not sample_path.is_file():
        raise RuntimeError(f"sample: file not found: {sample_path}")
    if sample_path.suffix.lower() != ".txt":
        raise RuntimeError(f"sample: expected a .txt file: {sample_path}")

    session_body = _post(base_url, "/session", "session")
    _require_fields(session_body, ("session_id",), "session")
    session_id = session_body["session_id"]
    if not isinstance(session_id, str) or not session_id:
        raise RuntimeError("session: session_id was empty")
    print("PASS session")

    with sample_path.open("rb") as sample_file:
        upload_body = _post(
            base_url,
            f"/session/{session_id}/upload",
            "upload",
            files={"file": (sample_path.name, sample_file, "text/plain")},
        )
    _require_fields(upload_body, ("sample_name", "signal_points", "do_array"), "upload")
    if not upload_body["signal_points"] or not upload_body["do_array"]:
        raise RuntimeError("upload: response contained no signal points")
    print(f"PASS upload ({upload_body['signal_points']} signal points)")

    peaks_body = _post(base_url, f"/session/{session_id}/peaks", "peaks")
    if not isinstance(peaks_body, list) or not peaks_body:
        raise RuntimeError("peaks: response contained no extracted peaks")
    peak_fields = {"No.peak", "Doin (mV)", "DOmin (mV)", "DDO (mV)"}
    if not all(isinstance(row, dict) and peak_fields <= row.keys() for row in peaks_body):
        raise RuntimeError("peaks: response rows were missing required fields")
    print(f"PASS peaks ({len(peaks_body)} rows)")

    classify_body = _post(base_url, f"/session/{session_id}/classify", "classification")
    _require_fields(classify_body, ("cls_pred", "cls_prob"), "classification")
    if classify_body["cls_pred"] in (None, "") or classify_body["cls_prob"] is None:
        raise RuntimeError("classification: prediction or probability was empty")
    print(f"PASS classification ({classify_body['cls_pred']})")

    phase_body = _post(base_url, f"/session/{session_id}/phase", "phase")
    if not isinstance(phase_body, list) or not phase_body:
        raise RuntimeError("phase: response contained no phase rows")
    phase_fields = {"Tag", "phase_confidence"}
    if not all(isinstance(row, dict) and phase_fields <= row.keys() for row in phase_body):
        raise RuntimeError("phase: response rows were missing required fields")
    print(f"PASS phase ({len(phase_body)} rows)")

    toxicity_body = _post(base_url, f"/session/{session_id}/toxicity", "toxicity")
    _require_fields(toxicity_body, ("tox_val", "stage1", "stage2"), "toxicity")
    if toxicity_body["tox_val"] is None:
        raise RuntimeError("toxicity: tox_val was null")
    print(f"PASS toxicity ({toxicity_body['tox_val']}%)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Backend base URL, e.g. http://127.0.0.1:8000")
    parser.add_argument("--sample", required=True, type=Path, help="Representative UTF-16 TXT sample")
    args = parser.parse_args()

    try:
        run_smoke_test(args.base_url, args.sample)
    except RuntimeError as exc:
        print(f"FAIL {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
