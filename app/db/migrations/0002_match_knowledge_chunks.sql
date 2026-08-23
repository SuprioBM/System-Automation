-- RPC used by the Supabase REST client to do cosine-similarity retrieval,
-- since PostgREST can't express the pgvector <-> operator directly.
create or replace function match_knowledge_chunks(
    query_embedding vector(384),
    match_owner text,
    match_count int default 8
)
returns table (
    id uuid,
    project_id uuid,
    source text,
    content text,
    metadata jsonb,
    similarity float
)
language sql stable
as $$
    select
        id,
        project_id,
        source,
        content,
        metadata,
        1 - (embedding <=> query_embedding) as similarity
    from knowledge_chunks
    where owner = match_owner
    order by embedding <=> query_embedding
    limit match_count;
$$;
