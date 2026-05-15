create schema if not exists orange;
create extension if not exists pgcrypto with schema extensions;

create or replace function orange.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table if not exists orange.organizations (
  id uuid primary key default extensions.gen_random_uuid(),
  external_org_id text unique,
  slug text not null unique,
  name text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists orange.users (
  id uuid primary key default extensions.gen_random_uuid(),
  auth_user_id uuid unique references auth.users(id) on delete set null,
  external_user_id text unique,
  email text,
  display_name text,
  role text,
  company text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint orange_users_has_identity check (
    auth_user_id is not null
    or nullif(external_user_id, '') is not null
    or nullif(email, '') is not null
  )
);

create table if not exists orange.organization_members (
  organization_id uuid not null references orange.organizations(id) on delete cascade,
  user_id uuid not null references orange.users(id) on delete cascade,
  membership_role text not null default 'member',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (organization_id, user_id)
);

create table if not exists orange.source_accounts (
  id uuid primary key default extensions.gen_random_uuid(),
  organization_id uuid references orange.organizations(id) on delete cascade,
  user_id uuid references orange.users(id) on delete set null,
  source text not null,
  external_account_id text not null,
  display_name text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, source, external_account_id)
);

create table if not exists orange.session_ingestions (
  id uuid primary key default extensions.gen_random_uuid(),
  organization_id uuid references orange.organizations(id) on delete set null,
  user_id uuid references orange.users(id) on delete set null,
  source text not null,
  session_id text not null,
  external_session_id text,
  graph_session_node_id text not null,
  client_name text,
  client_version text,
  source_url text,
  title text,
  summary text,
  started_at timestamptz,
  ended_at timestamptz,
  ingested_at timestamptz not null default now(),
  message_count integer not null default 0,
  status text not null default 'received',
  metadata jsonb not null default '{}'::jsonb,
  normalized_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, source, session_id)
);

create table if not exists orange.session_messages (
  id bigserial primary key,
  ingestion_id uuid not null references orange.session_ingestions(id) on delete cascade,
  turn_index integer not null,
  role text not null,
  content text not null,
  occurred_at timestamptz,
  message_id text,
  participant_id text,
  participant_name text,
  metadata jsonb not null default '{}'::jsonb,
  raw_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (ingestion_id, turn_index)
);

create table if not exists orange.memory_write_jobs (
  id uuid primary key default extensions.gen_random_uuid(),
  ingestion_id uuid not null references orange.session_ingestions(id) on delete cascade,
  status text not null default 'queued',
  attempt_count integer not null default 0,
  locked_at timestamptz,
  processed_at timestamptz,
  error text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (ingestion_id)
);

create index if not exists idx_orange_users_auth_user_id on orange.users(auth_user_id);
create index if not exists idx_orange_users_external_user_id on orange.users(external_user_id);
create index if not exists idx_orange_members_user on orange.organization_members(user_id);
create index if not exists idx_orange_source_accounts_user on orange.source_accounts(user_id);
create index if not exists idx_orange_session_ingestions_user_created
  on orange.session_ingestions(user_id, created_at desc);
create index if not exists idx_orange_session_ingestions_org_created
  on orange.session_ingestions(organization_id, created_at desc);
create index if not exists idx_orange_session_ingestions_status
  on orange.session_ingestions(status, created_at);
create index if not exists idx_orange_session_messages_ingestion
  on orange.session_messages(ingestion_id, turn_index);
create index if not exists idx_orange_memory_jobs_status
  on orange.memory_write_jobs(status, created_at);

drop trigger if exists set_updated_at on orange.organizations;
create trigger set_updated_at
before update on orange.organizations
for each row execute function orange.set_updated_at();

drop trigger if exists set_updated_at on orange.users;
create trigger set_updated_at
before update on orange.users
for each row execute function orange.set_updated_at();

drop trigger if exists set_updated_at on orange.organization_members;
create trigger set_updated_at
before update on orange.organization_members
for each row execute function orange.set_updated_at();

drop trigger if exists set_updated_at on orange.source_accounts;
create trigger set_updated_at
before update on orange.source_accounts
for each row execute function orange.set_updated_at();

drop trigger if exists set_updated_at on orange.session_ingestions;
create trigger set_updated_at
before update on orange.session_ingestions
for each row execute function orange.set_updated_at();

drop trigger if exists set_updated_at on orange.memory_write_jobs;
create trigger set_updated_at
before update on orange.memory_write_jobs
for each row execute function orange.set_updated_at();

alter table orange.organizations enable row level security;
alter table orange.users enable row level security;
alter table orange.organization_members enable row level security;
alter table orange.source_accounts enable row level security;
alter table orange.session_ingestions enable row level security;
alter table orange.session_messages enable row level security;
alter table orange.memory_write_jobs enable row level security;

revoke all on schema orange from anon, authenticated;
revoke all on all tables in schema orange from anon, authenticated;
revoke all on all sequences in schema orange from anon, authenticated;

grant usage on schema orange to service_role;
grant all privileges on all tables in schema orange to service_role;
grant all privileges on all sequences in schema orange to service_role;
