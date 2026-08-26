"""Conversation memory storage and compaction helpers."""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime
from typing import Any, Literal, Protocol

import psycopg2
from psycopg2.extras import Json, RealDictCursor
from pydantic import BaseModel, Field

from rag.result import estimate_tokens


MessageRole = Literal["user", "assistant"]


class ConversationMessage(BaseModel):
    sequence_number: int
    role: MessageRole
    content: str
    token_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class ConversationSession(BaseModel):
    id: str
    title: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    message_count: int = 0
    total_tokens: int = 0
    last_message: str | None = None


class ConversationContext(BaseModel):
    session_id: str
    summary: dict[str, Any] = Field(default_factory=dict)
    compacted_through: int = 0
    recent_messages: list[ConversationMessage] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.summary and not self.recent_messages

    def format_for_prompt(self, *, max_tokens: int) -> str:
        """Return a bounded prompt block; the full transcript stays in storage."""
        if self.is_empty() or max_tokens <= 0:
            return ""

        lines: list[str] = [f"session_id: {self.session_id}"]
        summary_text = json.dumps(self.summary, ensure_ascii=False, sort_keys=True)
        if summary_text and summary_text != "{}":
            lines.extend(["summary_json:", summary_text])

        remaining = max_tokens - estimate_tokens("\n".join(lines))
        if remaining <= 0:
            return _truncate_to_tokens("\n".join(lines), max_tokens)

        if self.recent_messages:
            lines.append("recent_turns:")
            for message in self.recent_messages:
                block = f"{message.role}[{message.sequence_number}]: {message.content}"
                block_tokens = estimate_tokens(block)
                if block_tokens > remaining:
                    if remaining > 20:
                        lines.append(_truncate_to_tokens(block, remaining))
                    break
                lines.append(block)
                remaining -= block_tokens
        return "\n".join(lines)


class ConversationMemoryStore(Protocol):
    def create_session(self, title: str | None = None) -> str:
        ...

    def session_exists(self, session_id: str) -> bool:
        ...

    def load_context(self, session_id: str, *, recent_token_budget: int) -> ConversationContext:
        ...

    def append_message(
        self,
        session_id: str,
        *,
        role: MessageRole,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        ...

    def compact_if_needed(
        self,
        session_id: str,
        *,
        generator_client: Any | None,
        model_name: str,
        trigger_tokens: int,
        keep_recent_messages: int,
        max_summary_tokens: int,
    ) -> bool:
        ...


class PostgresConversationMemoryStore:
    """PostgreSQL-backed conversation store used by the memory CLI."""

    def __init__(self, database_url: str | None = None):
        self._database_url = database_url or os.getenv("DATABASE_URL", "")

    def _connect(self) -> Any:
        if not self._database_url or "YOUR-PASSWORD" in self._database_url:
            raise RuntimeError("DATABASE_URL is required for conversation memory.")
        return psycopg2.connect(self._database_url, options="-c statement_timeout=10000")

    def ensure_chat_schema(self) -> None:
        connection = self._connect()
        try:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute("alter table conversation.sessions add column if not exists title text")
                    cursor.execute("alter table conversation.sessions add column if not exists archived_at timestamptz")
                    cursor.execute(
                        """
                        create index if not exists idx_conversation_sessions_active_updated_at
                        on conversation.sessions (updated_at desc)
                        where archived_at is null
                        """
                    )
        finally:
            connection.close()

    def create_session(self, title: str | None = None) -> str:
        session_id = str(uuid.uuid4())
        connection = self._connect()
        try:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        insert into conversation.sessions (id)
                        values (%s)
                        """,
                        (session_id,),
                    )
        finally:
            connection.close()
        if title:
            self.set_title_if_empty(session_id, title)
        return session_id

    def list_sessions(self, *, limit: int = 50, search: str | None = None) -> list[ConversationSession]:
        connection = self._connect()
        try:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                params: list[Any] = []
                where = "where s.archived_at is null"
                if search:
                    where += " and coalesce(s.title, '') ilike %s"
                    params.append(f"%{search.strip()}%")
                params.append(max(1, min(limit, 200)))
                cursor.execute(
                    f"""
                    select
                        s.id::text,
                        s.title,
                        s.created_at,
                        s.updated_at,
                        count(m.id)::int as message_count,
                        coalesce(sum(
                            case
                                when m.role = 'assistant'
                                 and (m.metadata->'token_usage'->>'total_tokens') ~ '^[0-9]+$'
                                then (m.metadata->'token_usage'->>'total_tokens')::int
                                else 0
                            end
                        ), 0)::int as total_tokens,
                        (
                            select content
                            from conversation.messages lm
                            where lm.session_id = s.id
                            order by lm.sequence_number desc
                            limit 1
                        ) as last_message
                    from conversation.sessions s
                    left join conversation.messages m on m.session_id = s.id
                    {where}
                    group by s.id, s.title, s.created_at, s.updated_at
                    order by s.updated_at desc
                    limit %s
                    """,
                    params,
                )
                return [ConversationSession(**row) for row in cursor.fetchall()]
        finally:
            connection.close()

    def load_messages(self, session_id: str) -> list[ConversationMessage]:
        connection = self._connect()
        try:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    select sequence_number, role, content, token_count, metadata, created_at
                    from conversation.messages
                    where session_id = %s
                    order by sequence_number asc
                    """,
                    (session_id,),
                )
                return [ConversationMessage(**row) for row in cursor.fetchall()]
        finally:
            connection.close()

    def rename_session(self, session_id: str, title: str) -> None:
        connection = self._connect()
        try:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        update conversation.sessions
                        set title = %s, updated_at = now()
                        where id = %s and archived_at is null
                        """,
                        (_clean_title(title), session_id),
                    )
                    if cursor.rowcount == 0:
                        raise KeyError(f"Conversation session not found: {session_id}")
        finally:
            connection.close()

    def delete_session(self, session_id: str) -> None:
        connection = self._connect()
        try:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute("delete from conversation.sessions where id = %s", (session_id,))
                    if cursor.rowcount == 0:
                        raise KeyError(f"Conversation session not found: {session_id}")
        finally:
            connection.close()

    def set_title_if_empty(self, session_id: str, title: str) -> None:
        cleaned = _clean_title(title)
        connection = self._connect()
        try:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        update conversation.sessions
                        set title = %s, updated_at = now()
                        where id = %s and nullif(btrim(coalesce(title, '')), '') is null
                        """,
                        (cleaned, session_id),
                    )
        finally:
            connection.close()

    def session_exists(self, session_id: str) -> bool:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select 1 from conversation.sessions where id = %s",
                    (session_id,),
                )
                return cursor.fetchone() is not None
        finally:
            connection.close()

    def load_context(self, session_id: str, *, recent_token_budget: int) -> ConversationContext:
        connection = self._connect()
        try:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    select id, summary, compacted_through
                    from conversation.sessions
                    where id = %s
                    """,
                    (session_id,),
                )
                session = cursor.fetchone()
                if session is None:
                    raise KeyError(f"Conversation session not found: {session_id}")

                cursor.execute(
                    """
                    select sequence_number, role, content, token_count, metadata, created_at
                    from conversation.messages
                    where session_id = %s and sequence_number > %s
                    order by sequence_number desc
                    limit 50
                    """,
                    (session_id, session["compacted_through"]),
                )
                rows = cursor.fetchall()
        finally:
            connection.close()

        recent: list[ConversationMessage] = []
        remaining = max(recent_token_budget, 0)
        if remaining <= 0:
            return ConversationContext(
                session_id=session_id,
                summary=dict(session["summary"] or {}),
                compacted_through=int(session["compacted_through"] or 0),
                recent_messages=[],
            )
        for row in rows:
            message = ConversationMessage(**row)
            tokens = message.token_count or estimate_tokens(message.content)
            if tokens > remaining and recent:
                break
            if tokens > remaining:
                message = message.model_copy(
                    update={"content": _truncate_to_tokens(message.content, remaining), "token_count": remaining}
                )
            recent.append(message)
            remaining -= min(tokens, remaining)
            if remaining <= 0:
                break

        recent.reverse()
        return ConversationContext(
            session_id=session_id,
            summary=dict(session["summary"] or {}),
            compacted_through=int(session["compacted_through"] or 0),
            recent_messages=recent,
        )

    def append_message(
        self,
        session_id: str,
        *,
        role: MessageRole,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        message_id = str(uuid.uuid4())
        token_count = estimate_tokens(content)
        connection = self._connect()
        try:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "select id from conversation.sessions where id = %s for update",
                        (session_id,),
                    )
                    if cursor.fetchone() is None:
                        raise KeyError(f"Conversation session not found: {session_id}")
                    cursor.execute(
                        """
                        select coalesce(max(sequence_number), 0) + 1
                        from conversation.messages
                        where session_id = %s
                        """,
                        (session_id,),
                    )
                    sequence_number = int(cursor.fetchone()[0])
                    cursor.execute(
                        """
                        insert into conversation.messages (
                            id, session_id, sequence_number, role, content,
                            token_count, metadata
                        ) values (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            message_id,
                            session_id,
                            sequence_number,
                            role,
                            content,
                            token_count,
                            Json(metadata or {}),
                        ),
                    )
                    cursor.execute(
                        "update conversation.sessions set updated_at = now() where id = %s",
                        (session_id,),
                    )
        finally:
            connection.close()
        return sequence_number

    def compact_if_needed(
        self,
        session_id: str,
        *,
        generator_client: Any | None,
        model_name: str,
        trigger_tokens: int,
        keep_recent_messages: int,
        max_summary_tokens: int,
    ) -> bool:
        session, messages = self._load_uncompacted(session_id)
        summary = dict(session["summary"] or {})
        total_tokens = estimate_tokens(json.dumps(summary, ensure_ascii=False)) + sum(
            int(message["token_count"] or estimate_tokens(message["content"])) for message in messages
        )
        if total_tokens <= trigger_tokens:
            return False

        keep_count = max(keep_recent_messages, 0)
        compactable = messages[:-keep_count] if keep_count and len(messages) > keep_count else []
        if not compactable and len(messages) > 1:
            compactable = messages[:-1]
        if not compactable:
            compactable = messages
        if not compactable:
            return False

        new_summary = compact_messages(
            previous_summary=summary,
            messages=[ConversationMessage(**message) for message in compactable],
            generator_client=generator_client,
            model_name=model_name,
            max_summary_tokens=max_summary_tokens,
        )
        compacted_through = int(compactable[-1]["sequence_number"])
        self._update_summary(session_id, new_summary, compacted_through)
        return True

    def _load_uncompacted(self, session_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        connection = self._connect()
        try:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    select id, summary, compacted_through
                    from conversation.sessions
                    where id = %s
                    """,
                    (session_id,),
                )
                session = cursor.fetchone()
                if session is None:
                    raise KeyError(f"Conversation session not found: {session_id}")
                cursor.execute(
                    """
                    select sequence_number, role, content, token_count, metadata, created_at
                    from conversation.messages
                    where session_id = %s and sequence_number > %s
                    order by sequence_number asc
                    """,
                    (session_id, session["compacted_through"]),
                )
                return dict(session), [dict(row) for row in cursor.fetchall()]
        finally:
            connection.close()

    def _update_summary(self, session_id: str, summary: dict[str, Any], compacted_through: int) -> None:
        connection = self._connect()
        try:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        update conversation.sessions
                        set summary = %s,
                            compacted_through = greatest(compacted_through, %s),
                            version = version + 1,
                            updated_at = now()
                        where id = %s
                        """,
                        (Json(summary), compacted_through, session_id),
                    )
        finally:
            connection.close()


SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "objective": {"type": "string"},
        "entities": {"type": "object", "additionalProperties": {"type": "string"}},
        "preferences": {"type": "object", "additionalProperties": {"type": "string"}},
        "references": {"type": "object", "additionalProperties": {"type": "string"}},
        "pending_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["objective", "entities", "preferences", "references", "pending_questions"],
    "additionalProperties": False,
}


def compact_messages(
    *,
    previous_summary: dict[str, Any],
    messages: list[ConversationMessage],
    generator_client: Any | None,
    model_name: str,
    max_summary_tokens: int,
) -> dict[str, Any]:
    if generator_client is None or not messages:
        return deterministic_summary(previous_summary, messages, max_summary_tokens=max_summary_tokens)

    transcript = "\n".join(f"{m.role}[{m.sequence_number}]: {m.content}" for m in messages)
    prompt_input = f"""
<previous_summary>
{json.dumps(previous_summary, ensure_ascii=False, sort_keys=True)}
</previous_summary>

<new_turns>
{transcript}
</new_turns>
"""
    try:
        response = generator_client.responses.create(
            model=model_name,
            instructions=(
                "Update the conversation memory. Keep only durable context needed "
                "for future turns: user objective, active entities, references, "
                "preferences, corrections and pending questions. Do not include "
                "retrieved evidence text. Do not invent facts. Assistant answers are "
                "not authoritative aviation evidence. Return the strict JSON schema."
            ),
            input=prompt_input,
            max_output_tokens=max_summary_tokens,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "conversation_summary",
                    "strict": True,
                    "schema": SUMMARY_SCHEMA,
                }
            },
        )
        summary = json.loads(response.output_text)
        return _limit_summary(summary, max_summary_tokens=max_summary_tokens)
    except Exception:
        return deterministic_summary(previous_summary, messages, max_summary_tokens=max_summary_tokens)


def deterministic_summary(
    previous_summary: dict[str, Any],
    messages: list[ConversationMessage],
    *,
    max_summary_tokens: int,
) -> dict[str, Any]:
    summary = {
        "objective": str(previous_summary.get("objective") or "").strip(),
        "entities": dict(previous_summary.get("entities") or {}),
        "preferences": dict(previous_summary.get("preferences") or {}),
        "references": dict(previous_summary.get("references") or {}),
        "pending_questions": list(previous_summary.get("pending_questions") or []),
    }
    user_messages = [m.content for m in messages if m.role == "user"]
    if user_messages:
        last_user = user_messages[-1]
        summary["objective"] = _truncate_to_tokens(
            summary["objective"] or f"Recent user focus: {last_user}",
            max(40, max_summary_tokens // 3),
        )
        aircraft = _extract_aircraft(last_user)
        if aircraft:
            summary["entities"]["active_aircraft"] = aircraft
            summary["references"].setdefault("it", aircraft)
            summary["references"].setdefault("su", aircraft)
    return _limit_summary(summary, max_summary_tokens=max_summary_tokens)


def _limit_summary(summary: dict[str, Any], *, max_summary_tokens: int) -> dict[str, Any]:
    text = json.dumps(summary, ensure_ascii=False)
    if estimate_tokens(text) <= max_summary_tokens:
        return summary
    limited = dict(summary)
    limited["objective"] = _truncate_to_tokens(str(limited.get("objective") or ""), max_summary_tokens // 2)
    limited["pending_questions"] = []
    return limited


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    if max_tokens <= 0:
        return ""
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 15)].rstrip() + "... [truncated]"


def _extract_aircraft(text: str) -> str | None:
    patterns = [
        r"\b(Cessna\s+\w[\w-]*)\b",
        r"\b(Piper\s+\w[\w-]*)\b",
        r"\b(Boeing\s+\w[\w-]*)\b",
        r"\b(Airbus\s+\w[\w-]*)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _clean_title(title: str | None) -> str:
    text = re.sub(r"\s+", " ", str(title or "")).strip()
    if not text:
        return "Untitled chat"
    if len(text) <= 72:
        return text
    return text[:69].rstrip() + "..."
