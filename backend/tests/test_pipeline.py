# backend/tests/test_pipeline.py
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_create_session_returns_session_id():
    resp = client.post("/session")
    assert resp.status_code == 200
    body = resp.json()
    assert "session_id" in body
    assert len(body["session_id"]) > 0


def test_unknown_session_id_returns_404():
    resp = client.get("/session/does-not-exist/export")
    assert resp.status_code == 404


SAMPLE_TXT = "data/GGA/File txt/N4-VS1-25-03-2024/10-5/N4-10-5-01042024-Q=49.81mL_phút-3.txt"


def _new_session() -> str:
    return client.post("/session").json()["session_id"]


def test_upload_returns_signal_stats():
    sid = _new_session()
    with open(SAMPLE_TXT, "rb") as f:
        resp = client.post(f"/session/{sid}/upload", files={"file": ("sample.txt", f, "text/plain")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["signal_points"] > 0
    assert body["do_min"] <= body["do_max"]
    assert len(body["do_array"]) == body["signal_points"]


def test_upload_missing_session_returns_404():
    with open(SAMPLE_TXT, "rb") as f:
        resp = client.post("/session/does-not-exist/upload", files={"file": ("sample.txt", f, "text/plain")})
    assert resp.status_code == 404


def _session_with_upload() -> str:
    sid = _new_session()
    with open(SAMPLE_TXT, "rb") as f:
        client.post(f"/session/{sid}/upload", files={"file": ("sample.txt", f, "text/plain")})
    return sid


def test_peaks_returns_rows_with_ddo():
    sid = _session_with_upload()
    resp = client.post(f"/session/{sid}/peaks")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) > 0
    assert "DDO (mV)" in rows[0]


def test_peaks_without_upload_returns_409():
    sid = _new_session()
    resp = client.post(f"/session/{sid}/peaks")
    assert resp.status_code == 409


def _session_with_peaks() -> str:
    sid = _session_with_upload()
    client.post(f"/session/{sid}/peaks")
    return sid


def test_classify_returns_prediction():
    sid = _session_with_peaks()
    resp = client.post(f"/session/{sid}/classify")
    assert resp.status_code == 200
    body = resp.json()
    assert body["cls_pred"].lower() in ("gga", "metal")
    assert 0.0 <= body["cls_prob"] <= 1.0


def test_classify_without_peaks_returns_409():
    sid = _new_session()
    resp = client.post(f"/session/{sid}/classify")
    assert resp.status_code == 409


def _session_with_classification() -> str:
    sid = _session_with_peaks()
    client.post(f"/session/{sid}/classify")
    return sid


def test_phase_tags_peaks():
    sid = _session_with_classification()
    resp = client.post(f"/session/{sid}/phase")
    assert resp.status_code == 200
    rows = resp.json()
    tags = {row["Tag"] for row in rows}
    assert tags <= {"phase1", "transition", "phase2"}


def test_phase_without_classification_uses_generic_detector():
    sid = _session_with_peaks()
    resp = client.post(f"/session/{sid}/phase")
    assert resp.status_code == 200
    rows = resp.json()
    assert {row["Tag"] for row in rows} <= {"phase1", "transition", "phase2"}


def _session_with_phase() -> str:
    sid = _session_with_classification()
    client.post(f"/session/{sid}/phase")
    return sid


def test_toxicity_returns_value():
    sid = _session_with_phase()
    resp = client.post(f"/session/{sid}/toxicity")
    assert resp.status_code == 200
    body = resp.json()
    assert body["stage1"] is not None
    assert body["stage2"] is not None


def test_toxicity_without_phase_returns_409():
    sid = _session_with_classification()
    resp = client.post(f"/session/{sid}/toxicity")
    assert resp.status_code == 409


def test_bod_calibration_returns_values():
    sid = _session_with_phase()
    resp = client.post(
        f"/session/{sid}/bod",
        json={"bod1": 20.0, "ddo1": 11.3, "bod2": 15.0, "ddo2": 9.13},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "bod_phase1" in body and "bod_phase2" in body


def test_bod_calibration_equal_bod_values_returns_422():
    sid = _session_with_phase()
    resp = client.post(
        f"/session/{sid}/bod",
        json={"bod1": 20.0, "ddo1": 11.3, "bod2": 20.0, "ddo2": 9.13},
    )
    assert resp.status_code == 422


def test_bod_calibration_without_phase_returns_409():
    sid = _session_with_classification()
    resp = client.post(
        f"/session/{sid}/bod",
        json={"bod1": 20.0, "ddo1": 11.3, "bod2": 15.0, "ddo2": 9.13},
    )
    assert resp.status_code == 409


def test_export_returns_xlsx():
    sid = _session_with_phase()
    client.post(f"/session/{sid}/toxicity")
    resp = client.get(f"/session/{sid}/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def test_export_without_peaks_returns_409():
    sid = _new_session()
    resp = client.get(f"/session/{sid}/export")
    assert resp.status_code == 409


def test_export_with_non_ascii_filename_returns_200():
    sid = _new_session()
    with open(SAMPLE_TXT, "rb") as f:
        client.post(
            f"/session/{sid}/upload",
            files={"file": ("mẫu-thử-nghiệm.txt", f, "text/plain")},
        )
    client.post(f"/session/{sid}/peaks")
    client.post(f"/session/{sid}/classify")
    client.post(f"/session/{sid}/phase")
    client.post(f"/session/{sid}/toxicity")
    resp = client.get(f"/session/{sid}/export")
    assert resp.status_code == 200
