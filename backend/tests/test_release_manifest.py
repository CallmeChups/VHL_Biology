import json
from pathlib import Path

from scripts.smoke_test import record_smoke_result


def test_release_manifest_has_runtime_identity(tmp_path: Path):
    manifest = {
        "release_version": "1.0.0",
        "source_commit": "abc123",
        "build_date_utc": "2026-09-10T00:00:00Z",
        "python_version": "3.11",
        "dependencies": {"catboost": "1.2.8"},
        "runtime_models": ["model/catboost_model.cbm"],
        "checksums": {"model/catboost_model.cbm": "a" * 64},
        "baseline": {"sample": "sample.txt", "status": "passed"},
    }
    path = tmp_path / "RELEASE_MANIFEST.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert set(("release_version", "source_commit", "build_date_utc",
                "python_version", "dependencies", "runtime_models",
                "checksums", "baseline")) <= loaded.keys()
    assert len(loaded["checksums"]["model/catboost_model.cbm"]) == 64


def test_smoke_result_records_observed_output_and_verification(tmp_path: Path):
    path = tmp_path / "RELEASE_MANIFEST.json"
    path.write_text(
        json.dumps(
            {
                "python_version": {
                    "runtime": "python-3.11",
                    "active": "3.12.10",
                },
                "baseline": {
                    "sample": "sample-data/representative-sample.txt",
                    "expected": {
                        "peaks": 20,
                        "classification": "GGA",
                        "toxicity_percent": 5.31,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    record_smoke_result(
        path,
        {
            "sample": "sample-data/representative-sample.txt",
            "peaks": 20,
            "classification": "gga",
            "classification_probability": 0.784,
            "toxicity_percent": 10.05,
            "runtime": "3.12.10",
        },
    )

    manifest = json.loads(path.read_text(encoding="utf-8"))
    baseline = manifest["baseline"]
    assert baseline["expected"]["toxicity_percent"] == 5.31
    assert baseline["observed"]["toxicity_percent"] == 10.05
    assert baseline["observed"]["classification"] == "gga"
    assert baseline["status"] == "failed"
    assert baseline["verification"]["status"] == "failed"
    assert baseline["verification"]["output_status"] == "failed"
    assert baseline["verification"]["runtime_status"] == "unverified"
