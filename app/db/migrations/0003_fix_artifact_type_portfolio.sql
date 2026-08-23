-- 0001_init.sql's check constraint used 'portfolio_update', but every call
-- site (generation.py, validation.py, approval.py, publish.py, routing.py's
-- RouteTarget Literal) consistently uses 'portfolio'. Fix the constraint to
-- match the actual code rather than renaming it in six places.
alter table artifacts drop constraint artifacts_artifact_type_check;
alter table artifacts add constraint artifacts_artifact_type_check
    check (artifact_type in ('resume', 'linkedin_post', 'portfolio'));
