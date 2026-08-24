-- Track the Discord failure-notification message so it can be updated in
-- place on resume/completion/failed-again (spec §17), instead of spamming a
-- new message each time.
alter table workflow_runs add column if not exists failure_message_id text;
