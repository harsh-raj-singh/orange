from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json
from psycopg_pool import ConnectionPool

from core.ingestion import NormalizedSession


_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class StoredSessionIngestion:
    organization_id: str
    user_id: str | None
    ingestion_id: str
    memory_job_id: str


def _slugify(value: str | None, fallback: str = "default") -> str:
    slug = _SLUG_RE.sub("-", (value or fallback).strip().lower()).strip("-")
    return slug or fallback


def _json(value: Any) -> Json:
    return Json(value if value is not None else {})


def _dt(value: datetime | None) -> datetime | None:
    return value


class OrangePostgresStore:
    """Backend-owned Postgres store for Orange identity and ingestion metadata.

    The schema is designed for Supabase Postgres, but this class uses direct
    Postgres connections rather than browser-facing Supabase Data API calls.
    """

    def __init__(
        self,
        dsn: str,
        *,
        min_pool_size: int = 1,
        max_pool_size: int = 5,
        open_pool: bool = True,
    ) -> None:
        if not dsn:
            raise ValueError("Postgres DSN is required")
        self.pool = ConnectionPool(
            dsn,
            min_size=min_pool_size,
            max_size=max_pool_size,
            open=open_pool,
            kwargs={"row_factory": dict_row},
        )

    def close(self) -> None:
        self.pool.close()

    def upsert_organization(
        self,
        *,
        external_org_id: str | None,
        slug: str | None = None,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        org_slug = _slugify(slug or external_org_id)
        org_name = name or external_org_id or org_slug
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                insert into orange.organizations (external_org_id, slug, name, metadata)
                values (%s, %s, %s, %s)
                on conflict (slug)
                do update set
                  external_org_id = coalesce(excluded.external_org_id, orange.organizations.external_org_id),
                  name = excluded.name,
                  metadata = orange.organizations.metadata || excluded.metadata
                returning id
                """,
                (external_org_id, org_slug, org_name, _json(metadata)),
            ).fetchone()
        return str(row["id"])

    def upsert_user(
        self,
        *,
        external_user_id: str,
        auth_user_id: str | None = None,
        email: str | None = None,
        display_name: str | None = None,
        role: str | None = None,
        company: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if not external_user_id and not auth_user_id and not email:
            raise ValueError("A user identity is required")
        stable_external_id = external_user_id or email or str(auth_user_id)
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                insert into orange.users (
                  auth_user_id, external_user_id, email, display_name, role, company, metadata
                )
                values (%s, %s, %s, %s, %s, %s, %s)
                on conflict (external_user_id)
                do update set
                  auth_user_id = coalesce(excluded.auth_user_id, orange.users.auth_user_id),
                  email = coalesce(excluded.email, orange.users.email),
                  display_name = coalesce(excluded.display_name, orange.users.display_name),
                  role = coalesce(excluded.role, orange.users.role),
                  company = coalesce(excluded.company, orange.users.company),
                  metadata = orange.users.metadata || excluded.metadata
                returning id
                """,
                (
                    auth_user_id,
                    stable_external_id,
                    email,
                    display_name,
                    role,
                    company,
                    _json(metadata),
                ),
            ).fetchone()
        return str(row["id"])

    def upsert_membership(
        self,
        *,
        organization_id: str,
        user_id: str,
        membership_role: str = "member",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                """
                insert into orange.organization_members (
                  organization_id, user_id, membership_role, metadata
                )
                values (%s, %s, %s, %s)
                on conflict (organization_id, user_id)
                do update set
                  membership_role = excluded.membership_role,
                  metadata = orange.organization_members.metadata || excluded.metadata
                """,
                (organization_id, user_id, membership_role, _json(metadata)),
            )

    def record_normalized_session(
        self,
        normalized: NormalizedSession,
        *,
        status: str = "received",
        organization_name: str | None = None,
        user_metadata: dict[str, Any] | None = None,
    ) -> StoredSessionIngestion:
        org_external_id = normalized.org_id or "default"
        organization_id = self.upsert_organization(
            external_org_id=org_external_id,
            slug=org_external_id,
            name=organization_name or org_external_id,
            metadata={"source": normalized.source.value},
        )

        user_id: str | None = None
        if normalized.user_id:
            user_id = self.upsert_user(
                external_user_id=normalized.user_id,
                display_name=normalized.user_id,
                metadata=user_metadata or {},
            )
            self.upsert_membership(organization_id=organization_id, user_id=user_id)

        payload = normalized.ingestion_metadata()
        with self.pool.connection() as conn:
            with conn.transaction():
                ingestion = conn.execute(
                    """
                    insert into orange.session_ingestions (
                      organization_id, user_id, source, session_id, external_session_id,
                      graph_session_node_id, client_name, client_version, source_url,
                      title, summary, started_at, ended_at, ingested_at, message_count,
                      status, metadata, normalized_payload
                    )
                    values (
                      %s, %s, %s, %s, %s,
                      %s, %s, %s, %s,
                      %s, %s, %s, %s, %s, %s,
                      %s, %s, %s
                    )
                    on conflict (organization_id, source, session_id)
                    do update set
                      user_id = excluded.user_id,
                      external_session_id = excluded.external_session_id,
                      graph_session_node_id = excluded.graph_session_node_id,
                      client_name = excluded.client_name,
                      client_version = excluded.client_version,
                      source_url = excluded.source_url,
                      title = excluded.title,
                      summary = excluded.summary,
                      started_at = excluded.started_at,
                      ended_at = excluded.ended_at,
                      ingested_at = excluded.ingested_at,
                      message_count = excluded.message_count,
                      status = excluded.status,
                      metadata = excluded.metadata,
                      normalized_payload = excluded.normalized_payload
                    returning id
                    """,
                    (
                        organization_id,
                        user_id,
                        normalized.source.value,
                        normalized.session_id,
                        normalized.external_session_id,
                        normalized.session_node_id,
                        normalized.client_name,
                        normalized.client_version,
                        normalized.source_url,
                        normalized.title,
                        normalized.transcript[:500],
                        _dt(normalized.started_at),
                        _dt(normalized.ended_at),
                        _dt(normalized.ingested_at),
                        normalized.message_count,
                        status,
                        _json(normalized.metadata),
                        _json(payload),
                    ),
                ).fetchone()
                ingestion_id = str(ingestion["id"])

                for turn in normalized.turns:
                    conn.execute(
                        """
                        insert into orange.session_messages (
                          ingestion_id, turn_index, role, content, occurred_at,
                          message_id, participant_id, participant_name, metadata, raw_payload
                        )
                        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        on conflict (ingestion_id, turn_index)
                        do update set
                          role = excluded.role,
                          content = excluded.content,
                          occurred_at = excluded.occurred_at,
                          message_id = excluded.message_id,
                          participant_id = excluded.participant_id,
                          participant_name = excluded.participant_name,
                          metadata = excluded.metadata,
                          raw_payload = excluded.raw_payload
                        """,
                        (
                            ingestion_id,
                            turn.turn_index,
                            turn.role,
                            turn.content,
                            _dt(turn.timestamp),
                            turn.message_id,
                            turn.participant_id,
                            turn.participant_name,
                            _json(turn.metadata),
                            _json(turn.raw),
                        ),
                    )

                job = conn.execute(
                    """
                    insert into orange.memory_write_jobs (ingestion_id, status)
                    values (%s, 'queued')
                    on conflict (ingestion_id)
                    do update set status = orange.memory_write_jobs.status
                    returning id
                    """,
                    (ingestion_id,),
                ).fetchone()

        return StoredSessionIngestion(
            organization_id=organization_id,
            user_id=user_id,
            ingestion_id=ingestion_id,
            memory_job_id=str(job["id"]),
        )

    def mark_session_status(self, *, ingestion_id: str, status: str) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                """
                update orange.session_ingestions
                set status = %s
                where id = %s
                """,
                (status, ingestion_id),
            )
