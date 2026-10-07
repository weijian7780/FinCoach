# Admin addition: diagram consistency

This documents the locally implemented admin scope. It is an addition to the
existing system diagrams, not a replacement for the complete context/Level 0
diagrams or evidence of deployment. The thesis document has not been overwritten.

## Context and Level 0 boundary additions

Add **Admin** as an external person interacting with process **0 FinCoach System**.
Keep the existing student flows. Add exactly the same boundary information to
the complete Level 0 diagram:

| Direction | Context flow | Corresponding Level 0 process |
|---|---|---|
| Admin → FinCoach | Admin access details | Manage Admin Access |
| FinCoach → Admin | Admin access status | Manage Admin Access |
| Admin → FinCoach | Account search details | Manage Account Access |
| FinCoach → Admin | Account list | Manage Account Access |
| Admin → FinCoach | Account status details and reason | Manage Account Access |
| FinCoach → Admin | Account status confirmation | Manage Account Access |
| Admin → FinCoach | Knowledge document, source URLs and check date | Maintain Knowledge Base |
| Admin → FinCoach | Knowledge preparation, publication, archive and restoration details | Maintain Knowledge Base |
| FinCoach → Admin | Knowledge revision, preview and processing status | Maintain Knowledge Base |
| Admin → FinCoach | Knowledge search question | Maintain Knowledge Base |
| FinCoach → Admin | Knowledge search results | Maintain Knowledge Base |
| Admin → FinCoach | System overview request | Review System Activity |
| FinCoach → Admin | Aggregate system overview and service status | Review System Activity |
| Admin → FinCoach | Audit history request | Review System Activity |
| FinCoach → Admin | Admin audit history | Review System Activity |

Number these processes within the existing model, rather than treating this
table as a second Level 0 DFD. Lower-level preparation/publishing steps may be
decomposed while preserving the parent boundary. Context diagrams contain one
process and no stores. Store reads/writes go through processes; Admin never
connects directly to a store. Use separate one-way, noun-labelled arrows.

## Exact store and ERD names

Use these exact business names on both diagrams. Physical table names belong in
the mapping/data dictionary, not as extra entities with different business names.

| DFD store name | ERD entity name | Physical representation |
|---|---|---|
| ACCOUNT ACCESS | ACCOUNT ACCESS | `account_access` |
| KNOWLEDGE SOURCE | KNOWLEDGE SOURCE | `knowledge_sources` |
| KNOWLEDGE REVISION | KNOWLEDGE REVISION | `knowledge_revisions` |
| KNOWLEDGE DOCUMENT | KNOWLEDGE DOCUMENT | Existing `knowledge_documents`: one chunk per row |
| ADMIN AUDIT LOG | ADMIN AUDIT LOG | `admin_audit_logs` |

Assign unused D-number identifiers when merging into the full DFD. If you prefer
a grouped **KNOWLEDGE BASE** store, explicitly map it to KNOWLEDGE SOURCE,
KNOWLEDGE REVISION and KNOWLEDGE DOCUMENT in the dictionary; it is not a separate
implemented table. Private uploaded originals are retained in Storage and are
referenced by revision metadata. USER remains mapped to existing profiles/Auth.

Admin is a role of USER, not a new single-instance ERD entity. ACCOUNT ACCESS
holds role/status for every user, so it has multiple instances. A dedicated
initial admin account does not imply that only one admin could ever exist.

## Relationship and attribute additions

Use singular ALL-CAPS names, starred identifiers and Crow's Foot notation.

| Parent / child | Forward / reverse verbs | Cardinality and modality |
|---|---|---|
| USER / ACCOUNT ACCESS | has / belongs to | 1:1; access row requires one user; provisioning creates one per account |
| KNOWLEDGE SOURCE / KNOWLEDGE REVISION | has / belongs to | 1:N; source may have revisions; revision requires one source |
| KNOWLEDGE REVISION / KNOWLEDGE DOCUMENT | contains / belongs to | 1:N; draft may contain zero chunks; chunk requires one revision |
| USER / KNOWLEDGE REVISION | creates / is created by | 1:N; imported revision may have no creator; user may create zero revisions |
| USER / ADMIN AUDIT LOG | performs / records activity by | 1:N; retained audit may have no actor after account removal |

ACCOUNT ACCESS: `*User ID`, role, access status, email/display-name cache and
timestamps. KNOWLEDGE SOURCE: `*Source ID`, stable source key, published title,
archival status, latest and published revision references. KNOWLEDGE REVISION:
`*Revision ID`, source reference, title, content, source check date, original file
reference, preparation status, creator and timestamps. KNOWLEDGE DOCUMENT:
`*Document ID`, revision reference, chunk content, source, page/index metadata,
hash and **1024-dimensional embedding**, matching BGE-M3. ADMIN AUDIT LOG:
`*Audit ID`, optional actor reference, action, target, details and timestamp.

Source URLs are physically stored as a JSON array. For a normalized logical ERD,
show a SOURCE REFERENCE child (one URL per instance) and explain its physical
JSON representation; do not claim the JSON repeating group itself is strict 1NF.
Likewise, derived chunk counts and metadata caches are implementation details,
not evidence that the physical schema is a fully normalized conceptual model.

Do not add administrator access to individual student transactions or backups:
the website exposes account metadata and aggregate counts only. Suspension adds
access checks to student processes; it does not delete their records.

An API key is a credential, not a DFD entity. If the examiner requires AI provider
calls to remain internal in this thesis model, represent them inside AI coaching
and receipt processing. Adding Admin represents a distinct implemented external
person; it does not itself replace or balance an AI-provider data flow. Apply the
same boundary decision consistently at every level and state it in the thesis.
