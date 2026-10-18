# Admin ingestion and vector retrieval corrections

Verified locally on PostgreSQL 17.11 and pgvector 0.8.6. These changes have not
been applied to the hosted Supabase project. The first admin migration is still
unapplied there, so its local definition was corrected before rollout.

## Legacy ingestion contract

The admin schema removes global content-hash uniqueness and requires revision
ownership. The old CLI cannot safely upsert or globally prune that schema.
The previous guard depended only on `ADMIN_PANEL_ENABLED`; with it off, the CLI
could compute embeddings and then fail on the incompatible database contract.

`ingest.py` now checks for `revision_id` with a zero-row database projection
before embeddings or writes. A successful projection rejects the legacy writer
with instructions to use `/admin`; only a missing-column error permits legacy
ingestion. Unexpected network/auth/table errors fail closed. `--validate` requires
no database connection and remains supported. This does not introduce a second
versioned ingestion path alongside the website worker.

The pre-admin `sql/knowledge.sql` bootstrap also rejects a versioned schema in
an explicit transaction, preventing a rerun from replacing the published-only
RPCs or recreating the old indexes. Regression tests verify old-schema writes,
migrated-schema rejection with flags off, local validation, and lookup errors.

## ANN publication filtering

The statement "a view prevents vector index use" was too broad. The original
joined published view could use HNSW in a local forced-index diagnostic. However,
the index covered all revisions; nearer unpublished chunks consumed ANN
candidates before publication filtering. The diagnostic returned zero published
results despite available published chunks.

The corrected migration adds a derived `is_published` flag, maintained by a
source-publication trigger in the same transaction as publishing, archiving or
restoring. The invoker view filters that flag directly. Partial HNSW and GIN
indexes include only published chunks. Draft/prepared/historical rows retain
their IDs and page/citation metadata without entering either index.

The new rollback-only fixture contains 1,000 published chunks and 2,000 closer
unpublished chunks. It returns 10 dense results. EXPLAIN of the view and the
actual hybrid SQL body finds the HNSW index; the hybrid plan also finds the GIN
index. The diagnostic disables sequential scans only to exercise index
eligibility. Production may choose a scan when the corpus is small; this test
does not claim production always selects HNSW or that ANN provides exact recall.

SET search_path makes the SQL RPC opaque to an outer EXPLAIN in this environment.
Inspecting an outer Function Scan alone cannot establish index use in its body.

## Completed checks

- 519 backend tests passed.
- Real PostgreSQL assertions passed for publication membership, draft isolation,
  archive/restore, pointer removal/restoration, citation preservation, atomic
  ingestion and publication, lease recovery and account access rules.
- Legacy SQL bootstrap rejection passed on the migrated schema.
- Full repository schema integration passed with hosted extension infrastructure
  stand-ins; hosted Auth/Storage/cron behavior is not certified by this test.
- A read-only follow-up source review found no concrete blocker in these fixes.

Run from `fincoach-backend`, with the dedicated local test container running:

```powershell
.\.venv\Scripts\python.exe docs/admin/test_local_database.py --retrieval-plan
.\.venv\Scripts\python.exe docs/admin/test_local_database.py --full-schema
```
