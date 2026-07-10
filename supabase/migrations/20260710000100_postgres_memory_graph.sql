-- Orange's durable memory graph now lives entirely in Postgres.
--
-- Graph-visible sessions are deliberately separate from session_ingestions:
-- one raw ingestion may produce both a private session and a separately
-- PII-scrubbed company session.  This prevents organization members from ever
-- reading the private ingestion payload through graph APIs.

create extension if not exists vector with schema extensions;

create table if not exists orange.memory_sessions (
  id uuid primary key default extensions.gen_random_uuid(),
  node_id text not null unique,
  idempotency_key text not null unique,
  source_ingestion_id uuid references orange.session_ingestions(id) on delete set null,
  scope text not null,
  user_id uuid references orange.users(id) on delete cascade,
  user_email text,
  organization_id uuid references orange.organizations(id) on delete cascade,
  contributed_by_user_id uuid references orange.users(id) on delete set null,
  contributed_by text,
  source text not null,
  conversation_type text not null default 'general',
  resolution_status text not null default 'open',
  title text not null default '',
  summary text not null default '',
  message_count integer not null default 0,
  external_session_id text,
  participants text[] not null default '{}',
  client_name text,
  client_version text,
  source_url text,
  started_at timestamptz,
  ended_at timestamptz,
  ingested_at timestamptz not null default now(),
  extraction_version text not null default 'v2',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint orange_memory_sessions_node_id_not_blank
    check (nullif(btrim(node_id), '') is not null),
  constraint orange_memory_sessions_idempotency_key_not_blank
    check (nullif(btrim(idempotency_key), '') is not null),
  constraint orange_memory_sessions_scope
    check (scope in ('user', 'global')),
  constraint orange_memory_sessions_owner
    check (
      (scope = 'user' and user_id is not null)
      or
      (scope = 'global' and organization_id is not null and user_id is null and user_email is null)
    ),
  constraint orange_memory_sessions_message_count_nonnegative
    check (message_count >= 0),
  constraint orange_memory_sessions_time_order
    check (ended_at is null or started_at is null or ended_at >= started_at)
);

comment on table orange.memory_sessions is
  'Scoped, graph-visible Session nodes. Global rows must contain only PII-scrubbed display content.';
comment on column orange.memory_sessions.node_id is
  'Globally unique graph ID. Include the scope owner when deriving it so private and global rows never collide.';
comment on column orange.memory_sessions.idempotency_key is
  'Stable caller key used to make retried graph-session writes safe; defaults to node_id in a BEFORE trigger.';
comment on column orange.memory_sessions.summary is
  'Graph-visible summary. The application must PII-scrub this value before writing a global row.';
comment on column orange.memory_sessions.metadata is
  'Graph-safe metadata only. Never copy normalized_payload or raw ingestion data into a global row.';

create table if not exists orange.insights (
  id uuid primary key default extensions.gen_random_uuid(),
  node_id text not null unique,
  idempotency_key text not null unique,
  source_session_id uuid not null references orange.memory_sessions(id) on delete cascade,
  scope text not null,
  user_id uuid references orange.users(id) on delete cascade,
  user_email text,
  organization_id uuid references orange.organizations(id) on delete cascade,
  contributed_by_user_id uuid references orange.users(id) on delete set null,
  contributed_by text,
  company text,
  source text not null,
  memory_kind text not null default 'technical_insight',
  what text not null,
  why text,
  how text,
  outcome text not null default 'exploratory',
  tags text[] not null default '{}',
  display_label text not null,
  display_summary text not null default '',
  raw_session_id text not null default '',
  extraction_version text not null default 'v2',
  canonical_merge_count integer not null default 0,
  embedding extensions.vector(1536),
  embedding_model text not null default 'text-embedding-3-small',
  embedding_content text,
  embedding_updated_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint orange_insights_node_id_not_blank
    check (nullif(btrim(node_id), '') is not null),
  constraint orange_insights_idempotency_key_not_blank
    check (nullif(btrim(idempotency_key), '') is not null),
  constraint orange_insights_scope
    check (scope in ('user', 'global')),
  constraint orange_insights_owner
    check (
      (scope = 'user' and user_id is not null)
      or
      (scope = 'global' and organization_id is not null and user_id is null and user_email is null)
    ),
  constraint orange_insights_outcome
    check (outcome in ('resolved', 'exploratory', 'partial', 'abandoned')),
  constraint orange_insights_what_not_blank
    check (nullif(btrim(what), '') is not null),
  constraint orange_insights_display_label_not_blank
    check (nullif(btrim(display_label), '') is not null),
  constraint orange_insights_canonical_merge_count_nonnegative
    check (canonical_merge_count >= 0),
  constraint orange_insights_embedding_metadata
    check (
      (embedding is null and embedding_updated_at is null)
      or
      (embedding is not null and embedding_updated_at is not null and nullif(btrim(embedding_model), '') is not null)
    )
);

comment on table orange.insights is
  'Durable private or organization-scoped Insight nodes and their pgvector embeddings.';
comment on column orange.insights.embedding is
  '1536-dimensional text-embedding-3-small vector, queried with cosine distance.';
comment on column orange.insights.embedding_content is
  'Exact normalized text used to produce embedding, retained for reproducible re-embedding.';

create table if not exists orange.memory_edges (
  id uuid primary key default extensions.gen_random_uuid(),
  idempotency_key text not null unique,
  relationship text not null,
  source_session_id uuid references orange.memory_sessions(id) on delete cascade,
  source_insight_id uuid references orange.insights(id) on delete cascade,
  target_session_id uuid references orange.memory_sessions(id) on delete cascade,
  target_insight_id uuid references orange.insights(id) on delete cascade,
  scope text not null,
  user_id uuid references orange.users(id) on delete cascade,
  organization_id uuid references orange.organizations(id) on delete cascade,
  similarity_score real,
  properties jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint orange_memory_edges_idempotency_key_not_blank
    check (nullif(btrim(idempotency_key), '') is not null),
  constraint orange_memory_edges_relationship
    check (relationship in ('PRODUCED', 'SIMILAR_TO')),
  constraint orange_memory_edges_one_source
    check (num_nonnulls(source_session_id, source_insight_id) = 1),
  constraint orange_memory_edges_one_target
    check (num_nonnulls(target_session_id, target_insight_id) = 1),
  constraint orange_memory_edges_supported_shape
    check (
      (
        relationship = 'PRODUCED'
        and source_session_id is not null
        and source_insight_id is null
        and target_session_id is null
        and target_insight_id is not null
      )
      or
      (
        relationship = 'SIMILAR_TO'
        and source_session_id is null
        and source_insight_id is not null
        and target_session_id is null
        and target_insight_id is not null
      )
    ),
  constraint orange_memory_edges_scope
    check (scope in ('user', 'global')),
  constraint orange_memory_edges_owner
    check (
      (scope = 'user' and user_id is not null)
      or
      (scope = 'global' and organization_id is not null and user_id is null)
    ),
  constraint orange_memory_edges_similarity_score
    check (similarity_score is null or similarity_score between -1.0 and 1.0),
  constraint orange_memory_edges_no_self_insight
    check (
      relationship <> 'SIMILAR_TO'
      or source_insight_id is distinct from target_insight_id
    ),
  constraint orange_memory_edges_endpoints_key
    unique nulls not distinct (
      relationship,
      source_session_id,
      source_insight_id,
      target_session_id,
      target_insight_id
    )
);

comment on table orange.memory_edges is
  'Typed graph relationships. Current shapes are Session-PRODUCED->Insight and Insight-SIMILAR_TO->Insight.';

-- A cheap per-owner token lets web clients poll for graph mutations without
-- repeatedly loading the graph. It is also published through Supabase Realtime.
create table if not exists orange.graph_scope_versions (
  scope text not null,
  owner_id uuid not null,
  version bigint not null default 1,
  last_changed_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (scope, owner_id),
  constraint orange_graph_scope_versions_scope
    check (scope in ('user', 'global')),
  constraint orange_graph_scope_versions_version_positive
    check (version > 0)
);

comment on table orange.graph_scope_versions is
  'Monotonic graph change sequence keyed by private user ID or global organization ID.';

-- Durable job fields. Existing ingestion_id uniqueness remains the natural
-- one-extraction-job-per-ingestion guard; idempotency_key also protects callers
-- that retry before they learn the ingestion UUID.
alter table orange.memory_write_jobs
  add column if not exists job_type text not null default 'extract_and_store',
  add column if not exists idempotency_key text,
  add column if not exists request_hash text,
  add column if not exists priority smallint not null default 0,
  add column if not exists available_at timestamptz not null default now(),
  add column if not exists max_attempts integer not null default 5,
  add column if not exists locked_by text,
  add column if not exists lease_expires_at timestamptz,
  add column if not exists last_attempt_at timestamptz,
  add column if not exists completed_at timestamptz,
  add column if not exists dead_lettered_at timestamptz,
  add column if not exists cancelled_at timestamptz,
  add column if not exists result jsonb not null default '{}'::jsonb;

update orange.memory_write_jobs
set idempotency_key = 'memory-write:' || ingestion_id::text
where idempotency_key is null or nullif(btrim(idempotency_key), '') is null;

alter table orange.memory_write_jobs
  alter column idempotency_key set not null;

alter table orange.memory_write_jobs
  drop constraint if exists orange_memory_write_jobs_status,
  drop constraint if exists orange_memory_write_jobs_attempts,
  drop constraint if exists orange_memory_write_jobs_lease,
  drop constraint if exists orange_memory_write_jobs_idempotency_key_not_blank;

alter table orange.memory_write_jobs
  add constraint orange_memory_write_jobs_status
    check (status in ('queued', 'running', 'retrying', 'succeeded', 'failed', 'dead_letter', 'cancelled')),
  add constraint orange_memory_write_jobs_attempts
    check (attempt_count >= 0 and max_attempts > 0 and attempt_count <= max_attempts),
  add constraint orange_memory_write_jobs_lease
    check (
      (status = 'running' and locked_by is not null and locked_at is not null and lease_expires_at is not null)
      or status <> 'running'
    ),
  add constraint orange_memory_write_jobs_idempotency_key_not_blank
    check (nullif(btrim(idempotency_key), '') is not null);

create unique index if not exists idx_orange_memory_jobs_idempotency
  on orange.memory_write_jobs(idempotency_key);

drop index if exists orange.idx_orange_memory_jobs_status;
create index if not exists idx_orange_memory_jobs_dequeue
  on orange.memory_write_jobs(priority desc, available_at, created_at)
  where status in ('queued', 'retrying', 'running');

create index if not exists idx_orange_memory_jobs_lease
  on orange.memory_write_jobs(lease_expires_at)
  where status = 'running';

create index if not exists idx_orange_memory_sessions_user_updated
  on orange.memory_sessions(user_id, updated_at desc)
  where scope = 'user';

create index if not exists idx_orange_memory_sessions_org_updated
  on orange.memory_sessions(organization_id, updated_at desc)
  where scope = 'global';

create index if not exists idx_orange_memory_sessions_ingestion
  on orange.memory_sessions(source_ingestion_id, scope);

create index if not exists idx_orange_insights_user_updated
  on orange.insights(user_id, updated_at desc)
  where scope = 'user';

create index if not exists idx_orange_insights_org_updated
  on orange.insights(organization_id, updated_at desc)
  where scope = 'global';

create index if not exists idx_orange_insights_session_created
  on orange.insights(source_session_id, created_at);

create index if not exists idx_orange_insights_user_kind_updated
  on orange.insights(user_id, memory_kind, updated_at desc)
  where scope = 'user';

create index if not exists idx_orange_insights_org_kind_updated
  on orange.insights(organization_id, memory_kind, updated_at desc)
  where scope = 'global';

create index if not exists idx_orange_insights_tags
  on orange.insights using gin(tags);

-- Separate scope indexes keep filtered ANN recall useful when private and
-- organization memories share the table. text-embedding-3-small is 1536-d.
create index if not exists idx_orange_insights_user_embedding_hnsw
  on orange.insights using hnsw (embedding extensions.vector_cosine_ops)
  where scope = 'user' and embedding is not null;

create index if not exists idx_orange_insights_global_embedding_hnsw
  on orange.insights using hnsw (embedding extensions.vector_cosine_ops)
  where scope = 'global' and embedding is not null;

create index if not exists idx_orange_memory_edges_source_session
  on orange.memory_edges(source_session_id, relationship)
  where source_session_id is not null;

create index if not exists idx_orange_memory_edges_source_insight
  on orange.memory_edges(source_insight_id, relationship)
  where source_insight_id is not null;

create index if not exists idx_orange_memory_edges_target_session
  on orange.memory_edges(target_session_id, relationship)
  where target_session_id is not null;

create index if not exists idx_orange_memory_edges_target_insight
  on orange.memory_edges(target_insight_id, relationship)
  where target_insight_id is not null;

create index if not exists idx_orange_memory_edges_user_updated
  on orange.memory_edges(user_id, updated_at desc)
  where scope = 'user';

create index if not exists idx_orange_memory_edges_org_updated
  on orange.memory_edges(organization_id, updated_at desc)
  where scope = 'global';

create or replace function orange.prepare_memory_session()
returns trigger
language plpgsql
set search_path = pg_catalog, orange
as $$
begin
  new.node_id := btrim(new.node_id);
  new.idempotency_key := coalesce(nullif(btrim(new.idempotency_key), ''), new.node_id);
  new.scope := lower(btrim(new.scope));
  new.user_email := nullif(lower(btrim(new.user_email)), '');
  new.contributed_by := nullif(lower(btrim(new.contributed_by)), '');
  return new;
end;
$$;

create or replace function orange.prepare_memory_write_job()
returns trigger
language plpgsql
set search_path = pg_catalog, orange
as $$
begin
  new.job_type := coalesce(nullif(btrim(new.job_type), ''), 'extract_and_store');
  new.idempotency_key := coalesce(
    nullif(btrim(new.idempotency_key), ''),
    'memory-write:' || new.ingestion_id::text
  );
  return new;
end;
$$;

create or replace function orange.prepare_insight()
returns trigger
language plpgsql
set search_path = pg_catalog, orange
as $$
declare
  owner_session orange.memory_sessions%rowtype;
begin
  select *
  into owner_session
  from orange.memory_sessions
  where id = new.source_session_id;

  if not found then
    raise exception 'Orange memory session % does not exist', new.source_session_id
      using errcode = 'foreign_key_violation';
  end if;

  new.node_id := btrim(new.node_id);
  new.idempotency_key := coalesce(nullif(btrim(new.idempotency_key), ''), new.node_id);
  new.scope := owner_session.scope;
  new.user_id := owner_session.user_id;
  new.user_email := owner_session.user_email;
  new.organization_id := owner_session.organization_id;
  new.contributed_by_user_id := owner_session.contributed_by_user_id;
  new.contributed_by := owner_session.contributed_by;
  new.source := owner_session.source;

  if new.embedding is not null and new.embedding_updated_at is null then
    new.embedding_updated_at := now();
  end if;
  return new;
end;
$$;

create or replace function orange.prepare_memory_edge()
returns trigger
language plpgsql
set search_path = pg_catalog, orange
as $$
declare
  source_scope text;
  source_user_id uuid;
  source_organization_id uuid;
  target_scope text;
  target_user_id uuid;
  target_organization_id uuid;
  source_key text;
  target_key text;
begin
  new.relationship := upper(btrim(new.relationship));

  if new.source_session_id is not null then
    select scope, user_id, organization_id, 'session:' || id::text
    into source_scope, source_user_id, source_organization_id, source_key
    from orange.memory_sessions
    where id = new.source_session_id;
  elsif new.source_insight_id is not null then
    select scope, user_id, organization_id, 'insight:' || id::text
    into source_scope, source_user_id, source_organization_id, source_key
    from orange.insights
    where id = new.source_insight_id;
  end if;

  if source_scope is null then
    raise exception 'Orange edge source does not exist'
      using errcode = 'foreign_key_violation';
  end if;

  if new.target_session_id is not null then
    select scope, user_id, organization_id, 'session:' || id::text
    into target_scope, target_user_id, target_organization_id, target_key
    from orange.memory_sessions
    where id = new.target_session_id;
  elsif new.target_insight_id is not null then
    select scope, user_id, organization_id, 'insight:' || id::text
    into target_scope, target_user_id, target_organization_id, target_key
    from orange.insights
    where id = new.target_insight_id;
  end if;

  if target_scope is null then
    raise exception 'Orange edge target does not exist'
      using errcode = 'foreign_key_violation';
  end if;

  if source_scope is distinct from target_scope
     or source_user_id is distinct from target_user_id
     or source_organization_id is distinct from target_organization_id then
    raise exception 'Orange edges cannot cross memory scope owners'
      using errcode = 'check_violation';
  end if;

  new.scope := target_scope;
  new.user_id := target_user_id;
  new.organization_id := target_organization_id;
  new.idempotency_key := coalesce(
    nullif(btrim(new.idempotency_key), ''),
    new.relationship || ':' || source_key || ':' || target_key
  );
  return new;
end;
$$;

drop trigger if exists prepare_memory_session on orange.memory_sessions;
create trigger prepare_memory_session
before insert or update on orange.memory_sessions
for each row execute function orange.prepare_memory_session();

drop trigger if exists prepare_memory_write_job on orange.memory_write_jobs;
create trigger prepare_memory_write_job
before insert or update on orange.memory_write_jobs
for each row execute function orange.prepare_memory_write_job();

drop trigger if exists prepare_insight on orange.insights;
create trigger prepare_insight
before insert or update on orange.insights
for each row execute function orange.prepare_insight();

drop trigger if exists prepare_memory_edge on orange.memory_edges;
create trigger prepare_memory_edge
before insert or update on orange.memory_edges
for each row execute function orange.prepare_memory_edge();

drop trigger if exists set_updated_at on orange.memory_sessions;
create trigger set_updated_at
before update on orange.memory_sessions
for each row execute function orange.set_updated_at();

drop trigger if exists set_updated_at on orange.insights;
create trigger set_updated_at
before update on orange.insights
for each row execute function orange.set_updated_at();

drop trigger if exists set_updated_at on orange.memory_edges;
create trigger set_updated_at
before update on orange.memory_edges
for each row execute function orange.set_updated_at();

drop trigger if exists set_updated_at on orange.graph_scope_versions;
create trigger set_updated_at
before update on orange.graph_scope_versions
for each row execute function orange.set_updated_at();

create or replace function orange.bump_graph_scope_version(
  p_scope text,
  p_user_id uuid,
  p_organization_id uuid
)
returns void
language plpgsql
security definer
set search_path = pg_catalog, orange
as $$
declare
  target_owner_id uuid;
begin
  target_owner_id := case
    when p_scope = 'user' then p_user_id
    when p_scope = 'global' then p_organization_id
    else null
  end;

  if target_owner_id is null then
    return;
  end if;

  insert into orange.graph_scope_versions (scope, owner_id, version, last_changed_at)
  values (p_scope, target_owner_id, 1, now())
  on conflict (scope, owner_id)
  do update set
    version = orange.graph_scope_versions.version + 1,
    last_changed_at = excluded.last_changed_at;
end;
$$;

create or replace function orange.bump_graph_version_from_row()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, orange
as $$
begin
  if tg_op = 'INSERT' then
    perform orange.bump_graph_scope_version(new.scope, new.user_id, new.organization_id);
    return new;
  end if;

  if tg_op = 'DELETE' then
    perform orange.bump_graph_scope_version(old.scope, old.user_id, old.organization_id);
    return old;
  end if;

  if old.scope is distinct from new.scope
     or old.user_id is distinct from new.user_id
     or old.organization_id is distinct from new.organization_id then
    perform orange.bump_graph_scope_version(old.scope, old.user_id, old.organization_id);
  end if;
  perform orange.bump_graph_scope_version(new.scope, new.user_id, new.organization_id);
  return new;
end;
$$;

drop trigger if exists bump_graph_version on orange.memory_sessions;
create trigger bump_graph_version
after insert or update or delete on orange.memory_sessions
for each row execute function orange.bump_graph_version_from_row();

drop trigger if exists bump_graph_version on orange.insights;
create trigger bump_graph_version
after insert or update or delete on orange.insights
for each row execute function orange.bump_graph_version_from_row();

drop trigger if exists bump_graph_version on orange.memory_edges;
create trigger bump_graph_version
after insert or update or delete on orange.memory_edges
for each row execute function orange.bump_graph_version_from_row();

create or replace function orange.get_graph_version(
  p_scope text default 'both',
  p_user_id uuid default null,
  p_organization_id uuid default null
)
returns table (
  version text,
  change_sequence bigint,
  last_changed_at timestamptz
)
language sql
stable
set search_path = pg_catalog, orange
as $$
  with visible_versions as (
    select v.scope, v.version, v.last_changed_at
    from orange.graph_scope_versions v
    where
      (p_scope in ('user', 'both') and v.scope = 'user' and v.owner_id = p_user_id)
      or
      (p_scope in ('global', 'both') and v.scope = 'global' and v.owner_id = p_organization_id)
  ), aggregated as (
    select
      coalesce(max(version) filter (where scope = 'user'), 0) as user_version,
      coalesce(max(version) filter (where scope = 'global'), 0) as global_version,
      coalesce(sum(version), 0)::bigint as change_sequence,
      max(last_changed_at) as last_changed_at
    from visible_versions
  )
  select
    'u:' || user_version::text || ':g:' || global_version::text,
    change_sequence,
    last_changed_at
  from aggregated;
$$;

create or replace function orange.claim_memory_write_jobs(
  p_worker_id text,
  p_limit integer default 1,
  p_lease_seconds integer default 300
)
returns setof orange.memory_write_jobs
language plpgsql
security definer
set search_path = pg_catalog, orange
as $$
begin
  if nullif(btrim(p_worker_id), '') is null then
    raise exception 'worker_id is required' using errcode = 'invalid_parameter_value';
  end if;

  -- Exhausted stale leases become terminal before the next claim attempt.
  update orange.memory_write_jobs
  set
    status = 'dead_letter',
    dead_lettered_at = now(),
    processed_at = now(),
    locked_by = null,
    locked_at = null,
    lease_expires_at = null,
    error = coalesce(error, 'Maximum attempts exhausted after lease expiry')
  where status = 'running'
    and lease_expires_at <= now()
    and attempt_count >= max_attempts;

  return query
  with candidates as (
    select job.id
    from orange.memory_write_jobs job
    where
      (
        (job.status in ('queued', 'retrying') and job.available_at <= now())
        or
        (job.status = 'running' and job.lease_expires_at <= now())
      )
      and job.attempt_count < job.max_attempts
    order by job.priority desc, job.available_at, job.created_at
    for update skip locked
    limit least(greatest(coalesce(p_limit, 1), 1), 50)
  )
  update orange.memory_write_jobs job
  set
    status = 'running',
    attempt_count = job.attempt_count + 1,
    locked_by = btrim(p_worker_id),
    locked_at = now(),
    lease_expires_at = now() + make_interval(secs => least(greatest(coalesce(p_lease_seconds, 300), 30), 3600)),
    last_attempt_at = now(),
    error = null
  from candidates
  where job.id = candidates.id
  returning job.*;
end;
$$;

create or replace function orange.finish_memory_write_job(
  p_job_id uuid,
  p_worker_id text,
  p_succeeded boolean,
  p_result jsonb default '{}'::jsonb,
  p_error text default null,
  p_retry_delay_seconds integer default 30
)
returns orange.memory_write_jobs
language plpgsql
security definer
set search_path = pg_catalog, orange
as $$
declare
  finished_job orange.memory_write_jobs%rowtype;
begin
  update orange.memory_write_jobs job
  set
    status = case
      when p_succeeded then 'succeeded'
      when job.attempt_count >= job.max_attempts then 'dead_letter'
      else 'retrying'
    end,
    result = coalesce(p_result, '{}'::jsonb),
    error = case when p_succeeded then null else coalesce(p_error, 'Memory write failed') end,
    available_at = case
      when p_succeeded or job.attempt_count >= job.max_attempts then job.available_at
      else now() + make_interval(secs => least(greatest(coalesce(p_retry_delay_seconds, 30), 0), 86400))
    end,
    processed_at = case
      when p_succeeded or job.attempt_count >= job.max_attempts then now()
      else null
    end,
    completed_at = case when p_succeeded then now() else null end,
    dead_lettered_at = case
      when not p_succeeded and job.attempt_count >= job.max_attempts then now()
      else null
    end,
    locked_by = null,
    locked_at = null,
    lease_expires_at = null
  where job.id = p_job_id
    and job.status = 'running'
    and job.locked_by = btrim(p_worker_id)
  returning job.* into finished_job;

  if not found then
    raise exception 'Memory job is not running under worker %', p_worker_id
      using errcode = 'object_not_in_prerequisite_state';
  end if;
  return finished_job;
end;
$$;

-- RLS helpers deliberately expose identity checks, not underlying user or
-- membership records. They are SECURITY DEFINER so nested RLS cannot turn a
-- valid authenticated user into an empty result.
create or replace function orange.current_orange_user_id()
returns uuid
language sql
stable
security definer
set search_path = ''
as $$
  select u.id
  from orange.users u
  where u.auth_user_id = (select auth.uid())
  limit 1;
$$;

create or replace function orange.can_read_memory_scope(
  p_scope text,
  p_user_id uuid,
  p_organization_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select case
    when p_scope = 'user' then
      p_user_id = orange.current_orange_user_id()
    when p_scope = 'global' then
      exists (
        select 1
        from orange.organization_members membership
        where membership.organization_id = p_organization_id
          and membership.user_id = orange.current_orange_user_id()
      )
    else false
  end;
$$;

alter table orange.memory_sessions enable row level security;
alter table orange.insights enable row level security;
alter table orange.memory_edges enable row level security;
alter table orange.graph_scope_versions enable row level security;

drop policy if exists orange_memory_sessions_read on orange.memory_sessions;
create policy orange_memory_sessions_read
on orange.memory_sessions
for select
to authenticated
using (orange.can_read_memory_scope(scope, user_id, organization_id));

drop policy if exists orange_insights_read on orange.insights;
create policy orange_insights_read
on orange.insights
for select
to authenticated
using (orange.can_read_memory_scope(scope, user_id, organization_id));

drop policy if exists orange_memory_edges_read on orange.memory_edges;
create policy orange_memory_edges_read
on orange.memory_edges
for select
to authenticated
using (orange.can_read_memory_scope(scope, user_id, organization_id));

drop policy if exists orange_graph_scope_versions_read on orange.graph_scope_versions;
create policy orange_graph_scope_versions_read
on orange.graph_scope_versions
for select
to authenticated
using (
  (scope = 'user' and owner_id = orange.current_orange_user_id())
  or
  (scope = 'global' and orange.can_read_memory_scope('global', null, owner_id))
);

revoke all on orange.memory_sessions from anon, authenticated;
revoke all on orange.insights from anon, authenticated;
revoke all on orange.memory_edges from anon, authenticated;
revoke all on orange.graph_scope_versions from anon, authenticated;
revoke all on function orange.current_orange_user_id() from public, anon;
revoke all on function orange.can_read_memory_scope(text, uuid, uuid) from public, anon;
revoke all on function orange.get_graph_version(text, uuid, uuid) from public, anon;
revoke all on function orange.bump_graph_scope_version(text, uuid, uuid)
  from public, anon, authenticated;
revoke all on function orange.claim_memory_write_jobs(text, integer, integer) from public, anon, authenticated;
revoke all on function orange.finish_memory_write_job(uuid, text, boolean, jsonb, text, integer)
  from public, anon, authenticated;

grant usage on schema orange to authenticated;
grant select on orange.memory_sessions to authenticated;
grant select on orange.insights to authenticated;
grant select on orange.memory_edges to authenticated;
grant select on orange.graph_scope_versions to authenticated;
grant execute on function orange.current_orange_user_id() to authenticated;
grant execute on function orange.can_read_memory_scope(text, uuid, uuid) to authenticated;
grant execute on function orange.get_graph_version(text, uuid, uuid) to authenticated;

grant usage on schema orange to service_role;
grant all privileges on orange.memory_sessions to service_role;
grant all privileges on orange.insights to service_role;
grant all privileges on orange.memory_edges to service_role;
grant all privileges on orange.graph_scope_versions to service_role;
grant all privileges on orange.memory_write_jobs to service_role;
grant execute on function orange.get_graph_version(text, uuid, uuid) to service_role;
grant execute on function orange.claim_memory_write_jobs(text, integer, integer) to service_role;
grant execute on function orange.finish_memory_write_job(uuid, text, boolean, jsonb, text, integer)
  to service_role;

-- Realtime publishes only graph-safe tables. RLS still determines which rows
-- an authenticated subscriber can receive.
alter table orange.memory_sessions replica identity full;
alter table orange.insights replica identity full;
alter table orange.memory_edges replica identity full;
alter table orange.graph_scope_versions replica identity full;

do $$
declare
  graph_table text;
begin
  if exists (select 1 from pg_catalog.pg_publication where pubname = 'supabase_realtime') then
    foreach graph_table in array array[
      'memory_sessions',
      'insights',
      'memory_edges',
      'graph_scope_versions'
    ]
    loop
      if not exists (
        select 1
        from pg_catalog.pg_publication_tables
        where pubname = 'supabase_realtime'
          and schemaname = 'orange'
          and tablename = graph_table
      ) then
        execute format('alter publication supabase_realtime add table orange.%I', graph_table);
      end if;
    end loop;
  end if;
end;
$$;
