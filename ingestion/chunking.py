import os
import json
import hashlib
import re
from pathlib import Path


PARENT_SIZE = 2000
CHILD_SIZE = 500
CHILD_OVERLAP = 100
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORPUS_ROOT = PROJECT_ROOT / "data" / "raw"


def _document_provenance(txt_path):
    path = Path(txt_path).resolve()
    try:
        relative = path.relative_to(CORPUS_ROOT.resolve()).as_posix()
        source_file = f"data/raw/{relative}"
    except ValueError:
        relative = path.name
        source_file = path.as_posix()
    document_id = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:16]
    return document_id, source_file


def _estimate_tokens(text):
    return (len(text) + 3) // 4 if text else 0


def clean_text(text):
    text = text.strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text


def split_paragraphs(text):
    raw = [p.strip() for p in text.split("\n\n")]
    return [p for p in raw if p]


def group_paragraphs_into_parents(paragraphs, target_size=PARENT_SIZE):
    parents = []
    buffer = []
    buffer_len = 0

    for para in paragraphs:
        if buffer and buffer_len + len(para) > target_size:
            parents.append("\n\n".join(buffer))
            buffer = []
            buffer_len = 0
        buffer.append(para)
        buffer_len += len(para)

    if buffer:
        parents.append("\n\n".join(buffer))

    return parents


def build_child_chunks(parent_text):
    chunks = []
    start = 0
    text_len = len(parent_text)

    while start < text_len:
        end = min(start + CHILD_SIZE, text_len)
        chunk = parent_text[start:end]
        chunks.append(chunk)
        if end == text_len:
            break
        start += CHILD_SIZE - CHILD_OVERLAP

    return chunks


def save_chunks_to_files(parents, children_map, aircraft, font,
                        output_root="data/processed", document_id=None,
                        source_file=None):
    parent_dir = os.path.join(output_root, "parents", aircraft)
    child_dir = os.path.join(output_root, "chunks", aircraft)
    os.makedirs(parent_dir, exist_ok=True)
    os.makedirs(child_dir, exist_ok=True)

    for i, parent_text in enumerate(parents):
        parent_id = f"{aircraft.lower()}_{font.lower()}_p{i:03d}"
        parent_data = {
            "texto": parent_text,
            "metadata": {
                "aeronave": aircraft,
                "fuente": font,
                "parent_id": parent_id,
                "document_id": document_id,
                "source_file": source_file,
                "token_count": _estimate_tokens(parent_text),
            }
        }
        with open(os.path.join(parent_dir, f"parent_{i + 1}.json"), "w", encoding="utf-8") as f:
            json.dump(parent_data, f, ensure_ascii=False, indent=2)

    child_counter = 0
    for parent_idx, child_texts in enumerate(children_map):
        parent_id = f"{aircraft.lower()}_{font.lower()}_p{parent_idx:03d}"
        for child_text in child_texts:
            chunk_id = f"{aircraft.lower()}_{font.lower()}_c{child_counter:03d}"
            child_data = {
                "texto": child_text,
                "metadata": {
                    "aeronave": aircraft,
                    "fuente": font,
                    "chunk_id": chunk_id,
                    "parent_id": parent_id,
                    "document_id": document_id,
                    "source_file": source_file,
                    "token_count": _estimate_tokens(child_text),
                }
            }
            with open(os.path.join(child_dir, f"chunk_{child_counter + 1}.json"), "w", encoding="utf-8") as f:
                json.dump(child_data, f, ensure_ascii=False, indent=2)
            child_counter += 1


def process_document(txt_path, aircraft, font, output_root="data/processed"):
    """Chunk a single txt file into parents + children and write them to disk.

    Returns (parents, children_map) so callers can inspect the result.
    """
    with open(txt_path, "r", encoding="utf-8") as file:
        raw_text = file.read()

    text = clean_text(raw_text)
    paragraphs = split_paragraphs(text)
    parents = group_paragraphs_into_parents(paragraphs, target_size=PARENT_SIZE)
    children_map = [build_child_chunks(p) for p in parents]
    document_id, source_file = _document_provenance(txt_path)
    save_chunks_to_files(
        parents,
        children_map,
        aircraft,
        font,
        output_root=output_root,
        document_id=document_id,
        source_file=source_file,
    )
    return parents, children_map


if __name__ == "__main__":
    wiki_route = "data/raw/wiki"
    pdf_route = "data/raw/pdf_to_txt"

    wiki_docs = os.listdir(wiki_route)
    pdf_docs = os.listdir(pdf_route)

    docs = wiki_docs + pdf_docs

    for doc in docs:
        if doc == ".gitkeep":
            continue
        aircraft = doc.split(".txt")[0]
        doc_font = "wiki" if doc in wiki_docs else "pdf" if doc in pdf_docs else "unknown"
        txt_path = os.path.join(wiki_route if doc_font == "wiki" else pdf_route, doc)

        parents, children_map = process_document(txt_path, aircraft, doc_font)
        print(f"{aircraft}: {len(parents)} parents, {sum(len(c) for c in children_map)} children")
