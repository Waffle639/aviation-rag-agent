"""
Shared fixtures and test-session configuration for the Aviation RAG suite.

Layers
------
unit/         No network, no DB, no API keys — every external dependency mocked.
integration/  Filesystem pipeline over the real corpus; DB tests need --live.
e2e/          Full RAG pipeline — mocked services by default, real with --live.
eval/         RAG quality evals (golden dataset) — real services, needs --live.

Why the import machinery exists
-------------------------------
ingestion/embedder.py, rag/retrival.py and rag/hybrid_debug.py open a real
Postgres connection AT IMPORT TIME, and rag/generator.py refuses to import
without OPENAI_API_KEY. Unit tests therefore import those modules through the
``import_fresh`` fixture, which patches psycopg2.connect / OpenAI /
register_vector / wrap_openai *before* the import happens and cleans
sys.modules afterwards so each test gets a pristine module.

rag.guardrails is import-safe and is NEVER reloaded here: GuardrailError's
class identity must stay stable across the whole session or pytest.raises()
in different modules would stop matching.
"""

import importlib
import os
import sys
from contextlib import contextmanager
from types import SimpleNamespace
from unittest import mock

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

LIVE_MODE = "--live" in sys.argv

if LIVE_MODE:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
else:
    # Dummy credentials so import-time guards pass and no real service is
    # ever touched. load_dotenv() does not override existing env vars, so
    # the real .env cannot leak into the mocked session.
    os.environ["OPENAI_API_KEY"] = "sk-test-dummy-key"
    os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:9/testdb"
    os.environ["HF_TOKEN"] = "hf-test-dummy"
    os.environ["RAG_SECURITY"] = "true"
    os.environ["RAG_MAX_QUESTION_CHARS"] = "1000"
    os.environ["RAG_MAX_CONTEXT_CHARS"] = "16000"
    os.environ["RAG_MAX_OUTPUT_TOKENS"] = "2000"

# Never send LangSmith traces during tests.
os.environ["LANGSMITH_TRACING"] = "false"


def pytest_addoption(parser):
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="run tests that call real external services (Supabase, OpenAI, HF)",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--live"):
        return
    skip_live = pytest.mark.skip(reason="needs --live (real external services)")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


# ---------------------------------------------------------------------------
# Import machinery for modules with import-time side effects
# ---------------------------------------------------------------------------

#: Modules that open DB connections or build API clients at import time.
_SIDE_EFFECT_MODULES = (
    "ingestion.embedder",
    "rag.retrival",
    "rag.generator",
    "rag.hybrid_debug",
    "rag.query_test",
)


def make_connection_mock():
    """psycopg2 connection mock whose cursor() works as a context manager."""
    connection = mock.MagicMock(name="db_connection")
    cursor = mock.MagicMock(name="db_cursor")
    connection.cursor.return_value.__enter__.return_value = cursor
    connection.cursor.return_value.__exit__.return_value = False
    return connection, cursor


@pytest.fixture
def import_fresh():
    """
    Import project modules with every external dependency mocked.

    Usage::

        with import_fresh("ingestion.embedder") as mods:
            embedder = mods["ingestion.embedder"]
            patches = mods["__patches__"]   # .connect / .openai / .register_vector
    """

    @contextmanager
    def _import(*module_names):
        to_pop = set(module_names) | set(_SIDE_EFFECT_MODULES)
        with (
            mock.patch("psycopg2.connect") as mock_connect,
            mock.patch("pgvector.psycopg2.register_vector") as mock_register,
            mock.patch(
                "langsmith.wrappers.wrap_openai", side_effect=lambda c: c
            ),
            mock.patch("rag.guardrails._openai_client", None),
            mock.patch("rag.guardrails._get_openai_client") as mock_moderation_client,
            mock.patch("openai.OpenAI") as mock_openai,
        ):
            connection, cursor = make_connection_mock()
            mock_connect.return_value = connection
            moderation_response = SimpleNamespace(
                results=[SimpleNamespace(flagged=False, categories=SimpleNamespace())]
            )
            mock_moderation_client.return_value.moderations.create.return_value = (
                moderation_response
            )
            for name in to_pop:
                sys.modules.pop(name, None)
            try:
                mods: dict[str, object] = {
                    name: importlib.import_module(name) for name in module_names
                }
                mods["__patches__"] = SimpleNamespace(
                    connect=mock_connect,
                    connection=connection,
                    cursor=cursor,
                    register_vector=mock_register,
                    openai_cls=mock_openai,
                )
                yield mods
            finally:
                for name in to_pop:
                    sys.modules.pop(name, None)

    return _import


# ---------------------------------------------------------------------------
# Sample data factories (mirror data/processed/*.json shapes)
# ---------------------------------------------------------------------------


@pytest.fixture
def make_chunk():
    """Factory for child-chunk dicts shaped like data/processed/chunks/*.json."""

    def _make(
        chunk_id="boeing_747_wiki_c000",
        parent_id="boeing_747_wiki_p000",
        aircraft="Boeing_747",
        font="wiki",
        texto="The Boeing 747's first flight took place on February 9, 1969.",
    ):
        return {
            "texto": texto,
            "metadata": {
                "aeronave": aircraft,
                "fuente": font,
                "chunk_id": chunk_id,
                "parent_id": parent_id,
            },
        }

    return _make


@pytest.fixture
def make_parent():
    """Factory for parent dicts shaped like data/processed/parents/*.json."""

    def _make(
        parent_id="boeing_747_wiki_p000",
        aircraft="Boeing_747",
        font="wiki",
        texto="The Boeing 747 is a long-range wide-body airliner. " * 20,
    ):
        return {
            "texto": texto,
            "metadata": {
                "aeronave": aircraft,
                "fuente": font,
                "parent_id": parent_id,
            },
        }

    return _make


@pytest.fixture
def make_retrieved_row():
    """Factory for rows returned by find_similar_parents_hybrid."""

    def _make(
        chunk_id="boeing_747_wiki_p000",
        aircraft="Boeing_747",
        font="wiki",
        texto="The Boeing 747's first flight took place on February 9, 1969.",
        similarity=0.42,
    ):
        return {
            "texto": texto,
            "aircraft": aircraft,
            "font": font,
            "chunk_id": chunk_id,
            "similarity": similarity,
        }

    return _make


# ---------------------------------------------------------------------------
# Guardrail helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def benign_detector():
    """Prompt Guard mock that always says BENIGN."""
    detector = mock.Mock(name="benign_detector")
    detector.classify.return_value = ("BENIGN", 0.01)
    return detector


@pytest.fixture
def malicious_detector():
    """Prompt Guard mock that always says MALICIOUS."""
    detector = mock.Mock(name="malicious_detector")
    detector.classify.return_value = ("MALICIOUS", 0.99)
    return detector


@pytest.fixture
def clean_moderation_client():
    """OpenAI client mock whose moderation endpoint never flags."""
    client = mock.Mock(name="openai_moderation_client")
    client.moderations.create.return_value = SimpleNamespace(
        results=[
            SimpleNamespace(
                flagged=False,
                categories=SimpleNamespace(
                    hate=False, violence=False, self_harm=False, sexual=False
                ),
            )
        ]
    )
    return client


# ---------------------------------------------------------------------------
# Live-service fixtures (only exercised with --live)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def live_database_url():
    url = os.environ.get("DATABASE_URL", "")
    if not url or "YOUR-PASSWORD" in url or "localhost:9" in url:
        pytest.skip("live DATABASE_URL not configured")
    return url


@pytest.fixture
def live_db(live_database_url):
    """Real Postgres connection (vector type registered), closed after use."""
    import psycopg2
    from pgvector.psycopg2 import register_vector

    conn = psycopg2.connect(
        live_database_url, options="-c statement_timeout=15000"
    )
    register_vector(conn)
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def live_openai_key():
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key or key == "sk-test-dummy-key":
        pytest.skip("live OPENAI_API_KEY not configured")
    return key
