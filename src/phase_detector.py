"""
Phase boundary detection module.

Public API:
    update_phase_tags(peaks_df, cls_label) -> peaks_df with rewritten Tag and phase_confidence.

Tag values: 'phase1', 'transition', 'phase2', (or 'unknown' on error).
"""
import os
import numpy as np
import pandas as pd

from src.phase_features import compute_peak_features

_MIN_PEAKS = 8
_GGA_K_MIN = 5
_GGA_K_MAX = 8
_HH_DDO_P90_THRESHOLD = 12.0

_MODEL_PATHS = {
    'metal': 'model/phase_detector_metal.pkl',
    'hh': 'model/phase_detector_hh.pkl',
}

_model_cache = {}


def _fallback_heuristic(peaks_df: pd.DataFrame):
    """Half-split fallback when n<8 peaks. No transition zone."""
    n = len(peaks_df)
    preds = np.zeros(n, dtype=int)
    half = n // 2
    preds[half:] = 2
    confs = np.full(n, 0.5)
    return preds, confs


def _find_change_point(ddo: np.ndarray, k_min: int, k_max: int) -> int:
    """
    Find k in [k_min, k_max] that minimizes within-group variance:
        var(ddo[:k]) + var(ddo[k:])
    Returns k (the size of phase 1). k_max clamped to len(ddo)-1.
    """
    n = len(ddo)
    k_max = min(k_max, n - 1)
    if k_min > k_max:
        return min(k_min, n - 1)
    best_k = k_min
    best_cost = np.inf
    for k in range(k_min, k_max + 1):
        left = ddo[:k]
        right = ddo[k:]
        if len(left) < 2 or len(right) < 2:
            continue
        cost = float(np.var(left)) + float(np.var(right))
        if cost < best_cost:
            best_cost = cost
            best_k = k
    return best_k


def _gga_algorithm(peaks_df: pd.DataFrame):
    """
    Constrained change-point detection for GGA.
    Phase 1 size in [5, 8]. Transition = 1 peak after phase 1 end.
    """
    n = len(peaks_df)
    ddo = peaks_df['DDO (mV)'].to_numpy(dtype=float)
    k = _find_change_point(ddo, _GGA_K_MIN, _GGA_K_MAX)
    preds = np.zeros(n, dtype=int)
    if k >= n:
        preds[:] = 0
        return preds, np.full(n, 0.6)
    if k + 1 < n:
        preds[k] = 1
        preds[k + 1:] = 2
    else:
        preds[k:] = 2
    confs = np.full(n, 0.85)
    return preds, confs


def update_phase_tags(peaks_df: pd.DataFrame, cls_label: str | None = None) -> pd.DataFrame:
    """
    Rewrite the 'Tag' column with phase labels and add 'phase_confidence'.

    Args:
        peaks_df: must contain ['No.peak','Doin (mV)','DOmin (mV)','DDO (mV)']
        cls_label: 'GGA' or 'Metal' (from CatBoost classifier). When omitted,
            use the generic GGA change-point algorithm.

    Returns:
        peaks_df with Tag in {'phase1','transition','phase2'} and phase_confidence column.
    """
    df = peaks_df.copy()
    n = len(df)
    if n == 0:
        df['phase_confidence'] = []
        return df

    if n < _MIN_PEAKS:
        preds, confs = _fallback_heuristic(df)
    else:
        is_hh = float(df['DDO (mV)'].quantile(0.9)) > _HH_DDO_P90_THRESHOLD
        if is_hh:
            preds, confs = _ml_predict(df, 'hh')
        elif 'metal' in str(cls_label).lower():
            preds, confs = _ml_predict(df, 'metal')
        else:
            preds, confs = _gga_algorithm(df)

    if (preds == 0).all():
        df['Tag'] = 'phase1'
        df['phase_confidence'] = confs
        return df

    tag_map = {0: 'phase1', 1: 'transition', 2: 'phase2'}
    df['Tag'] = [tag_map[int(p)] for p in preds]
    df['phase_confidence'] = confs
    return df


def _ml_predict(peaks_df: pd.DataFrame, kind: str):
    """Load RF model (cached), compute features, predict per-peak."""
    if kind not in _model_cache:
        import joblib
        path = _MODEL_PATHS[kind]
        if not os.path.exists(path):
            return _gga_algorithm(peaks_df)
        _model_cache[kind] = joblib.load(path)
    model = _model_cache[kind]
    feats = compute_peak_features(peaks_df)
    X = feats.to_numpy(dtype=float)
    preds = model.predict(X).astype(int)
    probs = model.predict_proba(X)
    confs = probs.max(axis=1)
    return preds, confs
