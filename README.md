# VHL Biology Project

**Version**: 1.3.1 | **Last Updated**: 2026-06-21 | **Status**: Production Ready

Production ML system for dissolved oxygen (DO) analysis. Classifies biological samples (GGA vs GGA-metal), extracts DO peaks using adaptive two-pass algorithm, and predicts BOD metrics—entirely from TXT file uploads with no Excel dependency.

**Full pipeline verified**: TXT → Peaks → Classification → Toxicity (tested 2026-03-11).

## Quick Start

1. **Environment** (conda `vhl` recommended):
```bash
conda activate vhl
# or: pip install -r requirements.txt
```

2. **Run the Streamlit dashboard:**
```bash
streamlit run app.py
```
Dashboard walks you through a 6-step wizard: Upload → Peak Extraction → Classification → Phase Detection → Toxicity → Summary.

## Project Overview

**Core Purpose**: Analyze DO degradation patterns from TXT files using production-tuned peak extraction, classify samples, and forecast time-series.
**Key Components**: Adaptive peak extraction (2-pass HH detection, +0.05mV non-HH bias), Classification (CatBoost primary, RF/XGBoost), Time-series forecasting (LSTM encoder-decoder)
**Production Pipeline**: UTF-16 TXT → extract_peaks_from_txt() → peaks DataFrame → Classification → Toxicity
**Python Environment**: conda env `vhl` (CatBoost 1.2.8, TensorFlow 2.19.0, SciPy, Keras 3.10.0)

## Directory Structure

```
VHL_Biology/
├── code/                          # Analysis scripts (legacy + training)
│   ├── gga_classification_model.py # RF/XGBoost classifier (70+ features)
│   ├── extract_DO_in.py           # Legacy Savitzky-Golay extraction
│   ├── extract_special_points.py  # Fixed-interval extraction
│   ├── ema_model.py               # EMA forecasting with RF
│   ├── process_txt_data.py        # UTF-16 TXT → CSV conversion
│   ├── check_matching_name.py     # Fuzzy name matching
│   └── train extract special points/  # ML-based extraction training
├── src/                           # Production modules
│   ├── peak_extractor.py          # Production adaptive peak extraction (448 lines)
│   ├── utils.py                   # Feature engineering, CatBoost, LSTM, toxicity (549 lines)
│   └── visualize_data.py          # Visualization with peak marking
├── tools/                         # Optimization & reporting utilities
│   ├── derive_metadata_from_txt.py # Signal processing peak detection
│   ├── validate_metadata.py       # Tolerance-based validation
│   ├── validate-classifier-accuracy.py # 518-file classification validation
│   ├── experiment-a-robust-features.py # Feature engineering experiments
│   ├── experiment-b-augmentation.py    # Noise injection + oversampling
│   ├── experiment-c-ensemble.py        # Multi-model ensemble comparison
│   ├── experiment-d-aligned-training.py # Aligned training (algo-extracted)
│   ├── experiment-e-aligned-noise.py   # Combined best approach
│   ├── experiment-final-combine.py     # Final model training
│   ├── analyze_metal_errors.py    # Per-peak error analysis (4 datasets)
│   ├── test_metal_targeted.py     # 47 bias/param configurations
│   ├── test_bias_finetune.py      # Bias fine-tuning (19 configs)
│   ├── test_ml_correction.py      # ML correction experiment (GBR/RF)
│   ├── generate_comprehensive_report.py  # Word report generation
│   └── generate-progress-report-260311.py # Vietnamese progress report
├── model/                          # Trained models (versioned)
│   ├── LSTM Model/28_07_2025/    # LSTM encoder-decoder (lookback=7, Huber loss)
│   ├── RF Model/03012025/         # Random Forest classifier
│   ├── catboost_model.cbm         # CatBoost classifier (production)
│   └── label_encoder_classes.npy
├── notebooks/                      # Jupyter notebooks (baselines)
│   ├── ARIMA_1_0_Bio_VHL.ipynb
│   ├── LSTM_Bio_VHL.ipynb
│   ├── LR_BIO_VHL.ipynb
│   └── SMA_EWMA_method.ipynb
├── data/
│   ├── GGA/, GGA-metal/, BOD-Hieu/  # Sample data (UTF-16 TXT)
│   ├── metadata-gga-*.csv         # Extracted metadata
│   └── ext_v16_*.csv              # Algorithm-extracted peaks
├── docs/                          # Documentation
├── plans/reports/                 # Optimization reports & Vietnamese progress reports
└── app.py                         # Streamlit Wizard Dashboard v2.2.0 (725 lines, 6-step)
```

## Key Features

- **Peak Extraction**: Production adaptive algorithm (two-pass HH detection, +0.05mV bias correction, 485+ configs tuned)
- **Classification**: CatBoost primary (84.4% on 518 files, aligned training + noise augmentation + GGA oversampling)
- **Phase Detection**: Hybrid 3-track ML/algorithm (RandomForest Metal/HH, constrained change-point GGA)
- **Time-Series**: LSTM encoder-decoder (lookback=7, Huber loss)
- **Toxicity**: Phase1 vs phase2 calculation (transition rows excluded)
- **Dashboard**: Wizard Dashboard v2.2.0 (6-step wizard, back/forward nav, per-step timing, cached charts, colored flow diagrams)
- **Validation**: Tolerance-based peak matching, phase boundary ±1 = 98%+ (Metal/HH)

## Production Pipeline

```
Upload TXT (UTF-16)
    ↓
extract_peaks_from_txt() [src/utils.py → src/peak_extractor.py]
    ├─ Two-pass HH detection
    ├─ Bias correction (+0.05mV non-HH, +0.04mV HH)
    └─ Output: DataFrame [No.peak, Tag, Doin, DOmin, DDO, Sample Name]
    ↓
Split processing:
├─ process_and_predict_lstm() [LSTM prediction on raw time-series]
├─ catboost_inference_from_csv() [CatBoost classification on peaks]
├─ update_phase_tags() [phase1 / transition / phase2 detection]
└─ calculate_toxicity() [DDO phase1 vs phase2 → toxicity %, transition skipped]
    ↓
Results: Classification, Toxicity %, Forecasts
```

### Pipeline Test Result (2026-03-11)

```
Sample: N4-10-5-01042024-Q=49.81mL_phút-3
Signal: 9,415 points | DO range: 277.24 – 284.75 mV
Peaks:  20 extracted (1 BOD10, 19 BOD5) | DDO: 4.49 – 5.84 mV
Classification: GGA (probability 78.4%)
Toxicity: 5.31%
Status: ALL 4 STEPS PASSED ✓
```

## Classification Accuracy (CatBoost, 518-file validation, 2026-03-22)

| Metric | Value |
|--------|-------|
| **Overall Accuracy** | **84.4%** (437/518) |
| GGA Recall | 88.1% (140/159) |
| Metal Recall | 82.7% (297/359) |

**Training**: Algo-extracted peaks + Gaussian noise (s=0.08, 3x) + GGA oversample (45%)
**Model**: CatBoost (iter=300, lr=0.05, depth=8, balanced weights), 81 features

## Extraction Accuracy (2-pass adaptive, tuned 485+ configs)

| Dataset | Samples | Peaks | 0.2mV  | 0.3mV  |
|---------|---------|-------|--------|--------|
| Test    | 14      | 681   | 88.1%  | **93.0%** |
| GGA     | 134     | 1793  | 79.9%  | **85.3%** |
| Metal   | 348     | 5254  | 73.6%  | **80.1%** |
| HH      | 89      | 1252  | 73.7%  | **84.1%** |

## Environment Setup

```bash
# Recommended: conda vhl environment (has all dependencies)
conda activate vhl

# Key packages in vhl env:
# catboost==1.2.8, tensorflow==2.19.0, keras==3.10.0
# scipy, pandas, numpy, scikit-learn, plotly, streamlit, openpyxl
```

## Documentation

- [Project Overview & Requirements](./docs/project-overview-pdr.md)
- [Code Standards & Structure](./docs/code-standards.md)
- [System Architecture](./docs/system-architecture.md)
- [Codebase Summary](./docs/codebase-summary.md)
- [Project Roadmap](./docs/project-roadmap.md)

## Windows LAN Client Handoff

For the Windows/Conda client installation, run the backend and Streamlit
dashboard from the same release directory on a private LAN:

- [Client deployment guide](./CLIENT_DEPLOYMENT.md)
- [Operations runbook](./OPERATIONS_RUNBOOK.md)
- [Model card](./MODEL_CARD.md)
- [Internal API reference](./API_INTERNAL.md)
- [Release history](./CHANGELOG.md)

The handoff scripts are:

- [`start_backend.ps1`](scripts/start_backend.ps1)
- [`start_dashboard.ps1`](scripts/start_dashboard.ps1)
- [`health_check.ps1`](scripts/health_check.ps1)
- [`build_release.ps1`](scripts/build_release.ps1)
- [`smoke_test.py`](scripts/smoke_test.py)

The release builder creates `RELEASE_MANIFEST.json` with runtime metadata and
model checksums.

## Reports

- Classification improvement: `plans/reports/classification-improvement-260322.md`
- Vietnamese progress report: `plans/reports/BÁO CÁO SINH HỌC (11-03-2026).docx`
- DOin bias correction & ML analysis: `plans/reports/optimization-260224-0921-doin-bias-correction-ml-analysis.md`
- DOin accuracy ceiling audit: `plans/reports/evaluation-audit-260222-0956-doin-accuracy-ceiling.md`
