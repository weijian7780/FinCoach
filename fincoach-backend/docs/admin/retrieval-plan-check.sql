-- Read-only diagnostic on the dedicated local database, with temporary fixture
-- rows rolled back afterward. Uses the real 1024-dimensional index and RPCs.
\set ON_ERROR_STOP on
begin;
insert into public.knowledge_sources(id,source_key,title) values('90000000-0000-0000-0000-000000000001','plan-live.md','Live plan fixture');
insert into public.knowledge_revisions(id,source_id,title,content,status,chunk_count)
values('90000000-0000-0000-0000-000000000002','90000000-0000-0000-0000-000000000001','Live plan fixture','fixture','published',1000),
('90000000-0000-0000-0000-000000000003','90000000-0000-0000-0000-000000000001','Hidden fixture','fixture','ready',2000);
-- Hidden vectors are deliberately closer to the query than published vectors.
insert into public.knowledge_documents(title,content,source,embedding,chunk_index,revision_id)
select 'Live plan fixture','Visible retrieval plan fixture','plan-live.md',(array[0::real,1::real]||array_fill(0::real,array[1022]))::vector,n,'90000000-0000-0000-0000-000000000002' from generate_series(1,1000)n;
insert into public.knowledge_documents(title,content,source,embedding,chunk_index,revision_id)
select 'Hidden fixture','Unpublished retrieval plan fixture','plan-live.md',(array[1::real,(n::real/10000)]||array_fill(0::real,array[1022]))::vector,n,'90000000-0000-0000-0000-000000000003' from generate_series(1,2000)n;
update public.knowledge_sources set latest_revision_id='90000000-0000-0000-0000-000000000003',published_revision_id='90000000-0000-0000-0000-000000000002' where id='90000000-0000-0000-0000-000000000001';
analyze public.knowledge_documents;
analyze public.knowledge_sources;
set local role service_role;
-- Diagnostic only: force eligibility to reveal ANN post-filter underfilling.
set local enable_seqscan=off;
do $$declare q vector:=(array[1::real,0::real]||array_fill(0::real,array[1022]))::vector;plan jsonb;normal_count integer;begin
 select count(*) into normal_count from public.match_knowledge_documents(q,10);
 execute 'explain(format json) select id from public.published_knowledge_documents order by embedding <=> $1 limit 10' into plan using q;
 raise notice 'DENSE RESULT COUNT: %; HNSW IN VIEW PLAN: %',normal_count,position('knowledge_documents_embedding_idx' in plan::text)>0;
 if normal_count<>10 then raise exception 'Hidden vectors starved published retrieval: %',normal_count;end if;
 if position('knowledge_documents_embedding_idx' in plan::text)=0 then raise exception 'Published vector index not eligible in diagnostic plan';end if;
 -- SET search_path prevents SQL RPC inlining; inspect the actual function body
 -- instead of mistaking an opaque Function Scan for proof of no index.
 execute 'explain(format json) '||regexp_replace(regexp_replace(regexp_replace((select prosrc from pg_proc where pronamespace='public'::regnamespace and proname='match_knowledge_documents_hybrid'),'\mquery_text\M','$1','g'),'\mquery_embedding\M','$2','g'),'\mmatch_count\M','$3','g') into plan using 'fixture',q,10;
 raise notice 'HNSW IN HYBRID BODY PLAN: %',position('knowledge_documents_embedding_idx' in plan::text)>0;
 raise notice 'HYBRID INDEX NAMES: %',jsonb_path_query_array(plan,'$.**."Index Name"');
 if position('knowledge_documents_embedding_idx' in plan::text)=0 or position('knowledge_documents_fts_idx' in plan::text)=0 then raise exception 'Hybrid retrieval did not use active corpus indexes';end if;
 if exists(select 1 from public.match_knowledge_documents_hybrid('fixture',q,10) m join public.knowledge_documents d on d.id=m.id where d.revision_id='90000000-0000-0000-0000-000000000003') then raise exception 'Hidden hybrid chunks leaked';end if;
end$$;
rollback;
