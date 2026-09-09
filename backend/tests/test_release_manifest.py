import json
from pathlib import Path


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
