-- DevSync core schema.
-- Structured source of truth (projects), vector knowledge (knowledge_chunks),
-- workflow observability/idempotency (workflow_runs, processed_events -- NOT
-- the LangGraph checkpoint tables themselves, which langgraph-checkpoint-postgres
-- manages separately via PostgresSaver.setup()), and artifact/approval history.

create extension if not exists vector;
create extension if not exists pgcrypto;

-- ── Structured source of truth ──────────────────────────────────────────
create table if not exists projects (
    id                uuid primary key default gen_random_uuid(),
    owner             text not null,
    name              text not null,
    slug              text not null unique,
    description       text,
    problem           text,
    solution          text,
    technologies      jsonb not null default '[]'::jsonb,
    architecture      text,
    features          jsonb not null default '[]'::jsonb,
    technical_depth   text,
    impact            text,
    completion_status text,
    category          text check (category in ('featured', 'insight', 'ignore')),
    score             numeric,
    resume_bullets    jsonb not null default '[]'::jsonb,
    linkedin_angle    text,
    repository_url    text,
    live_url          text,
    source_commit     text,
    source_repository text,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);
create index if not exists idx_projects_category_score on projects (category, score desc);

-- ── Vector knowledge (RAG) ───────────────────────────────────────────────
-- Dimension matches EMBEDDING_MODEL=BAAI/bge-small-en-v1.5 (384-d). If the
-- embedding model changes, this column must be recreated at the new dimension.
create table if not exists knowledge_chunks (
    id          uuid primary key default gen_random_uuid(),
    owner       text not null,
    project_id  uuid references projects(id) on delete cascade,
    source      text not null,
    content     text not null,
    embedding   vector(384) not null,
    metadata    jsonb not null default '{}'::jsonb,
    created_at  timestamptz not null default now()
);
create index if not exists idx_knowledge_chunks_owner on knowledge_chunks (owner);
create index if not exists idx_knowledge_chunks_embedding on knowledge_chunks
    using ivfflat (embedding vector_cosine_ops) with (lists = 100);

-- ── Workflow observability + idempotency ────────────────────────────────
create table if not exists workflow_runs (
    workflow_id     text primary key,
    run_id          text not null,
    event_id        text unique,
    repository      text,
    commit_sha      text,
    status          text not null default 'running',
    current_stage   text,
    current_node    text,
    retry_count     integer not null default 0,
    error_state     jsonb,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);
create index if not exists idx_workflow_runs_status on workflow_runs (status);

create table if not exists processed_events (
    event_id     text primary key,
    delivery_id  text,
    source       text not null,
    workflow_id  text,
    received_at  timestamptz not null default now()
);

-- ── Artifacts + approvals ────────────────────────────────────────────────
create table if not exists artifacts (
    id                 uuid primary key default gen_random_uuid(),
    workflow_id        text not null references workflow_runs(workflow_id) on delete cascade,
    run_id             text not null,
    artifact_type      text not null check (artifact_type in ('resume', 'linkedin_post', 'portfolio_update')),
    version            integer not null,
    status             text not null default 'draft' check (status in ('draft', 'approved', 'rejected', 'superseded')),
    content            jsonb not null default '{}'::jsonb,
    validation_results jsonb,
    storage_url        text,
    created_at         timestamptz not null default now(),
    approved_at        timestamptz
);
create index if not exists idx_artifacts_workflow on artifacts (workflow_id, artifact_type, version desc);

create table if not exists resume_versions (
    id                  uuid primary key default gen_random_uuid(),
    artifact_id         uuid references artifacts(id) on delete set null,
    version             integer not null unique,
    pdf_storage_url     text not null,
    tex_snapshot        text not null,
    is_active           boolean not null default false,
    validation_results  jsonb,
    created_at          timestamptz not null default now()
);
create unique index if not exists idx_resume_versions_single_active on resume_versions (is_active) where is_active;

create table if not exists approvals (
    id                 uuid primary key default gen_random_uuid(),
    workflow_id        text not null references workflow_runs(workflow_id) on delete cascade,
    run_id             text not null,
    artifact_id        uuid not null references artifacts(id) on delete cascade,
    artifact_version   integer not null,
    channel            text not null default 'discord',
    status             text not null default 'pending' check (status in ('pending', 'approved', 'rejected', 'changes_requested')),
    feedback           text,
    discord_message_id text,
    requested_at       timestamptz not null default now(),
    decided_at         timestamptz
);
create index if not exists idx_approvals_workflow on approvals (workflow_id, artifact_id);
