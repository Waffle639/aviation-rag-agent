"""Build a reproducible manifest for the local source corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = PROJECT_ROOT / "evaluation_data" / "corpus_manifest.json"
CORPUS_ROOT = PROJECT_ROOT / "data" / "raw"

PDF_METADATA = {
    "AC_A320_0624": ("Airbus A320", "A320"),
    "ac_a330_jul2023_0": ("Airbus A330", "A330"),
    "747-400_Rev_F": ("Boeing 747", "747-400"),
    "IF12945.7": ("U.S. Strategic Bombers", "B-52/B-1B/B-2/B-21"),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _document_metadata(path: Path, corpus_root: Path) -> tuple[str, str, str, str]:
    relative = path.relative_to(corpus_root).as_posix()
    if path.parent.name == "pdf_to_txt":
        aircraft, variant = PDF_METADATA.get(
            path.stem, (path.stem, "unknown")
        )
        return relative, "pdf_text", aircraft, variant

    title = path.stem.replace("_", " ")
    return relative, "wikipedia", title, "family_or_base_model"


def build_manifest(corpus_root: Path = CORPUS_ROOT) -> dict:
    documents = []
    for path in sorted(corpus_root.rglob("*.txt")):
        relative, source_type, aircraft, variant = _document_metadata(path, corpus_root)
        text = path.read_text(encoding="utf-8")
        documents.append(
            {
                "document_id": hashlib.sha256(relative.encode("utf-8")).hexdigest()[:16],
                "path": f"data/raw/{relative}",
                "source_type": source_type,
                "aircraft": aircraft,
                "variant": variant,
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
                "line_count": len(text.splitlines()),
                "is_empty": not text.strip(),
            }
        )

    payload = {"manifest_version": "v1", "documents": documents}
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    payload["manifest_sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    manifest = build_manifest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"Wrote {len(manifest['documents'])} documents to {args.output} "
        f"(manifest_sha256={manifest['manifest_sha256']})."
    )


if __name__ == "__main__":
    main()
