alter table orange.session_ingestions
  add column if not exists scope text not null default 'user',
  add column if not exists user_email text;

create index if not exists idx_orange_session_ingestions_scope_created
  on orange.session_ingestions(scope, created_at desc);

create index if not exists idx_orange_session_ingestions_user_email_created
  on orange.session_ingestions(user_email, created_at desc);
