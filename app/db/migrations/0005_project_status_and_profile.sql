-- §48: distinguish a project's lifecycle status (active/archived/rejected)
-- from its category. Replacement now archives the losing project instead of
-- deleting it, preserving historical/RAG context.
alter table projects add column if not exists status text not null default 'active'
    check (status in ('active', 'archived', 'rejected'));
create index if not exists idx_projects_status on projects (owner, status);

-- §43/§50/§51: profile/portfolio sections other than featuredProjects
-- (site, about, skills, experiences, insightProjects, services, testimonials,
-- achievements, blogPosts). Flexible JSONB per section so each can have its
-- own shape. No graph node writes to this table -- it exists purely as a
-- durable store the portfolio site could read from instead of static files;
-- DevSync's automated project workflow never touches it (§44).
create table if not exists profile_sections (
    owner       text not null,
    section     text not null,
    content     jsonb not null default '{}'::jsonb,
    updated_at  timestamptz not null default now(),
    primary key (owner, section)
);
