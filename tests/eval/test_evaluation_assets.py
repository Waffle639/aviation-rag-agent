import hashlib
import json

from evaluation.manifest import build_manifest
from evaluation.validate_dataset import validate_manifest, validate_seed


def test_manifest_contains_text_corpus(tmp_path):
    corpus_root = tmp_path / "raw"
    wiki_root = corpus_root / "wiki"
    wiki_root.mkdir(parents=True)
    (wiki_root / "Example_Aircraft.txt").write_text(
        "A test aircraft.\n", encoding="utf-8"
    )

    manifest = build_manifest(corpus_root)

    assert len(manifest["documents"]) == 1
    expected_sha = hashlib.sha256(
        (wiki_root / "Example_Aircraft.txt").read_bytes()
    ).hexdigest()
    assert manifest["documents"][0]["sha256"] == expected_sha
    assert manifest["documents"][0]["line_count"] == 1
    canonical = json.dumps(
        {key: value for key, value in manifest.items() if key != "manifest_sha256"},
        ensure_ascii=True,
        sort_keys=True,
    ).encode("utf-8")
    assert manifest["manifest_sha256"] == hashlib.sha256(canonical).hexdigest()


def test_evaluation_seed_has_initial_cases_and_valid_evidence():
    from evaluation.validate_dataset import DEFAULT_SEED

    assert validate_seed(DEFAULT_SEED, check_sources=False) == []


def test_manifest_validation_reports_missing_path_duplicate_and_invalid_lines(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "documents": [
                    {"document_id": "duplicate", "path": "missing.txt", "line_count": -1},
                    {"document_id": "duplicate", "path": "missing-again.txt", "line_count": 0},
                ]
            }
        ),
        encoding="utf-8",
    )

    errors = validate_manifest(manifest_path, project_root=tmp_path)

    assert any("Duplicate document_id" in error for error in errors)
    assert any("does not exist" in error for error in errors)
    assert any("Invalid line count" in error for error in errors)


def test_validation_reports_missing_or_invalid_assets(tmp_path):
    missing = tmp_path / "missing.json"
    assert "does not exist" in validate_manifest(missing)[0]
    assert "does not exist" in validate_seed(missing)[0]

    invalid_manifest = tmp_path / "invalid.json"
    invalid_manifest.write_text("not-json", encoding="utf-8")
    assert "not valid JSON" in validate_manifest(invalid_manifest)[0]
