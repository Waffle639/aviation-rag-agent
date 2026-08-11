from evaluation.manifest import build_manifest
from evaluation.validate_dataset import validate_seed


def test_manifest_contains_text_corpus(tmp_path):
    corpus_root = tmp_path / "raw"
    wiki_root = corpus_root / "wiki"
    wiki_root.mkdir(parents=True)
    (wiki_root / "Example_Aircraft.txt").write_text(
        "A test aircraft.\n", encoding="utf-8"
    )

    manifest = build_manifest(corpus_root)

    assert len(manifest["documents"]) == 1
    assert all(document["sha256"] for document in manifest["documents"])
    assert manifest["documents"][0]["line_count"] == 1


def test_evaluation_seed_has_initial_cases_and_valid_evidence():
    from evaluation.validate_dataset import DEFAULT_SEED

    assert validate_seed(DEFAULT_SEED, check_sources=False) == []
