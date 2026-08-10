"""
Hybrid search debug tool.

Runs the same question through the two search legs separately and through
the hybrid function, then shows them side by side:

  1. VECTOR leg:  top children by embedding similarity (HNSW).
  2. KEYWORD leg: top children by ts_rank with OR semantics (GIN).
  3. HYBRID:      the real find_similar_parents_hybrid result, annotated
                  with the rank each parent had in EACH leg, so you can
                  see which leg actually contributed to the final list.

If every hybrid result shows a rank in both columns, both legs matter.
If a column is all "-", that leg is contributing nothing for that question.

Usage:
    python -m rag.hybrid_debug
"""

import os

from dotenv import load_dotenv
from pgvector import Vector
from pgvector.psycopg2 import register_vector
import psycopg2
from psycopg2.extras import RealDictCursor

from ingestion.embedder import embed_text

load_dotenv()

db_connection = psycopg2.connect(os.environ["DATABASE_URL"])
register_vector(db_connection)

CANDIDATES = 10
TOP_K = 5

# Same logic as the vec CTE in find_similar_parents_hybrid.
VEC_SQL = """
    select parent_id,
           row_number() over (order by embedding <=> %s) as rnk,
           1 - (embedding <=> %s) as similarity
    from documents
    where parent_id is not null
    order by embedding <=> %s
    limit %s
"""

# Same logic as the kw CTE in find_similar_parents_hybrid.
KW_SQL = """
    select d.parent_id,
           row_number() over (order by ts_rank(d.texto_tsv, t.q) desc) as rnk,
           ts_rank(d.texto_tsv, t.q) as kw_score
    from documents d
    cross join lateral (
        select string_agg(lexeme, ' | ' order by lexeme)::tsquery as q
        from unnest(tsvector_to_array(to_tsvector('english', %s))) as lex(lexeme)
    ) t
    where d.parent_id is not null
      and t.q is not null
      and d.texto_tsv @@ t.q
    order by ts_rank(d.texto_tsv, t.q) desc
    limit %s
"""

TSQUERY_SQL = """
    select string_agg(lexeme, ' | ' order by lexeme)::tsquery as q
    from unnest(tsvector_to_array(to_tsvector('english', %s))) as lex(lexeme)
"""


def best_rank_per_parent(rows):
    """Several children can share a parent; keep the best (lowest) rank."""
    ranks = {}
    for row in rows:
        pid = row["parent_id"]
        if pid not in ranks or row["rnk"] < ranks[pid]["rnk"]:
            ranks[pid] = row
    return ranks


def print_leg(title, ranks, score_key, score_label):
    print(f"\n-- {title} --")
    if not ranks:
        print("  (empty: this leg found nothing)")
        return
    print(f"  {'rank':>4}  {'parent_id':<35} {score_label:>8}")
    for pid, row in sorted(ranks.items(), key=lambda kv: kv[1]["rnk"]):
        print(f"  {row['rnk']:>4}  {pid:<35} {row[score_key]:>8.4f}")


def main():
    question = input("Question: ")
    query_vector = embed_text(question)

    with db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(TSQUERY_SQL, (question,))
        tsquery_row = cursor.fetchone()
        tsquery = tsquery_row["q"] if tsquery_row else None

        cursor.execute(VEC_SQL, (Vector(query_vector),) * 3 + (CANDIDATES,))
        vec_ranks = best_rank_per_parent(cursor.fetchall())

        cursor.execute(KW_SQL, (question, CANDIDATES))
        kw_ranks = best_rank_per_parent(cursor.fetchall())

        cursor.execute(
            "select * from find_similar_parents_hybrid(%s, %s, null, %s)",
            (Vector(query_vector), question, TOP_K),
        )
        hybrid_rows = cursor.fetchall()

    print(f"\nKeyword lexemes (OR): {tsquery if tsquery else '(none: only stop words)'}")

    print_leg("VECTOR leg (cosine similarity)", vec_ranks, "similarity", "cosine")
    print_leg("KEYWORD leg (ts_rank)", kw_ranks, "kw_score", "ts_rank")

    print("\n-- HYBRID result (what the LLM actually sees) --")
    print(f"  {'parent_id':<35} {'vec':>4} {'kw':>4} {'rrf':>8}  source")
    both = only_vec = only_kw = 0
    for row in hybrid_rows:
        pid = row["chunk_id"]
        vec = str(vec_ranks[pid]["rnk"]) if pid in vec_ranks else "-"
        kw = str(kw_ranks[pid]["rnk"]) if pid in kw_ranks else "-"
        print(f"  {pid:<35} {vec:>4} {kw:>4} {row['similarity']:>8.4f}  "
              f"{row['aircraft']} / {row['font']}")
        if pid in vec_ranks and pid in kw_ranks:
            both += 1
        elif pid in vec_ranks:
            only_vec += 1
        else:
            only_kw += 1

    print(f"\nVerdict: {both} of {len(hybrid_rows)} results were found by BOTH legs, "
          f"{only_vec} only by vector, {only_kw} only by keyword.")
    if both == 0 and only_kw == 0:
        print("The keyword leg contributed NOTHING to this question "
              "(pure vector result).")
    elif only_kw > 0:
        print("The keyword leg rescued documents the vector leg missed "
              "-- that is exactly what hybrid search is for.")


if __name__ == "__main__":
    main()
