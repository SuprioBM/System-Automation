-- Same mismatch as 0003, second value: code uses 'linkedin' everywhere
-- (generation.py, validation.py, approval.py, publish.py, routing.py), not
-- 'linkedin_post'. Align the constraint with the code.
alter table artifacts drop constraint artifacts_artifact_type_check;
alter table artifacts add constraint artifacts_artifact_type_check
    check (artifact_type in ('resume', 'linkedin', 'portfolio'));
