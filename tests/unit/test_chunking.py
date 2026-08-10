"""
Unit tests for ingestion/chunking.py — the parent-child chunking stage.

Design contract under test (from README):
  - children (~500 chars, 100 overlap) are embedded for precise matching
  - parents (~2000 chars, paragraph-aligned) are what the model sees
  - stable IDs make ingestion idempotent across re-runs
"""

import json
import os

import pytest

from ingestion.chunking import (
    CHILD_OVERLAP,
    CHILD_SIZE,
    PARENT_SIZE,
    build_child_chunks,
    clean_text,
    group_paragraphs_into_parents,
    save_chunks_to_files,
    split_paragraphs,
)


class TestCleanText:
    def test_strips_surrounding_whitespace(self):
        assert clean_text("  hello \n") == "hello"

    def test_collapses_three_or_more_newlines(self):
        assert clean_text("a\n\n\n\nb") == "a\n\nb"

    def test_collapses_tabs_and_multiple_spaces(self):
        assert clean_text("a \t  b") == "a b"

    def test_removes_spaces_around_newlines(self):
        assert clean_text("a \n b") == "a\nb"

    def test_empty_string(self):
        assert clean_text("") == ""

    def test_only_whitespace(self):
        assert clean_text("   \n\n\t  ") == ""

    def test_preserves_unicode_content(self):
        text = "Sukhoi Su-57 (Russian: Сухой Су-57) café"
        assert clean_text(text) == text

    def test_idempotent(self):
        messy = "  a \n\n\n\n b \t c \n d  "
        assert clean_text(clean_text(messy)) == clean_text(messy)

    def test_preserves_single_and_double_newlines(self):
        assert clean_text("a\nb\n\nc") == "a\nb\n\nc"


class TestSplitParagraphs:
    def test_splits_on_double_newline(self):
        assert split_paragraphs("p1\n\np2\n\np3") == ["p1", "p2", "p3"]

    def test_drops_empty_paragraphs(self):
        assert split_paragraphs("p1\n\n\n\np2") == ["p1", "p2"]

    def test_single_paragraph(self):
        assert split_paragraphs("only one") == ["only one"]

    def test_empty_string_returns_empty(self):
        assert split_paragraphs("") == []

    def test_strips_each_paragraph(self):
        assert split_paragraphs("  p1  \n\n  p2  ") == ["p1", "p2"]

    def test_single_newlines_stay_inside_paragraph(self):
        assert split_paragraphs("line1\nline2") == ["line1\nline2"]


class TestGroupParagraphsIntoParents:
    def test_empty_input(self):
        assert group_paragraphs_into_parents([]) == []

    def test_small_paragraphs_share_one_parent(self):
        parents = group_paragraphs_into_parents(["aaa", "bbb", "ccc"], target_size=100)
        assert parents == ["aaa\n\nbbb\n\nccc"]

    def test_splits_when_next_paragraph_would_exceed_target(self):
        paragraphs = ["x" * 60, "y" * 60]
        parents = group_paragraphs_into_parents(paragraphs, target_size=100)
        assert len(parents) == 2
        assert parents[0] == "x" * 60
        assert parents[1] == "y" * 60

    def test_exact_fit_stays_together(self):
        # buffer_len(50) + len(next)(50) == target -> NOT greater -> same parent
        paragraphs = ["x" * 50, "y" * 50]
        parents = group_paragraphs_into_parents(paragraphs, target_size=100)
        assert parents == ["x" * 50 + "\n\n" + "y" * 50]

    def test_single_oversized_paragraph_becomes_own_parent(self):
        big = "x" * (PARENT_SIZE * 3)
        parents = group_paragraphs_into_parents([big], target_size=PARENT_SIZE)
        assert parents == [big]

    def test_no_paragraph_is_lost(self):
        paragraphs = [f"paragraph {i} " + "x" * (i * 37 % 211) for i in range(50)]
        parents = group_paragraphs_into_parents(paragraphs, target_size=PARENT_SIZE)
        assert "\n\n".join(paragraphs) == "\n\n".join(parents)

    def test_order_is_preserved(self):
        paragraphs = [f"p{i:02d}" for i in range(30)]
        parents = group_paragraphs_into_parents(paragraphs, target_size=40)
        flat = "\n\n".join(parents)
        positions = [flat.index(f"p{i:02d}") for i in range(30)]
        assert positions == sorted(positions)

    def test_default_target_size_is_parent_size(self):
        paragraphs = ["x" * (PARENT_SIZE - 10), "y" * 20]
        parents = group_paragraphs_into_parents(paragraphs)
        assert len(parents) == 2


class TestBuildChildChunks:
    def test_empty_text(self):
        assert build_child_chunks("") == []

    def test_short_text_single_chunk(self):
        text = "short text"
        assert build_child_chunks(text) == [text]

    def test_exact_child_size_single_chunk(self):
        text = "x" * CHILD_SIZE
        assert build_child_chunks(text) == [text]

    def test_one_over_limit_gives_two_chunks(self):
        text = "x" * (CHILD_SIZE + 1)
        chunks = build_child_chunks(text)
        assert len(chunks) == 2
        assert chunks[0] == text[:CHILD_SIZE]
        assert chunks[1] == text[CHILD_SIZE - CHILD_OVERLAP:]

    def test_no_chunk_exceeds_child_size(self):
        text = "Lorem ipsum dolor sit amet. " * 500
        for chunk in build_child_chunks(text):
            assert len(chunk) <= CHILD_SIZE

    def test_chunks_start_at_expected_offsets(self):
        text = "".join(chr(65 + (i % 26)) for i in range(3000))
        chunks = build_child_chunks(text)
        step = CHILD_SIZE - CHILD_OVERLAP
        for i, chunk in enumerate(chunks):
            start = i * step
            assert chunk == text[start:start + CHILD_SIZE]

    def test_full_coverage_no_character_lost(self):
        text = "".join(f"{i:04d}-" for i in range(1000))
        chunks = build_child_chunks(text)
        covered = set()
        step = CHILD_SIZE - CHILD_OVERLAP
        for i, chunk in enumerate(chunks):
            start = i * step
            for j in range(len(chunk)):
                covered.add(start + j)
        assert covered == set(range(len(text)))

    def test_overlap_content_matches_between_consecutive_chunks(self):
        text = "abcdefghij" * 300  # 3000 chars, several chunks
        chunks = build_child_chunks(text)
        for prev, nxt in zip(chunks, chunks[1:]):
            if len(prev) == CHILD_SIZE and len(nxt) >= CHILD_OVERLAP:
                assert prev[-CHILD_OVERLAP:] == nxt[:CHILD_OVERLAP]

    def test_expected_chunk_count_formula(self):
        step = CHILD_SIZE - CHILD_OVERLAP
        for length in (1, 500, 501, 901, 2000, 5432):
            text = "x" * length
            chunks = build_child_chunks(text)
            if length <= CHILD_SIZE:
                assert len(chunks) == 1
            else:
                expected = 1 + -(-(length - CHILD_SIZE) // step)  # ceil div
                assert len(chunks) == expected, f"length={length}"


class TestSaveChunksToFiles:
    @pytest.fixture
    def saved(self, tmp_path, monkeypatch):
        """Save a small corpus into a tmp data/processed tree."""
        monkeypatch.chdir(tmp_path)
        parents = ["P0 text " + "a" * 30, "P1 text " + "b" * 30]
        children_map = [
            ["c00", "c01"],
            ["c10", "c11", "c12"],
        ]
        save_chunks_to_files(parents, children_map, "TestPlane", "WIKI")
        return tmp_path

    def test_creates_directory_tree(self, saved):
        assert (saved / "data/processed/parents/TestPlane").is_dir()
        assert (saved / "data/processed/chunks/TestPlane").is_dir()

    def test_writes_one_file_per_parent_and_child(self, saved):
        parents_dir = saved / "data/processed/parents/TestPlane"
        chunks_dir = saved / "data/processed/chunks/TestPlane"
        assert len(list(parents_dir.glob("*.json"))) == 2
        assert len(list(chunks_dir.glob("*.json"))) == 5  # 2 + 3 child texts

    def test_parent_json_schema_and_metadata(self, saved):
        with open(saved / "data/processed/parents/TestPlane/parent_1.json",
                  encoding="utf-8") as f:
            data = json.load(f)
        assert data["texto"].startswith("P0 text")
        assert data["metadata"]["aeronave"] == "TestPlane"
        assert data["metadata"]["fuente"] == "WIKI"
        assert data["metadata"]["parent_id"] == "testplane_wiki_p000"

    def test_child_json_schema_and_parent_linkage(self, saved):
        chunks_dir = saved / "data/processed/chunks/TestPlane"
        children = []
        for path in sorted(chunks_dir.glob("*.json")):
            with open(path, encoding="utf-8") as f:
                children.append(json.load(f))

        # child_counter is global across parents (c000..c004)
        assert [c["metadata"]["chunk_id"] for c in children] == [
            "testplane_wiki_c000",
            "testplane_wiki_c001",
            "testplane_wiki_c002",
            "testplane_wiki_c003",
            "testplane_wiki_c004",
        ]
        # first two children belong to parent 0, next three to parent 1
        assert children[0]["metadata"]["parent_id"] == "testplane_wiki_p000"
        assert children[1]["metadata"]["parent_id"] == "testplane_wiki_p000"
        assert children[2]["metadata"]["parent_id"] == "testplane_wiki_p001"
        assert children[4]["metadata"]["parent_id"] == "testplane_wiki_p001"

    def test_ids_are_lowercased_and_zero_padded(self, saved):
        with open(saved / "data/processed/chunks/TestPlane/chunk_1.json",
                  encoding="utf-8") as f:
            data = json.load(f)
        assert data["metadata"]["chunk_id"] == "testplane_wiki_c000"

    def test_unicode_written_with_utf8(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        save_chunks_to_files(["Сухой Су-57"], [["Сухой"]], "Su_57", "wiki")
        with open(tmp_path / "data/processed/parents/Su_57/parent_1.json",
                  encoding="utf-8") as f:
            data = json.load(f)
        assert data["texto"] == "Сухой Су-57"

    def test_deterministic_ids_across_runs(self, tmp_path, monkeypatch):
        """Idempotency contract: same input -> same IDs, safe to re-run."""
        monkeypatch.chdir(tmp_path)
        parents = ["alpha text", "beta text"]
        children_map = [["a1", "a2"], ["b1"]]
        save_chunks_to_files(parents, children_map, "Plane", "pdf")
        first = {}
        for path in (tmp_path / "data/processed/chunks/Plane").glob("*.json"):
            with open(path, encoding="utf-8") as f:
                first[os.path.basename(path)] = json.load(f)["metadata"]["chunk_id"]

        save_chunks_to_files(parents, children_map, "Plane", "pdf")
        second = {}
        for path in (tmp_path / "data/processed/chunks/Plane").glob("*.json"):
            with open(path, encoding="utf-8") as f:
                second[os.path.basename(path)] = json.load(f)["metadata"]["chunk_id"]

        assert first == second


class TestProcessDocument:
    """process_document: the single-document chunking driver (TDD refactor)."""

    def test_process_document_exists(self, tmp_path):
        from ingestion.chunking import process_document

        txt = tmp_path / "Plane.txt"
        txt.write_text("Intro paragraph.\n\nSecond paragraph here.", encoding="utf-8")
        parents, children_map = process_document(
            str(txt), "Plane", "wiki", output_root=str(tmp_path / "out")
        )
        assert len(parents) == 1
        assert len(children_map) == 1
        assert (tmp_path / "out/parents/Plane/parent_1.json").exists()

    def test_process_document_full_roundtrip(self, tmp_path):
        from ingestion.chunking import process_document

        body = "\n\n".join(f"Paragraph {i} " + "x" * 300 for i in range(20))
        txt = tmp_path / "BigPlane.txt"
        txt.write_text(body, encoding="utf-8")
        parents, children_map = process_document(
            str(txt), "BigPlane", "pdf", output_root=str(tmp_path / "out")
        )
        assert len(parents) == len(children_map)
        assert all(len(children_map[i]) >= 1 for i in range(len(parents)))
        # every child text is a substring of its own parent
        for i, children in enumerate(children_map):
            for child in children:
                assert child in parents[i] or parents[i].startswith(child[:50])
