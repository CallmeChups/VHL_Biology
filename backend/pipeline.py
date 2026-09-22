# backend/pipeline.py
"""Router: one endpoint per analysis pipeline stage, wrapping src/ functions."""
import os
import tempfile
from typing import Any, Dict
from urllib.parse import quote

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from backend.schemas import (
    BodCalibrationRequest,
    BodResponse,
    ClassifyResponse,
    SessionCreateResponse,
    ToxicityResponse,
    UploadResponse,
)
from backend.session_store import store
from src.export_excel import generate_excel_report
from src.phase_detector import update_phase_tags
from src.utils import calculate_bod_from_calibration, calculate_toxicity, catboost_inference_from_csv, extract_peaks_from_txt

router = APIRouter()


def _safe_content_disposition(filename: str) -> str:
    ascii_fallback = filename.encode("ascii", "ignore").decode("ascii").replace('"', "") or "report.xlsx"
    utf8_quoted = quote(filename)
    return f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{utf8_quoted}'


def require_session(session_id: str) -> Dict[str, Any]:
    try:
        return store.get(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found or expired")


@router.post("/session", response_model=SessionCreateResponse)
def create_session():
    session_id = store.create()
    return SessionCreateResponse(session_id=session_id)


@router.get("/session/{session_id}/export")
def export_report(session_id: str):
    session = require_session(session_id)
    peaks_df = session.get("peaks_df")
    if peaks_df is None:
        raise HTTPException(status_code=409, detail="Nothing to export yet")

    buffer = generate_excel_report(
        sample_name=session.get("sample_name", "sample"),
        peaks_df=peaks_df,
        classification=session.get("cls_pred") or "unknown",
        probability=session.get("cls_prob") or 0.0,
        toxicity_pct=session.get("tox_val"),
        stage1_tag=session.get("stage1_tag"),
        stage1_ddo_avg=session.get("s1_ddo"),
        stage2_tag=session.get("stage2_tag"),
        stage2_ddo_avg=session.get("s2_ddo"),
        signal_points=session.get("signal_points", 0),
        do_min=session.get("do_min", 0.0),
        do_max=session.get("do_max", 0.0),
        bod_phase1=session.get("bod_phase1"),
        bod_phase2=session.get("bod_phase2"),
    )
    filename = f"{session.get('sample_name', 'report')}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _safe_content_disposition(filename)},
    )


def _parse_signal(file_bytes: bytes):
    tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
    tmp.write(file_bytes)
    tmp.close()
    try:
        try:
            raw = pd.read_csv(tmp.name, sep="\t", header=None, usecols=[0, 1],
                               names=["Time", "DO"], encoding="utf-16")
        except UnicodeError:
            rows = []
            with open(tmp.name) as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            rows.append((float(parts[0].replace("\x00", "")),
                                         float(parts[1].replace("\x00", ""))))
                        except ValueError:
                            pass
            raw = pd.DataFrame(rows, columns=["Time", "DO"])
        do = raw["DO"].values
        return do, len(raw), float(do.min()), float(do.max())
    finally:
        os.unlink(tmp.name)


@router.post("/session/{session_id}/upload", response_model=UploadResponse)
async def upload_file(session_id: str, file: UploadFile = File(...)):
    session = require_session(session_id)
    file_bytes = await file.read()
    sample_name = (file.filename or "sample").replace(".txt", "").strip()
    do_array, points, do_min, do_max = _parse_signal(file_bytes)

    session.update(
        file_bytes=file_bytes,
        sample_name=sample_name,
        do_array=do_array,
        do_min=do_min,
        do_max=do_max,
        signal_points=points,
        peaks_df=None,
        cls_pred=None,
        cls_prob=None,
    )
    return UploadResponse(
        sample_name=sample_name,
        signal_points=points,
        do_min=do_min,
        do_max=do_max,
        do_array=do_array.tolist(),
    )


@router.post("/session/{session_id}/peaks")
def extract_peaks(session_id: str):
    session = require_session(session_id)
    if "file_bytes" not in session:
        raise HTTPException(status_code=409, detail="Upload a file before extracting peaks")

    tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
    tmp.write(session["file_bytes"])
    tmp.close()
    try:
        peaks_df = extract_peaks_from_txt(tmp.name)
        for col in ("Doin (mV)", "No.peak", "DOmin (mV)", "DDO (mV)"):
            peaks_df[col] = pd.to_numeric(peaks_df[col], errors="coerce")
    finally:
        os.unlink(tmp.name)

    session["peaks_df"] = peaks_df
    return peaks_df.where(pd.notnull(peaks_df), None).to_dict(orient="records")


@router.post("/session/{session_id}/classify", response_model=ClassifyResponse)
def classify(session_id: str):
    session = require_session(session_id)
    if session.get("peaks_df") is None:
        raise HTTPException(status_code=409, detail="Extract peaks before classifying")

    results = catboost_inference_from_csv(
        session["peaks_df"],
        model_path="model/catboost_model.cbm",
        label_encoder_path="model/label_encoder_classes.npy",
    )
    _, pred, prob = results[0]
    session["cls_pred"] = str(pred)
    session["cls_prob"] = float(prob.max())
    return ClassifyResponse(cls_pred=session["cls_pred"], cls_prob=session["cls_prob"])


@router.post("/session/{session_id}/phase")
def detect_phase(session_id: str):
    session = require_session(session_id)
    if session.get("peaks_df") is None:
        raise HTTPException(status_code=409, detail="Extract peaks before phase detection")

    peaks_df = update_phase_tags(session["peaks_df"], session.get("cls_pred"))
    session["peaks_df"] = peaks_df
    return peaks_df.where(pd.notnull(peaks_df), None).to_dict(orient="records")


@router.post("/session/{session_id}/toxicity", response_model=ToxicityResponse)
def toxicity(session_id: str):
    session = require_session(session_id)
    peaks_df = session.get("peaks_df")
    if peaks_df is None or "phase_confidence" not in peaks_df.columns:
        raise HTTPException(status_code=409, detail="Run phase detection before toxicity")

    tox_df = calculate_toxicity(peaks_df)
    tox_row = tox_df.iloc[0] if len(tox_df) > 0 else None
    tox_val = (float(tox_row["Toxicity (%)"])
               if tox_row is not None and pd.notna(tox_row["Toxicity (%)"]) else None)
    stage1 = tox_row["Stage 1"] if tox_row is not None else None
    stage2 = tox_row["Stage 2"] if tox_row is not None else None

    s1_peaks = peaks_df[peaks_df["Tag"].str.strip() == str(stage1).strip()] if stage1 else pd.DataFrame()
    s2_peaks = peaks_df[peaks_df["Tag"].str.strip() == str(stage2).strip()] if stage2 else pd.DataFrame()
    s1_ddo = float(s1_peaks["DDO (mV)"].mean()) if not s1_peaks.empty else None
    s2_ddo = float(s2_peaks["DDO (mV)"].mean()) if not s2_peaks.empty else None

    session.update(toxicity_df=tox_df, tox_val=tox_val, stage1_tag=stage1, stage2_tag=stage2,
                    s1_ddo=s1_ddo, s2_ddo=s2_ddo)
    return ToxicityResponse(tox_val=tox_val, stage1=stage1, stage2=stage2, s1_ddo=s1_ddo, s2_ddo=s2_ddo)


@router.post("/session/{session_id}/bod", response_model=BodResponse)
def bod_calibration(session_id: str, payload: BodCalibrationRequest):
    session = require_session(session_id)
    peaks_df = session.get("peaks_df")
    if peaks_df is None or "phase_confidence" not in peaks_df.columns:
        raise HTTPException(status_code=409, detail="Run phase detection before BOD calibration")

    p1 = peaks_df[peaks_df["Tag"].str.strip() == "phase1"]
    p2 = peaks_df[peaks_df["Tag"].str.strip() == "phase2"]
    ddo_p1 = float(p1["DDO (mV)"].mean()) if not p1.empty else None
    ddo_p2 = float(p2["DDO (mV)"].mean()) if not p2.empty else None
    if ddo_p1 is None or ddo_p2 is None:
        raise HTTPException(status_code=409, detail="No phase1/phase2 peaks found")

    try:
        result = calculate_bod_from_calibration(
            ddo_phase1=ddo_p1, ddo_phase2=ddo_p2,
            bod1_cal=payload.bod1, ddo1_cal=payload.ddo1,
            bod2_cal=payload.bod2, ddo2_cal=payload.ddo2,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    session.update(bod_phase1=result["bod_phase1"], bod_phase2=result["bod_phase2"],
                    bod_a=result["a"], bod_b=result["b"])
    return BodResponse(**result)
