"""Validate the local corpus manifest and evaluation seed without a DB."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = PROJECT_ROOT / "evaluation_data" / "corpus_manifest.json"
DEFAULT_SEED = PROJECT_ROOT / "db" / "evaluation_seed_v1.sql"

CASE_ID_PATTERN = re.compile(r"\(\s*'(av_\d{4})',\s*'aviation_golden_v1'")
EVIDENCE_PATTERN = re.compile(
    r"\(\s*'(av_\d{4})',\s*'([^']+)',\s*'[^']+',\s*(\d+),\s*(\d+),"
)


def validate_manifest(path: Path, project_root: Path = PROJECT_ROOT) -> list[str]:
    errors = []
    if not path.exists():
        return [f"Manifest does not exist: {path}"]

    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return [f"Manifest is not valid JSON: {error}"]

    documents = manifest.get("documents")
    if not isinstance(documents, list) or not documents:
        return ["Manifest must contain a non-empty documents list."]

    seen_ids = set()
    for document in documents:
        document_id = document.get("document_id")
        document_path = document.get("path")
        if document_id in seen_ids:
            errors.append(f"Duplicate document_id: {document_id}")
        seen_ids.add(document_id)
        if not document_path:
            errors.append(f"Document has no path: {document_id}")
        elif not (project_root / document_path).exists():
            errors.append(f"Source file does not exist: {document_path}")
        if document.get("line_count", 0) < 0:
            errors.append(f"Invalid line count: {document_id}")
    return errors


def validate_seed(
    path: Path,
    project_root: Path = PROJECT_ROOT,
    check_sources: bool = True,
) -> list[str]:
    errors = []
    if not path.exists():
        return [f"Seed does not exist: {path}"]

    sql = path.read_text(encoding="utf-8")
    case_ids = CASE_ID_PATTERN.findall(sql)
    expected_ids = [f"av_{index:04d}" for index in range(1, 37)]
    if case_ids != expected_ids:
        errors.append(
            "Seed case IDs must contain av_0001 through av_0036 in order. "
            f"Found {len(case_ids)} case rows."
        )

    evidence_ids = set()
    for case_id, source_file, line_start, line_end in EVIDENCE_PATTERN.findall(sql):
        evidence_ids.add(case_id)
        source_path = project_root / source_file
        if check_sources and not source_path.exists():
            errors.append(f"Evidence source does not exist for {case_id}: {source_file}")
            continue
        if check_sources:
            line_count = len(source_path.read_text(encoding="utf-8").splitlines())
            if int(line_start) < 1 or int(line_end) > line_count:
                errors.append(
                    f"Evidence lines out of range for {case_id}: "
                    f"{line_start}-{line_end} in {source_file} ({line_count} lines)"
                )

    if "'av_0030'" not in sql or "false, true, 'Airbus A380'" not in sql:
        errors.append("Seed must include an explicit unanswerable case.")
    if "on conflict (case_id, source_file, line_start, line_end, quote) do nothing" not in sql:
        errors.append("Evidence seed must be idempotent.")
    if len(evidence_ids) != 35:
        errors.append(f"Expected evidence for 35 answerable cases, found {len(evidence_ids)}.")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    args = parser.parse_args()

    errors = validate_manifest(args.manifest) + validate_seed(args.seed)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(1)

    print("Evaluation manifest and seed are valid.")


if __name__ == "__main__":
    main()
