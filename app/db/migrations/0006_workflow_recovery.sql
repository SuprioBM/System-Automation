-- Checkpoint-based failure recovery: extends workflow_runs (no new/duplicate
-- workflow-state table) with what's needed to know a failed run is
-- recoverable and where it stopped. status already has no CHECK constraint,
-- so 'cancelled' is usable immediately alongside the existing values.
alter table workflow_runs add column if not exists recoverable boolean not null default false;
alter table workflow_runs add column if not exists failed_node text;
alter table workflow_runs add column if not exists attempt_count integer not null default 0;

create index if not exists idx_workflow_runs_recoverable on workflow_runs (recoverable) where recoverable;
