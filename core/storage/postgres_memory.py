"""Transactional Postgres/pgvector repository for Orange memory.

The repository is deliberately synchronous.  API and MCP call sites should run
its methods with ``asyncio.to_thread`` so psycopg and embedding calls never
block the event loop.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timezone
from enum import Enum
from typing import Any, Iterable, Sequence
from uuid import UUID, uuid4

from psycopg.types.json import Json

from core.graph_schema_v2 import Insight, Session, SourceType, validate_node
from core.graph_upsert.embeddings import build_insight_embed_string
from core.ingestion import NormalizedSession, normalize_ingestion_request
from core.storage.embeddings import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    EmbeddingProvider,
    OpenAIEmbeddingProvider,
    vector_literal,
)
from core.storage.supabase_store import OrangePostgresStore, _slugify, _uuid_or_none


_VALID_SCOPES = {"user", "global", "both"}
_SAFE_ID_RE = re.compile(r"[^a-zA-Z0-9_-]+")


@dataclass(frozen=True)
class ResolvedMemoryIdentity:
    """Internal owner IDs resolved from an external/authenticated identity."""

    user_db_id: str | None = None
    organization_db_id: str | None = None
    external_user_id: str | None = None
    user_email: str | None = None
    organization_slug: str | None = None


@dataclass
class UpsertSummary:
    """Counters compatible with Orange's former graph writer response."""

    sessions_written: int = 0
    insights_stored: int = 0
    insights_skipped: int = 0
    similar_to_edges_written: int = 0
    edges_written: int = 0
    edges_skipped: int = 0
    skipped_by_idempotency: int = 0
    canonical_merges: int = 0

    # Compatibility counters from the retired Problem/Solution graph.
    concepts_written: int = 0
    problems_created: int = 0
    problems_merged: int = 0
    solutions_written: int = 0
    cross_session_links_written: int = 0
    related_to_edges_written: int = 0


def _enum_value(value: Enum | str) -> str:
    return str(value.value if isinstance(value, Enum) else value)


def _json(value: Any) -> Json:
    return Json(value if value is not None else {})


def _clean_scope(value: str, *, allow_both: bool = False) -> str:
    scope = str(value or "user").strip().lower()
    accepted = _VALID_SCOPES if allow_both else {"user", "global"}
    if scope not in accepted:
        raise ValueError(f"scope must be one of: {', '.join(sorted(accepted))}")
    return scope


def _clean_limit(value: int, *, maximum: int = 500) -> int:
    return min(max(int(value or 1), 1), maximum)


def _safe_node_fragment(value: str, fallback: str) -> str:
    cleaned = _SAFE_ID_RE.sub("_", str(value or "").strip()).strip("_")
    return (cleaned or fallback)[:64]


def scoped_session_node_id_for(scope: str, owner: str, session_node_id: str) -> str:
    """Derive a globally unique, retry-stable graph session ID."""

    raw = f"{scope}:{owner}:{session_node_id}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    fragment = _safe_node_fragment(session_node_id, "session")
    return f"{fragment}_{digest}"


def insight_node_id_for(scope_owner: str, session_id: str, display_label: str, what: str) -> str:
    raw = f"{scope_owner}:{session_id}:{display_label}:{what}"
    return f"insight_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _row_dict(row: Any | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {str(key): _json_safe(value) for key, value in dict(row).items()}


def _merge_how(existing: str | None, incoming: str | None) -> str | None:
    old = str(existing or "").strip()
    new = str(incoming or "").strip()
    if not new or new in old:
        return old or None
    if not old:
        return new
    return f"{old}\n{new}"


def _embedding_text_from_row(row: dict[str, Any], *, how: str | None, tags: Sequence[str]) -> str:
    parts = [
        str(row.get("what") or ""),
        str(row.get("why") or ""),
        str(how or ""),
        str(row.get("memory_kind") or "technical_insight"),
        " ".join(str(tag) for tag in tags),
    ]
    return " ".join(part.strip() for part in parts if part.strip())


class PostgresMemoryRepository(OrangePostgresStore):
    """One Postgres repository for ingestion, graph, vectors, and jobs."""

    def __init__(
        self,
        dsn: str | None = None,
        *,
        pool: Any | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        min_pool_size: int = 1,
        max_pool_size: int = 5,
        open_pool: bool = True,
    ) -> None:
        if pool is None:
            super().__init__(
                str(dsn or ""),
                min_pool_size=min_pool_size,
                max_pool_size=max_pool_size,
                open_pool=open_pool,
            )
            self._owns_pool = True
        else:
            self.pool = pool
            self._owns_pool = False
        self._embedding_provider = embedding_provider

    def close(self) -> None:
        if self._owns_pool:
            super().close()

    @property
    def embedding_provider(self) -> EmbeddingProvider:
        if self._embedding_provider is None:
            self._embedding_provider = OpenAIEmbeddingProvider()
        if int(getattr(self._embedding_provider, "dimensions", 0)) != DEFAULT_EMBEDDING_DIMENSIONS:
            raise RuntimeError(
                f"Orange requires {DEFAULT_EMBEDDING_DIMENSIONS}-dimension embeddings."
            )
        return self._embedding_provider

    @property
    def embedding_model(self) -> str:
        return str(getattr(self.embedding_provider, "model", DEFAULT_EMBEDDING_MODEL))

    # ------------------------------------------------------------------
    # Identity resolution

    def get_or_create_identity(
        self,
        *,
        user_id: str | None = None,
        user_email: str | None = None,
        auth_user_id: str | None = None,
        org_id: str | None = None,
        organization_name: str | None = None,
        create_membership: bool = True,
    ) -> ResolvedMemoryIdentity:
        """Resolve/create graph owners, normally from verified OAuth claims."""

        with self.pool.connection() as conn:
            with conn.transaction():
                return self._get_or_create_identity_conn(
                    conn,
                    user_id=user_id,
                    user_email=user_email,
                    auth_user_id=auth_user_id,
                    org_id=org_id,
                    organization_name=organization_name,
                    create_membership=create_membership,
                )

    def _get_or_create_identity_conn(
        self,
        conn: Any,
        *,
        user_id: str | None,
        user_email: str | None,
        auth_user_id: str | None,
        org_id: str | None,
        organization_name: str | None = None,
        create_membership: bool = True,
    ) -> ResolvedMemoryIdentity:
        clean_external_user = str(user_id or user_email or auth_user_id or "").strip() or None
        clean_email = str(user_email or "").strip().lower() or None
        clean_auth_id = _uuid_or_none(auth_user_id)
        clean_org = _slugify(org_id) if org_id else None

        organization_db_id: str | None = None
        organization_created = False
        if clean_org:
            row = conn.execute(
                """/* orange:upsert-organization */
                insert into orange.organizations (external_org_id, slug, name, metadata)
                values (%s, %s, %s, '{}'::jsonb)
                on conflict (slug) do update set
                  external_org_id = coalesce(
                    orange.organizations.external_org_id,
                    excluded.external_org_id
                  ),
                  name = coalesce(nullif(excluded.name, ''), orange.organizations.name)
                returning id, (xmax = 0) as created
                """,
                (org_id, clean_org, organization_name or org_id or clean_org),
            ).fetchone()
            organization_db_id = str(row["id"])
            organization_created = bool(row.get("created"))

        user_db_id: str | None = None
        if clean_external_user or clean_email or clean_auth_id:
            existing = conn.execute(
                """/* orange:find-user-for-upsert */
                select id
                from orange.users
                where (%s::uuid is not null and auth_user_id = %s::uuid)
                   or (%s::text is not null and external_user_id = %s::text)
                   or (%s::text is not null and lower(email) = %s::text)
                order by (auth_user_id = %s::uuid) desc nulls last
                limit 1
                for update
                """,
                (
                    clean_auth_id,
                    clean_auth_id,
                    clean_external_user,
                    clean_external_user,
                    clean_email,
                    clean_email,
                    clean_auth_id,
                ),
            ).fetchone()
            if existing:
                row = conn.execute(
                    """/* orange:update-user-identity */
                    update orange.users
                    set auth_user_id = coalesce(%s::uuid, auth_user_id),
                        external_user_id = coalesce(external_user_id, %s),
                        email = coalesce(%s, email),
                        display_name = coalesce(display_name, %s)
                    where id = %s
                    returning id
                    """,
                    (clean_auth_id, clean_external_user, clean_email, clean_external_user, existing["id"]),
                ).fetchone()
            else:
                row = conn.execute(
                    """/* orange:insert-user-identity */
                    insert into orange.users (
                      auth_user_id, external_user_id, email, display_name, metadata
                    ) values (%s::uuid, %s, %s, %s, '{}'::jsonb)
                    returning id
                    """,
                    (clean_auth_id, clean_external_user, clean_email, clean_external_user),
                ).fetchone()
            user_db_id = str(row["id"])

        if create_membership and organization_db_id and user_db_id:
            if organization_created:
                conn.execute(
                    """/* orange:upsert-membership */
                    insert into orange.organization_members (
                      organization_id, user_id, membership_role
                    ) values (%s, %s, 'owner')
                    on conflict (organization_id, user_id) do nothing
                    """,
                    (organization_db_id, user_db_id),
                )
            else:
                membership = conn.execute(
                    """/* orange:require-membership */
                    select 1
                    from orange.organization_members
                    where organization_id = %s::uuid and user_id = %s::uuid
                    limit 1
                    """,
                    (organization_db_id, user_db_id),
                ).fetchone()
                if not membership:
                    raise PermissionError(
                        "The authenticated user is not a member of this Orange organization."
                    )

        return ResolvedMemoryIdentity(
            user_db_id=user_db_id,
            organization_db_id=organization_db_id,
            external_user_id=clean_external_user,
            user_email=clean_email,
            organization_slug=clean_org,
        )

    def resolve_identity(
        self,
        *,
        user_id: str | None = None,
        user_email: str | None = None,
        org_id: str | None = None,
    ) -> ResolvedMemoryIdentity:
        """Read an existing owner without silently provisioning accounts."""

        with self.pool.connection() as conn:
            return self._resolve_identity_conn(
                conn, user_id=user_id, user_email=user_email, org_id=org_id
            )

    def _resolve_identity_conn(
        self,
        conn: Any,
        *,
        user_id: str | None,
        user_email: str | None,
        org_id: str | None,
    ) -> ResolvedMemoryIdentity:
        clean_user = str(user_id or "").strip() or None
        clean_email = str(user_email or "").strip().lower() or None
        clean_org = _slugify(org_id) if org_id else None
        user_row = None
        org_row = None
        if clean_user or clean_email:
            user_row = conn.execute(
                """/* orange:resolve-user */
                select id, external_user_id, lower(email) as email
                from orange.users
                where (%s::text is not null and (
                        id::text = %s::text
                        or auth_user_id::text = %s::text
                        or external_user_id = %s::text
                      ))
                   or (%s::text is not null and lower(email) = %s::text)
                order by (auth_user_id::text = %s::text) desc nulls last
                limit 1
                """,
                (clean_user, clean_user, clean_user, clean_user, clean_email, clean_email, clean_user),
            ).fetchone()
        if clean_org:
            org_row = conn.execute(
                """/* orange:resolve-organization */
                select id, slug
                from orange.organizations
                where slug = %s or external_org_id = %s
                limit 1
                """,
                (clean_org, org_id),
            ).fetchone()
            if org_row:
                membership = None
                if user_row:
                    membership = conn.execute(
                        """/* orange:authorize-resolved-organization */
                        select 1
                        from orange.organization_members
                        where organization_id = %s::uuid and user_id = %s::uuid
                        limit 1
                        """,
                        (org_row["id"], user_row["id"]),
                    ).fetchone()
                if not membership:
                    org_row = None
        return ResolvedMemoryIdentity(
            user_db_id=str(user_row["id"]) if user_row else None,
            organization_db_id=str(org_row["id"]) if org_row else None,
            external_user_id=(str(user_row.get("external_user_id") or "") or clean_user) if user_row else clean_user,
            user_email=(str(user_row.get("email") or "") or clean_email) if user_row else clean_email,
            organization_slug=str(org_row.get("slug") or clean_org) if org_row else clean_org,
        )

    def is_organization_member(self, *, organization_id: str, user_id: str) -> bool:
        """Return whether internal Orange IDs have an explicit membership."""

        with self.pool.connection() as conn:
            row = conn.execute(
                """/* orange:is-organization-member */
                select 1
                from orange.organization_members
                where organization_id = %s::uuid and user_id = %s::uuid
                limit 1
                """,
                (organization_id, user_id),
            ).fetchone()
        return bool(row)

    def resolve_authorized_organization(
        self,
        *,
        org_id: str,
        user_id: str | None = None,
        user_email: str | None = None,
    ) -> ResolvedMemoryIdentity:
        """Resolve an existing organization and require explicit membership."""

        identity = self.resolve_identity(
            user_id=user_id, user_email=user_email, org_id=org_id
        )
        if not identity.user_db_id or not identity.organization_db_id:
            raise PermissionError("A valid Orange user and organization are required.")
        if not self.is_organization_member(
            organization_id=identity.organization_db_id,
            user_id=identity.user_db_id,
        ):
            raise PermissionError(
                "The authenticated user is not a member of this Orange organization."
            )
        return identity

    # ------------------------------------------------------------------
    # Transactional graph/vector write path

    def upsert_insights(
        self,
        *,
        session: Session,
        user_id: str,
        insights: list[Insight],
        scope: str = "user",
        user_email: str | None = None,
        auth_user_id: str | None = None,
        contributed_by: str | None = None,
        org_id: str | None = None,
        company: str | None = None,
        source_ingestion_id: str | None = None,
        similarity_threshold: float = 0.88,
        canonical_threshold: float = 0.95,
    ) -> UpsertSummary:
        """Atomically upsert a session, insights, embeddings, and graph edges."""

        summary = UpsertSummary()
        if not insights:
            return summary
        clean_scope = _clean_scope(scope)
        validate_node(session)
        if clean_scope == "user" and not (user_id or user_email or auth_user_id):
            raise ValueError("A user identity is required for user memory.")
        resolved_org = org_id or session.org_id
        if clean_scope == "global" and not resolved_org:
            raise ValueError("org_id is required for global memory.")

        prepared: list[tuple[Insight, str, list[float]]] = []
        for insight in insights:
            document = build_insight_embed_string(insight)
            if not document:
                raise ValueError("Insight embedding content must not be empty.")
            prepared.append((insight, document, []))
        vectors = self.embedding_provider.embed([item[1] for item in prepared])
        prepared = [
            (insight, document, vector)
            for (insight, document, _), vector in zip(prepared, vectors, strict=True)
        ]

        owner_key = (
            f"org:{_slugify(resolved_org)}"
            if clean_scope == "global"
            else f"user:{str(user_email or user_id or auth_user_id).strip().lower()}"
        )
        original_session_node_id = session.node_id
        session_node_id = scoped_session_node_id_for(
            clean_scope, owner_key, original_session_node_id
        )

        with self.pool.connection() as conn:
            with conn.transaction():
                identity = self._get_or_create_identity_conn(
                    conn,
                    user_id=user_id,
                    user_email=user_email,
                    auth_user_id=auth_user_id,
                    org_id=resolved_org,
                    organization_name=company,
                    create_membership=True,
                )
                if clean_scope == "user" and not identity.user_db_id:
                    raise ValueError("Could not resolve the private memory owner.")
                if clean_scope == "global" and not identity.organization_db_id:
                    raise ValueError("Could not resolve the global memory owner.")

                session_row = conn.execute(
                    """/* orange:insert-memory-session */
                    insert into orange.memory_sessions (
                      node_id, idempotency_key, source_ingestion_id, scope,
                      user_id, user_email, organization_id,
                      contributed_by_user_id, contributed_by, source,
                      conversation_type, resolution_status, title, summary,
                      message_count, external_session_id, participants,
                      client_name, client_version, source_url, started_at,
                      ended_at, ingested_at, extraction_version, metadata
                    ) values (
                      %s, %s, %s::uuid, %s,
                      %s::uuid, %s, %s::uuid,
                      %s::uuid, %s, %s,
                      %s, %s, %s, %s,
                      %s, %s, %s,
                      %s, %s, %s, %s,
                      %s, %s, %s, %s
                    )
                    on conflict (idempotency_key) do nothing
                    returning id, node_id
                    """,
                    (
                        session_node_id,
                        session_node_id,
                        _uuid_or_none(source_ingestion_id),
                        clean_scope,
                        identity.user_db_id if clean_scope == "user" else None,
                        identity.user_email if clean_scope == "user" else None,
                        identity.organization_db_id if clean_scope == "global" else None,
                        identity.user_db_id if clean_scope == "global" else None,
                        contributed_by if clean_scope == "global" else None,
                        _enum_value(session.source),
                        _enum_value(session.conversation_type),
                        _enum_value(session.resolution_status),
                        session.title,
                        session.summary,
                        session.message_count,
                        session.external_session_id,
                        list(session.participants),
                        session.client_name,
                        session.client_version,
                        session.source_url,
                        session.started_at,
                        session.ended_at,
                        session.ingested_at,
                        session.extraction_version,
                        _json({"original_node_id": original_session_node_id}),
                    ),
                ).fetchone()
                if session_row:
                    summary.sessions_written = 1
                else:
                    session_row = conn.execute(
                        """/* orange:get-memory-session-idempotent */
                        select id, node_id
                        from orange.memory_sessions
                        where idempotency_key = %s
                        """,
                        (session_node_id,),
                    ).fetchone()
                    if not session_row:
                        raise RuntimeError("Idempotent memory session could not be loaded.")
                    summary.skipped_by_idempotency += 1

                session_db_id = str(session_row["id"])
                session.node_id = str(session_row["node_id"])

                for insight, document, vector in prepared:
                    insight.scope = clean_scope
                    insight.user_id = (
                        identity.external_user_id or identity.user_email
                        if clean_scope == "user"
                        else None
                    )
                    insight.user_email = identity.user_email if clean_scope == "user" else None
                    insight.org_id = identity.organization_slug if clean_scope == "global" else None
                    insight.company = company if clean_scope == "global" else None
                    insight.contributed_by = contributed_by if clean_scope == "global" else None
                    insight.raw_session_id = insight.raw_session_id or session.node_id
                    insight.node_id = insight_node_id_for(
                        owner_key,
                        session.node_id,
                        insight.display_label,
                        insight.what,
                    )
                    validate_node(insight)

                    exact = conn.execute(
                        """/* orange:find-exact-insight */
                        select id, node_id
                        from orange.insights
                        where idempotency_key = %s
                        """,
                        (insight.node_id,),
                    ).fetchone()
                    if exact:
                        self._upsert_produced_edge(
                            conn,
                            session_db_id=session_db_id,
                            insight_db_id=str(exact["id"]),
                            canonical_merge=False,
                            similarity_score=None,
                        )
                        summary.insights_skipped += 1
                        summary.skipped_by_idempotency += 1
                        summary.edges_written += 1
                        continue

                    similar = self._find_similar_insight_conn(
                        conn,
                        vector=vector,
                        identity=identity,
                        scope=clean_scope,
                        threshold=similarity_threshold,
                    )
                    similarity_score = float(similar["similarity_score"]) if similar else None
                    if similar and similarity_score is not None and similarity_score >= canonical_threshold:
                        merged_how = _merge_how(similar.get("how"), insight.how)
                        merged_tags = list(
                            dict.fromkeys(
                                [
                                    *(str(tag) for tag in (similar.get("tags") or [])),
                                    *(str(tag) for tag in insight.tags),
                                ]
                            )
                        )
                        merged_outcome = (
                            _enum_value(insight.outcome)
                            if _enum_value(insight.outcome) in {"resolved", "partial"}
                            else str(similar.get("outcome") or _enum_value(insight.outcome))
                        )
                        merged_document = _embedding_text_from_row(
                            similar, how=merged_how, tags=merged_tags
                        )
                        merged_vector = self.embedding_provider.embed([merged_document])[0]
                        conn.execute(
                            """/* orange:merge-canonical-insight */
                            update orange.insights
                            set how = %s,
                                outcome = %s,
                                tags = %s,
                                canonical_merge_count = canonical_merge_count + 1,
                                embedding = %s::extensions.vector,
                                embedding_model = %s,
                                embedding_content = %s,
                                embedding_updated_at = now()
                            where id = %s::uuid
                            """,
                            (
                                merged_how,
                                merged_outcome,
                                merged_tags,
                                vector_literal(merged_vector),
                                self.embedding_model,
                                merged_document,
                                similar["id"],
                            ),
                        )
                        self._upsert_produced_edge(
                            conn,
                            session_db_id=session_db_id,
                            insight_db_id=str(similar["id"]),
                            canonical_merge=True,
                            similarity_score=similarity_score,
                        )
                        summary.insights_skipped += 1
                        summary.canonical_merges += 1
                        summary.edges_written += 1
                        continue

                    created = conn.execute(
                        """/* orange:insert-insight */
                        insert into orange.insights (
                          node_id, idempotency_key, source_session_id, scope,
                          user_id, user_email, organization_id,
                          contributed_by_user_id, contributed_by, company,
                          source, memory_kind, what, why, how, outcome, tags,
                          display_label, display_summary, raw_session_id,
                          extraction_version, embedding, embedding_model,
                          embedding_content, embedding_updated_at, metadata
                        ) values (
                          %s, %s, %s::uuid, %s,
                          %s::uuid, %s, %s::uuid,
                          %s::uuid, %s, %s,
                          %s, %s, %s, %s, %s, %s, %s,
                          %s, %s, %s,
                          %s, %s::extensions.vector, %s,
                          %s, now(), %s
                        )
                        on conflict (idempotency_key) do nothing
                        returning id, node_id
                        """,
                        (
                            insight.node_id,
                            insight.node_id,
                            session_db_id,
                            clean_scope,
                            identity.user_db_id if clean_scope == "user" else None,
                            identity.user_email if clean_scope == "user" else None,
                            identity.organization_db_id if clean_scope == "global" else None,
                            identity.user_db_id if clean_scope == "global" else None,
                            contributed_by if clean_scope == "global" else None,
                            company if clean_scope == "global" else None,
                            _enum_value(session.source),
                            insight.memory_kind,
                            insight.what,
                            insight.why,
                            insight.how,
                            _enum_value(insight.outcome),
                            list(insight.tags),
                            insight.display_label,
                            insight.display_summary,
                            insight.raw_session_id,
                            insight.extraction_version,
                            vector_literal(vector),
                            self.embedding_model,
                            document,
                            _json(insight.model_dump(mode="json").get("metadata", {})),
                        ),
                    ).fetchone()
                    if not created:
                        created = conn.execute(
                            """/* orange:get-insight-idempotent */
                            select id, node_id from orange.insights where idempotency_key = %s
                            """,
                            (insight.node_id,),
                        ).fetchone()
                        if not created:
                            raise RuntimeError("Idempotent insight could not be loaded.")
                        summary.insights_skipped += 1
                        summary.skipped_by_idempotency += 1
                    else:
                        summary.insights_stored += 1

                    self._upsert_produced_edge(
                        conn,
                        session_db_id=session_db_id,
                        insight_db_id=str(created["id"]),
                        canonical_merge=False,
                        similarity_score=None,
                    )
                    summary.edges_written += 1
                    if similar and similarity_score is not None:
                        self._upsert_similar_edge(
                            conn,
                            source_insight_db_id=str(created["id"]),
                            target_insight_db_id=str(similar["id"]),
                            similarity_score=similarity_score,
                        )
                        summary.edges_written += 1
                        summary.similar_to_edges_written += 1

        return summary

    def _find_similar_insight_conn(
        self,
        conn: Any,
        *,
        vector: list[float],
        identity: ResolvedMemoryIdentity,
        scope: str,
        threshold: float,
    ) -> dict[str, Any] | None:
        row = conn.execute(
            """/* orange:find-similar-insight */
            select id, node_id, what, why, how, outcome, tags, memory_kind,
                   1 - (embedding <=> %s::extensions.vector) as similarity_score
            from orange.insights
            where embedding is not null
              and scope = %s
              and (
                (%s = 'user' and user_id = %s::uuid)
                or (%s = 'global' and organization_id = %s::uuid)
              )
              and 1 - (embedding <=> %s::extensions.vector) >= %s
            order by embedding <=> %s::extensions.vector
            limit 1
            """,
            (
                vector_literal(vector),
                scope,
                scope,
                identity.user_db_id,
                scope,
                identity.organization_db_id,
                vector_literal(vector),
                float(threshold),
                vector_literal(vector),
            ),
        ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _upsert_produced_edge(
        conn: Any,
        *,
        session_db_id: str,
        insight_db_id: str,
        canonical_merge: bool,
        similarity_score: float | None,
    ) -> None:
        key = f"PRODUCED:session:{session_db_id}:insight:{insight_db_id}"
        conn.execute(
            """/* orange:upsert-produced-edge */
            insert into orange.memory_edges (
              idempotency_key, relationship, source_session_id,
              target_insight_id, similarity_score, properties, scope,
              user_id, organization_id
            ) values (%s, 'PRODUCED', %s::uuid, %s::uuid, %s, %s, 'user', null, null)
            on conflict (idempotency_key) do update set
              similarity_score = excluded.similarity_score,
              properties = orange.memory_edges.properties || excluded.properties
            """,
            (
                key,
                session_db_id,
                insight_db_id,
                similarity_score,
                _json({"canonical_merge": canonical_merge} if canonical_merge else {}),
            ),
        )

    @staticmethod
    def _upsert_similar_edge(
        conn: Any,
        *,
        source_insight_db_id: str,
        target_insight_db_id: str,
        similarity_score: float,
    ) -> None:
        key = f"SIMILAR_TO:insight:{source_insight_db_id}:insight:{target_insight_db_id}"
        conn.execute(
            """/* orange:upsert-similar-edge */
            insert into orange.memory_edges (
              idempotency_key, relationship, source_insight_id,
              target_insight_id, similarity_score, properties, scope,
              user_id, organization_id
            ) values (%s, 'SIMILAR_TO', %s::uuid, %s::uuid, %s, %s, 'user', null, null)
            on conflict (idempotency_key) do update set
              similarity_score = excluded.similarity_score,
              properties = orange.memory_edges.properties || excluded.properties
            """,
            (
                key,
                source_insight_db_id,
                target_insight_db_id,
                similarity_score,
                _json({"similarity_score": similarity_score}),
            ),
        )

    # ------------------------------------------------------------------
    # Semantic recall

    def search_insights(
        self,
        query: str,
        *,
        user_id: str | None = None,
        user_email: str | None = None,
        org_id: str | None = None,
        scope: str = "both",
        limit: int = 6,
        min_score: float = 0.0,
    ) -> list[dict[str, Any]]:
        clean_query = str(query or "").strip()
        if not clean_query:
            raise ValueError("query is required")
        clean_scope = _clean_scope(scope, allow_both=True)
        vector = self.embedding_provider.embed([clean_query])[0]
        with self.pool.connection() as conn:
            identity = self._resolve_identity_conn(
                conn, user_id=user_id, user_email=user_email, org_id=org_id
            )
            if not identity.user_db_id and not identity.organization_db_id:
                return []
            rows = conn.execute(
                """/* orange:search-insights */
                select
                  i.node_id, i.scope, u.external_user_id as user_id,
                  i.user_email, o.slug as org_id, i.company, i.contributed_by,
                  i.memory_kind, i.what, i.why, i.how, i.outcome, i.tags,
                  i.display_label, i.display_summary, i.raw_session_id,
                  i.source, i.created_at, i.updated_at,
                  s.node_id as session_node_id, s.title as session_title,
                  s.summary as session_summary,
                  1 - (i.embedding <=> %s::extensions.vector) as similarity_score,
                  coalesce((
                    select array_agg(distinct neighbor.display_label)
                    from orange.memory_edges edge
                    join orange.insights neighbor on neighbor.id = edge.target_insight_id
                    where edge.source_insight_id = i.id
                      and edge.relationship = 'SIMILAR_TO'
                  ), '{}') as similar_insights
                from orange.insights i
                join orange.memory_sessions s on s.id = i.source_session_id
                left join orange.users u on u.id = i.user_id
                left join orange.organizations o on o.id = i.organization_id
                where i.embedding is not null
                  and (
                    (%s in ('user', 'both') and i.scope = 'user' and i.user_id = %s::uuid)
                    or
                    (%s in ('global', 'both') and i.scope = 'global' and i.organization_id = %s::uuid)
                  )
                  and 1 - (i.embedding <=> %s::extensions.vector) >= %s
                order by similarity_score desc, i.updated_at desc
                limit %s
                """,
                (
                    vector_literal(vector),
                    clean_scope,
                    identity.user_db_id,
                    clean_scope,
                    identity.organization_db_id,
                    vector_literal(vector),
                    float(min_score),
                    _clean_limit(limit, maximum=50),
                ),
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]

    # ------------------------------------------------------------------
    # Graph reads

    def get_full_graph(
        self,
        *,
        user_id: str | None = None,
        user_email: str | None = None,
        org_id: str | None = None,
        scope: str = "both",
        limit: int = 500,
        offset: int = 0,
    ) -> dict[str, list[dict[str, Any]]]:
        clean_scope = _clean_scope(scope, allow_both=True)
        with self.pool.connection() as conn:
            identity = self._resolve_identity_conn(
                conn, user_id=user_id, user_email=user_email, org_id=org_id
            )
            if not identity.user_db_id and not identity.organization_db_id:
                return {"nodes": [], "edges": []}
            node_ids = self._visible_node_ids_conn(
                conn,
                identity=identity,
                scope=clean_scope,
                limit=_clean_limit(limit, maximum=5000),
                offset=max(int(offset or 0), 0),
            )
            return self._fetch_graph_for_node_ids_conn(conn, node_ids)

    def _visible_node_ids_conn(
        self,
        conn: Any,
        *,
        identity: ResolvedMemoryIdentity,
        scope: str,
        limit: int,
        offset: int,
    ) -> list[str]:
        rows = conn.execute(
            """/* orange:visible-graph-node-ids */
            select node_id
            from (
              select node_id, updated_at
              from orange.memory_sessions
              where (%s in ('user', 'both') and scope = 'user' and user_id = %s::uuid)
                 or (%s in ('global', 'both') and scope = 'global' and organization_id = %s::uuid)
              union all
              select node_id, updated_at
              from orange.insights
              where (%s in ('user', 'both') and scope = 'user' and user_id = %s::uuid)
                 or (%s in ('global', 'both') and scope = 'global' and organization_id = %s::uuid)
            ) visible
            order by updated_at desc, node_id
            limit %s offset %s
            """,
            (
                scope,
                identity.user_db_id,
                scope,
                identity.organization_db_id,
                scope,
                identity.user_db_id,
                scope,
                identity.organization_db_id,
                limit,
                offset,
            ),
        ).fetchall()
        return [str(row["node_id"]) for row in rows]

    def _fetch_graph_for_node_ids_conn(
        self, conn: Any, node_ids: Sequence[str]
    ) -> dict[str, list[dict[str, Any]]]:
        if not node_ids:
            return {"nodes": [], "edges": []}
        node_rows = conn.execute(
            """/* orange:fetch-graph-nodes */
            select id, label, properties
            from (
              select
                s.node_id as id,
                'Session'::text as label,
                (to_jsonb(s)
                  - 'id' - 'idempotency_key' - 'source_ingestion_id'
                  - 'user_id' - 'organization_id' - 'contributed_by_user_id')
                  || jsonb_build_object(
                    'user_id', u.external_user_id,
                    'org_id', o.slug,
                    'node_type', 'Session'
                  ) as properties
              from orange.memory_sessions s
              left join orange.users u on u.id = s.user_id
              left join orange.organizations o on o.id = s.organization_id
              where s.node_id = any(%s)
              union all
              select
                i.node_id as id,
                'Insight'::text as label,
                (to_jsonb(i)
                  - 'id' - 'idempotency_key' - 'source_session_id'
                  - 'user_id' - 'organization_id' - 'contributed_by_user_id'
                  - 'embedding' - 'embedding_content')
                  || jsonb_build_object(
                    'user_id', u.external_user_id,
                    'org_id', o.slug,
                    'node_type', 'Insight'
                  ) as properties
              from orange.insights i
              left join orange.users u on u.id = i.user_id
              left join orange.organizations o on o.id = i.organization_id
              where i.node_id = any(%s)
            ) nodes
            order by label, id
            """,
            (list(node_ids), list(node_ids)),
        ).fetchall()
        edge_rows = conn.execute(
            """/* orange:fetch-graph-edges */
            select
              coalesce(source_session.node_id, source_insight.node_id) as source,
              coalesce(target_session.node_id, target_insight.node_id) as target,
              edge.relationship as type,
              edge.properties || case
                when edge.similarity_score is null then '{}'::jsonb
                else jsonb_build_object('similarity_score', edge.similarity_score)
              end as properties
            from orange.memory_edges edge
            left join orange.memory_sessions source_session on source_session.id = edge.source_session_id
            left join orange.insights source_insight on source_insight.id = edge.source_insight_id
            left join orange.memory_sessions target_session on target_session.id = edge.target_session_id
            left join orange.insights target_insight on target_insight.id = edge.target_insight_id
            where coalesce(source_session.node_id, source_insight.node_id) = any(%s)
              and coalesce(target_session.node_id, target_insight.node_id) = any(%s)
            order by edge.created_at, edge.id
            """,
            (list(node_ids), list(node_ids)),
        ).fetchall()
        nodes = [
            {
                "id": str(row["id"]),
                "label": str(row["label"]),
                "properties": _json_safe(row.get("properties") or {}),
            }
            for row in node_rows
        ]
        edges = [
            {
                "source": str(row["source"]),
                "target": str(row["target"]),
                "type": str(row["type"]),
                "properties": _json_safe(row.get("properties") or {}),
            }
            for row in edge_rows
            if row.get("source") and row.get("target")
        ]
        return {"nodes": nodes, "edges": edges}

    def get_node_with_neighborhood(
        self,
        node_id: str,
        *,
        user_id: str | None = None,
        user_email: str | None = None,
        org_id: str | None = None,
        scope: str = "both",
        limit: int = 100,
    ) -> dict[str, list[dict[str, Any]]]:
        clean_scope = _clean_scope(scope, allow_both=True)
        with self.pool.connection() as conn:
            identity = self._resolve_identity_conn(
                conn, user_id=user_id, user_email=user_email, org_id=org_id
            )
            visible = self._visible_node_ids_conn(
                conn,
                identity=identity,
                scope=clean_scope,
                limit=5000,
                offset=0,
            )
            if node_id not in set(visible):
                return {"nodes": [], "edges": []}
            rows = conn.execute(
                """/* orange:neighbor-node-ids */
                select distinct neighbor_id
                from (
                  select coalesce(ts.node_id, ti.node_id) as neighbor_id
                  from orange.memory_edges e
                  left join orange.memory_sessions ss on ss.id = e.source_session_id
                  left join orange.insights si on si.id = e.source_insight_id
                  left join orange.memory_sessions ts on ts.id = e.target_session_id
                  left join orange.insights ti on ti.id = e.target_insight_id
                  where coalesce(ss.node_id, si.node_id) = %s
                  union
                  select coalesce(ss.node_id, si.node_id) as neighbor_id
                  from orange.memory_edges e
                  left join orange.memory_sessions ss on ss.id = e.source_session_id
                  left join orange.insights si on si.id = e.source_insight_id
                  left join orange.memory_sessions ts on ts.id = e.target_session_id
                  left join orange.insights ti on ti.id = e.target_insight_id
                  where coalesce(ts.node_id, ti.node_id) = %s
                ) neighbors
                where neighbor_id is not null
                limit %s
                """,
                (node_id, node_id, _clean_limit(limit, maximum=500)),
            ).fetchall()
            visible_set = set(visible)
            node_ids = [node_id, *[str(row["neighbor_id"]) for row in rows if str(row["neighbor_id"]) in visible_set]]
            return self._fetch_graph_for_node_ids_conn(conn, list(dict.fromkeys(node_ids)))

    def get_session_subgraph(
        self,
        session_id: str,
        *,
        user_id: str | None = None,
        user_email: str | None = None,
        org_id: str | None = None,
        scope: str = "both",
    ) -> dict[str, list[dict[str, Any]]]:
        clean_scope = _clean_scope(scope, allow_both=True)
        with self.pool.connection() as conn:
            identity = self._resolve_identity_conn(
                conn, user_id=user_id, user_email=user_email, org_id=org_id
            )
            visible = set(
                self._visible_node_ids_conn(
                    conn,
                    identity=identity,
                    scope=clean_scope,
                    limit=5000,
                    offset=0,
                )
            )
            if session_id not in visible:
                return {"nodes": [], "edges": []}
            rows = conn.execute(
                """/* orange:session-insight-node-ids */
                select insight.node_id
                from orange.memory_edges edge
                join orange.memory_sessions session on session.id = edge.source_session_id
                join orange.insights insight on insight.id = edge.target_insight_id
                where session.node_id = %s and edge.relationship = 'PRODUCED'
                order by insight.created_at
                """,
                (session_id,),
            ).fetchall()
            node_ids = [session_id, *[str(row["node_id"]) for row in rows if str(row["node_id"]) in visible]]
            return self._fetch_graph_for_node_ids_conn(conn, node_ids)

    def list_sessions(
        self,
        *,
        user_id: str | None = None,
        user_email: str | None = None,
        org_id: str | None = None,
        scope: str = "both",
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        clean_scope = _clean_scope(scope, allow_both=True)
        with self.pool.connection() as conn:
            identity = self._resolve_identity_conn(
                conn, user_id=user_id, user_email=user_email, org_id=org_id
            )
            rows = conn.execute(
                """/* orange:list-memory-sessions */
                select s.node_id, s.title, s.summary, s.source, s.scope,
                       s.started_at, s.ended_at, s.message_count,
                       u.external_user_id as user_id, s.user_email,
                       o.slug as org_id, s.updated_at
                from orange.memory_sessions s
                left join orange.users u on u.id = s.user_id
                left join orange.organizations o on o.id = s.organization_id
                where (%s in ('user', 'both') and s.scope = 'user' and s.user_id = %s::uuid)
                   or (%s in ('global', 'both') and s.scope = 'global' and s.organization_id = %s::uuid)
                order by s.started_at desc nulls last, s.created_at desc
                limit %s offset %s
                """,
                (
                    clean_scope,
                    identity.user_db_id,
                    clean_scope,
                    identity.organization_db_id,
                    _clean_limit(limit, maximum=500),
                    max(int(offset or 0), 0),
                ),
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]

    def get_graph_version(
        self,
        *,
        user_id: str | None = None,
        user_email: str | None = None,
        org_id: str | None = None,
        scope: str = "both",
    ) -> dict[str, Any]:
        clean_scope = _clean_scope(scope, allow_both=True)
        with self.pool.connection() as conn:
            identity = self._resolve_identity_conn(
                conn, user_id=user_id, user_email=user_email, org_id=org_id
            )
            if not identity.user_db_id and not identity.organization_db_id:
                return {"version": "empty", "change_sequence": 0, "node_count": 0, "last_changed_at": None}
            version = conn.execute(
                """/* orange:get-graph-version */
                select version, change_sequence, last_changed_at
                from orange.get_graph_version(%s, %s::uuid, %s::uuid)
                """,
                (clean_scope, identity.user_db_id, identity.organization_db_id),
            ).fetchone()
            count = conn.execute(
                """/* orange:get-graph-node-count */
                select (
                  select count(*) from orange.memory_sessions s
                  where (%s in ('user', 'both') and s.scope = 'user' and s.user_id = %s::uuid)
                     or (%s in ('global', 'both') and s.scope = 'global' and s.organization_id = %s::uuid)
                ) + (
                  select count(*) from orange.insights i
                  where (%s in ('user', 'both') and i.scope = 'user' and i.user_id = %s::uuid)
                     or (%s in ('global', 'both') and i.scope = 'global' and i.organization_id = %s::uuid)
                ) as node_count
                """,
                (
                    clean_scope,
                    identity.user_db_id,
                    clean_scope,
                    identity.organization_db_id,
                    clean_scope,
                    identity.user_db_id,
                    clean_scope,
                    identity.organization_db_id,
                ),
            ).fetchone()
        payload = _row_dict(version) or {"version": "u:0:g:0", "change_sequence": 0, "last_changed_at": None}
        payload["node_count"] = int((count or {}).get("node_count") or 0)
        return payload

    # ------------------------------------------------------------------
    # Checkpoints are ordinary durable insight nodes.

    def checkpoint_context(
        self,
        note: str,
        *,
        user_id: str,
        user_email: str | None = None,
        auth_user_id: str | None = None,
        org_id: str | None = None,
        company: str | None = None,
        source: str = "mcp",
        scope: str = "user",
    ) -> dict[str, Any]:
        clean_note = str(note or "").strip()
        if not clean_note:
            raise ValueError("note is required")
        timestamp = datetime.now(timezone.utc)
        checkpoint_id = uuid4().hex
        try:
            source_type = SourceType(str(source or "mcp").strip().lower())
        except ValueError:
            source_type = SourceType.MCP
        session = Session(
            node_id=f"checkpoint_session_{checkpoint_id}",
            source=source_type,
            title="Mid-session checkpoint",
            summary=clean_note[:500],
            message_count=1,
            org_id=org_id,
            started_at=timestamp,
            ended_at=timestamp,
            ingested_at=timestamp,
        )
        insight = Insight(
            node_id=f"checkpoint_{checkpoint_id}",
            source=source_type,
            scope="global" if scope == "global" else "user",
            user_id=user_id if scope != "global" else None,
            user_email=user_email if scope != "global" else None,
            org_id=org_id if scope == "global" else None,
            company=company,
            memory_kind="checkpoint",
            what=clean_note,
            display_label="Checkpoint",
            display_summary=clean_note[:280],
            raw_session_id=session.node_id,
        )
        summary = self.upsert_insights(
            session=session,
            user_id=user_id,
            user_email=user_email,
            auth_user_id=auth_user_id,
            org_id=org_id,
            company=company,
            scope=scope,
            insights=[insight],
        )
        return {
            "checkpointed": True,
            "timestamp": timestamp.isoformat(),
            "node_id": insight.node_id,
            "summary": asdict(summary),
        }

    # ------------------------------------------------------------------
    # Durable extraction queue

    def finish_memory_write_job_inline(
        self,
        job_id: str,
        *,
        succeeded: bool,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Finish a job processed inline by a local stdio MCP process.

        The hosted worker uses leased claim/finish functions. Local stdio has
        no worker loop, so it uses this bounded single-job transition instead.
        """

        with self.pool.connection() as conn:
            row = conn.execute(
                """/* orange:finish-memory-job-inline */
                update orange.memory_write_jobs
                set status = case when %s then 'succeeded' else 'failed' end,
                    attempt_count = greatest(attempt_count, 1),
                    result = %s,
                    error = case when %s then null else coalesce(%s, 'Memory write failed') end,
                    processed_at = now(),
                    completed_at = case when %s then now() else null end,
                    locked_by = null,
                    locked_at = null,
                    lease_expires_at = null
                where id = %s::uuid
                  and status in ('queued', 'retrying', 'failed')
                returning *
                """,
                (
                    bool(succeeded),
                    _json(result),
                    bool(succeeded),
                    error,
                    bool(succeeded),
                    job_id,
                ),
            ).fetchone()
        if not row:
            existing = self.get_memory_write_job(job_id=job_id)
            if existing and existing.get("status") == "succeeded":
                return existing
            raise RuntimeError("Inline memory job could not be completed.")
        return _row_dict(row) or {}

    def claim_memory_write_jobs(
        self, worker_id: str, *, limit: int = 1, lease_seconds: int = 300
    ) -> list[dict[str, Any]]:
        clean_worker = str(worker_id or "").strip()
        if not clean_worker:
            raise ValueError("worker_id is required")
        with self.pool.connection() as conn:
            rows = conn.execute(
                """/* orange:claim-memory-jobs */
                select * from orange.claim_memory_write_jobs(%s, %s, %s)
                """,
                (
                    clean_worker,
                    _clean_limit(limit, maximum=50),
                    min(max(int(lease_seconds or 300), 30), 3600),
                ),
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]

    def finish_memory_write_job(
        self,
        job_id: str,
        worker_id: str,
        *,
        succeeded: bool,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        retry_delay_seconds: int = 30,
    ) -> dict[str, Any]:
        with self.pool.connection() as conn:
            row = conn.execute(
                """/* orange:finish-memory-job */
                select * from orange.finish_memory_write_job(
                  %s::uuid, %s::text, %s::boolean, %s::jsonb, %s::text, %s::integer
                )
                """,
                (
                    job_id,
                    str(worker_id or "").strip(),
                    bool(succeeded),
                    _json(result),
                    error,
                    min(max(int(retry_delay_seconds or 0), 0), 86400),
                ),
            ).fetchone()
        if not row:
            raise RuntimeError("Memory job was not returned after finishing.")
        return _row_dict(row) or {}

    def get_memory_write_job(
        self,
        *,
        job_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any] | None:
        if not job_id and not idempotency_key:
            raise ValueError("job_id or idempotency_key is required")
        with self.pool.connection() as conn:
            row = conn.execute(
                """/* orange:get-memory-job */
                select job.*, ingestion.source, ingestion.session_id,
                       ingestion.user_email, ingestion.scope
                from orange.memory_write_jobs job
                join orange.session_ingestions ingestion on ingestion.id = job.ingestion_id
                where (%s::text is not null and job.id::text = %s::text)
                   or (%s::text is not null and job.idempotency_key = %s::text)
                order by job.created_at desc
                limit 1
                """,
                (job_id, job_id, idempotency_key, idempotency_key),
            ).fetchone()
        return _row_dict(row)

    def get_existing_job_result(
        self,
        *,
        idempotency_key: str | None = None,
        ingestion_id: str | None = None,
        source: str | None = None,
        session_id: str | None = None,
        org_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Look up a durable result by job key, ingestion, or session fingerprint."""

        if not any([idempotency_key, ingestion_id, source and session_id]):
            raise ValueError("Provide idempotency_key, ingestion_id, or source + session_id")
        clean_org = _slugify(org_id) if org_id else None
        with self.pool.connection() as conn:
            row = conn.execute(
                """/* orange:get-existing-job-result */
                select job.*, ingestion.source, ingestion.session_id,
                       organization.slug as organization_slug
                from orange.memory_write_jobs job
                join orange.session_ingestions ingestion on ingestion.id = job.ingestion_id
                left join orange.organizations organization on organization.id = ingestion.organization_id
                where (%s::text is not null and job.idempotency_key = %s::text)
                   or (%s::text is not null and ingestion.id::text = %s::text)
                   or (
                     %s::text is not null and %s::text is not null
                     and ingestion.source = %s::text and ingestion.session_id = %s::text
                     and (%s::text is null or organization.slug = %s::text)
                   )
                order by (job.status = 'succeeded') desc, job.created_at desc
                limit 1
                """,
                (
                    idempotency_key,
                    idempotency_key,
                    ingestion_id,
                    ingestion_id,
                    source,
                    session_id,
                    source,
                    session_id,
                    clean_org,
                    clean_org,
                ),
            ).fetchone()
        return _row_dict(row)

    def load_normalized_session(self, ingestion_id: str) -> NormalizedSession:
        """Rehydrate the normalized input needed by a durable extraction worker."""

        with self.pool.connection() as conn:
            row = conn.execute(
                """/* orange:load-normalized-session */
                select normalized_payload, metadata, external_session_id,
                       client_name, client_version, source_url
                from orange.session_ingestions
                where id = %s::uuid
                """,
                (ingestion_id,),
            ).fetchone()
        if not row:
            raise KeyError(f"Session ingestion not found: {ingestion_id}")
        payload = dict(row.get("normalized_payload") or {})
        stored_metadata = dict(row.get("metadata") or {})
        known = {
            "source",
            "session_id",
            "user_id",
            "user_email",
            "org_id",
            "started_at",
            "ended_at",
            "participants",
            "client_metadata",
            "tool_metadata",
            "raw_transcript",
            "raw_messages",
            "normalized_turns",
            "message_count",
        }
        extra_metadata = {key: value for key, value in payload.items() if key not in known}
        request = {
            **{key: value for key, value in payload.items() if key in known},
            "external_session_id": row.get("external_session_id"),
            "client_name": row.get("client_name"),
            "client_version": row.get("client_version"),
            "source_url": row.get("source_url"),
            "messages": payload.get("normalized_turns") or payload.get("raw_messages") or [],
            "metadata": {**extra_metadata, **stored_metadata},
        }
        return normalize_ingestion_request(request)

    def get_ingestion_for_job(self, job_id: str) -> tuple[dict[str, Any], NormalizedSession]:
        job = self.get_memory_write_job(job_id=job_id)
        if not job:
            raise KeyError(f"Memory job not found: {job_id}")
        ingestion_id = str(job.get("ingestion_id") or "")
        if not ingestion_id:
            raise RuntimeError(f"Memory job {job_id} has no ingestion_id")
        return job, self.load_normalized_session(ingestion_id)


__all__ = [
    "PostgresMemoryRepository",
    "ResolvedMemoryIdentity",
    "UpsertSummary",
    "insight_node_id_for",
    "scoped_session_node_id_for",
]
