import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { createClient, type Session, type SupabaseClient } from '@supabase/supabase-js';

type Config = { supabase_url: string; publishable_key: string; enabled: boolean };
type Tab = 'Overview' | 'Accounts' | 'Knowledge base' | 'Search test' | 'Audit history';
type Account = { user_id: string; role: string; status: string; email: string; display_name: string; created_at: string; last_sign_in_at: string | null };
type Source = { id: string; title: string; source_key: string; archived: boolean; published_revision_id: string | null; latest_revision_id: string | null; updated_at: string };
type Revision = { id: string; title: string; content?: string; source_urls?: string[]; checked_at: string | null; status: string; created_at: string; chunk_count: number; error_message: string | null; file_path: string | null };
type Detail = { source: Source; latest: Revision | null; revisions: Revision[] };
type Audit = { id: number; actor_id: string; action: string; target_type: string; target_id: string; details: Record<string, unknown>; created_at: string };
type Dashboard = { counts: Record<string, number>; components: Record<string, string>; providers: Record<string, boolean> };
type Match = { id: number; title: string; source: string; content: string; similarity: number };
type Editor = { title: string; content: string; urls: string; checked_at: string; upload_id?: string; expected_revision_id?: string | null };
type Preview = { chunk_count: number; excerpts: string[]; stale: boolean };
const tabs: Tab[] = ['Overview', 'Accounts', 'Knowledge base', 'Search test', 'Audit history'];
const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kuala_Lumpur', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
const emptyEditor = (): Editor => ({ title: '', content: '', urls: '', checked_at: today() });
const fmt = (value: string | null) => value ? new Date(value).toLocaleString('en-MY') : '—';
const badge = (value: string) => <span className={`badge ${value}`}>{value.replaceAll('_', ' ')}</span>;

export function App() {
  const [config, setConfig] = useState<Config | null>(null);
  const [client, setClient] = useState<SupabaseClient | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [allowed, setAllowed] = useState(false);
  const [checking, setChecking] = useState(false);
  const [tab, setTab] = useState<Tab>('Overview');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [searchEmail, setSearchEmail] = useState('');
  const [sources, setSources] = useState<Source[]>([]);
  const [audits, setAudits] = useState<Audit[]>([]);
  const [page, setPage] = useState(0);
  const [total, setTotal] = useState(0);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [editing, setEditing] = useState(false);
  const [openingSource, setOpeningSource] = useState<string | null>(null);
  const [editor, setEditor] = useState<Editor>(emptyEditor);
  const [dirty, setDirty] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [historyComplete, setHistoryComplete] = useState(false);
  const [question, setQuestion] = useState('');
  const [matches, setMatches] = useState<Match[]>([]);
  const [accountAction, setAccountAction] = useState<Account | null>(null);
  const [reason, setReason] = useState('');
  const [confirmation, setConfirmation] = useState<{ action: 'publish' | 'archive' | 'restore'; revisionId: string | null } | null>(null);
  // Prevent stale detail responses from switching the editor to another source.
  const detailRequest = useRef(0);
  const editorPanel = useRef<HTMLElement>(null);
  const editorHeading = useRef<HTMLHeadingElement>(null);
  const errorMessage = useRef<HTMLDivElement>(null);

  const api = useCallback(async <T,>(path: string, init: RequestInit = {}): Promise<T> => {
    const token = (await client?.auth.getSession())?.data.session?.access_token;
    const response = await fetch(`/api/admin${path}`, { ...init, headers: { ...(init.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers } });
    // A failed upstream request may return plain text instead of JSON.
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      if (response.status === 403) setAllowed(false);
      if (response.status === 401 && token) { setAllowed(false); await client?.auth.signOut({ scope: 'local' }); }
      throw new Error(typeof body?.detail === 'string' ? body.detail : response.status >= 500 ? 'The admin service is temporarily unavailable. Please retry.' : 'Please check the entered values and try again.');
    }
    if (body === null) throw new Error('The admin service returned an unreadable response. Please retry.');
    return body as T;
  }, [client]);

  useEffect(() => {
    let disposed = false;
    let unsubscribe: (() => void) | undefined;
    fetch('/api/admin/config').then(async response => {
      if (!response.ok) throw new Error('The admin service could not be reached.');
      const settings: Config = await response.json();
      if (disposed) return;
      setConfig(settings);
      if (!settings.supabase_url || !settings.publishable_key) throw new Error('Supabase client configuration is missing.');
      const instance = createClient(settings.supabase_url, settings.publishable_key, { auth: { flowType: 'pkce', storageKey: 'fincoach-admin-session' } });
      setClient(instance);
      const subscription = instance.auth.onAuthStateChange((_event, next) => { if (!disposed) setSession(next); });
      unsubscribe = () => subscription.data.subscription.unsubscribe();
      const cached = await instance.auth.getSession();
      if (!disposed) setSession(cached.data.session);
    }).catch(caught => { if (!disposed) setError(caught.message); });
    return () => { disposed = true; unsubscribe?.(); };
  }, []);

  useEffect(() => {
    let disposed = false;
    setAllowed(false);
    detailRequest.current++;
    // Drop previously loaded admin data whenever the authenticated identity
    // changes; authorization is still enforced independently by the server.
    setAccounts([]); setSources([]); setAudits([]); setDashboard(null); setDetail(null); setEditing(false); setMatches([]);
    if (!session || !client || !config?.enabled) { setChecking(false); return; }
    setChecking(true);
    api('/me').then(() => { if (!disposed) { setAllowed(true); setError(''); } }).catch(caught => { if (!disposed) setError(caught.message); }).finally(() => { if (!disposed) setChecking(false); });
    return () => { disposed = true; };
  }, [session?.user.id, client, config?.enabled, api]);

  useEffect(() => {
    const unload = (event: BeforeUnloadEvent) => { if (dirty) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', unload);
    return () => window.removeEventListener('beforeunload', unload);
  }, [dirty]);

  const loadPage = useCallback(async () => {
    if (!allowed) return;
    if (tab === 'Overview') setDashboard(await api<Dashboard>('/dashboard'));
    if (tab === 'Accounts') { const data = await api<{ items: Account[]; total: number }>(`/accounts?offset=${page * 25}&search=${encodeURIComponent(searchEmail)}`); setAccounts(data.items); setTotal(data.total); }
    if (tab === 'Knowledge base') { const data = await api<{ items: Source[]; total: number }>(`/knowledge?offset=${page * 25}`); setSources(data.items); setTotal(data.total); }
    if (tab === 'Audit history') { const data = await api<{ items: Audit[]; total: number }>(`/audit?offset=${page * 25}`); setAudits(data.items); setTotal(data.total); }
  }, [allowed, tab, page, api, searchEmail]);
  useEffect(() => {
    let disposed = false;
    loadPage().catch(caught => { if (!disposed) setError(caught.message); });
    return () => { disposed = true; };
  }, [loadPage]);

  useEffect(() => {
    // Show the editor immediately, including when opening a row far down a list.
    // Polling and saving the same source must not move focus during editing.
    if (!editing) return;
    editorPanel.current?.scrollIntoView({ block: 'start' });
    editorHeading.current?.focus({ preventScroll: true });
  }, [editing, detail?.source.id]);

  useEffect(() => {
    if (!error) return;
    errorMessage.current?.scrollIntoView({ block: 'nearest' });
    errorMessage.current?.focus({ preventScroll: true });
  }, [error]);

  async function run(action: () => Promise<void>) {
    setBusy(true); setError(''); setNotice('');
    try { await action(); } catch (caught) { setError(caught instanceof Error ? caught.message : 'Operation failed. Please retry.'); }
    finally { setBusy(false); }
  }

  async function openSource(id: string, preserveEditor = false) {
    const requestId = ++detailRequest.current;
    const data = await api<Detail>(`/knowledge/${id}`);
    if (requestId !== detailRequest.current) return;
    setDetail(data); setEditing(true);
    setHistoryComplete(data.revisions.length < 50);
    if (!preserveEditor) {
      setEditor({ title: data.latest?.title || data.source.title, content: data.latest?.content || '', urls: (data.latest?.source_urls || []).join('\n'), checked_at: data.latest?.checked_at || today(), expected_revision_id: data.source.latest_revision_id });
      setDirty(false); setPreview(null);
    }
  }
  useEffect(() => {
    if (!allowed || !detail || !['queued', 'processing'].includes(detail.latest?.status || '')) return;
    const id = setInterval(() => { openSource(detail.source.id, true).catch(caught => setError(caught.message)); }, 3000);
    return () => clearInterval(id);
  }, [allowed, detail?.source.id, detail?.latest?.status, api]);

  const body = () => ({ title: editor.title, content: editor.content, source_urls: editor.urls.split('\n').map(value => value.trim()).filter(Boolean), checked_at: editor.checked_at, expected_revision_id: editor.expected_revision_id || null, upload_id: editor.upload_id || null });
  const edit = (field: keyof Editor, value: string) => { setEditor(old => ({ ...old, [field]: value })); setDirty(true); setPreview(null); };
  const leaveEditor = () => !dirty || window.confirm('Discard unsaved document changes?');
  const closeEditor = () => {
    if (!leaveEditor()) return;
    detailRequest.current++;
    setEditing(false); setDetail(null); setEditor(emptyEditor()); setDirty(false); setPreview(null);
    setError(''); setNotice('');
  };
  async function actionKnowledge(action: string, revisionId: string | null) {
    if (!detail) return;
    await api(`/knowledge/${detail.source.id}/actions`, { method: 'POST', body: JSON.stringify({ action, revision_id: revisionId, expected_revision_id: detail.source.latest_revision_id }) });
    setConfirmation(null); await openSource(detail.source.id); await loadPage(); setNotice(`Document ${action === 'prepare' ? 'queued for processing' : action === 'archive' ? 'archived' : 'published'}.`);
  }

  if (!allowed) return <main className="login-shell"><div className="login-card">
    <div className="brand"><span className="brand-symbol">F</span><span>FinCoach<span className="brand-sub">ADMINISTRATION</span></span></div>
    <h1>Manage FinCoach</h1><p className="muted">Administrator access to accounts and the knowledge base.</p>
    {error && <div className="alert error" role="alert">{error}</div>}
    {config && !config.enabled && <div className="alert">The admin service has not been enabled. Complete the database and server setup first.</div>}
    {checking ? <p>Checking administrator access…</p> : session ? <><p>This account does not currently have administrator access.</p><button onClick={() => run(async () => { await client?.auth.signOut({ scope: 'local' }); setError(''); })}>Use another account</button></> :
    <form onSubmit={(event: FormEvent) => { event.preventDefault(); run(async () => { const tokens = await api<{ access_token: string; refresh_token: string }>('/login', { method: 'POST', body: JSON.stringify({ username, password }) }); const result = await client!.auth.setSession(tokens); if (result.error) throw result.error; setPassword(''); }); }}>
      <label>Username or email<input autoComplete="username" value={username} onChange={event => setUsername(event.target.value)} required /></label>
      <label>Password<input type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} required /></label>
      <button className="primary full" disabled={busy || !client || !config?.enabled}>{busy ? 'Signing in…' : 'Sign in'}</button>
      <div className="divider">or</div><button type="button" className="full" disabled={busy || !client || !config?.enabled} onClick={() => run(async () => { const result = await client!.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: `${window.location.origin}/admin/` } }); if (result.error) throw result.error; })}>Continue with Google</button>
    </form>}
    <p className="login-foot">Restricted to provisioned administrators.</p>
  </div></main>;

  return <div className="app-shell"><aside className="sidebar">
    <div className="brand"><span className="brand-symbol">F</span><span>FinCoach<span className="brand-sub">ADMINISTRATION</span></span></div>
    <nav aria-label="Admin sections">{tabs.map((item, index) => <button key={item} className={tab === item ? 'active' : ''} onClick={() => { if (!leaveEditor()) return; detailRequest.current++; setTab(item); setPage(0); setEditing(false); setDetail(null); setDirty(false); setError(''); setNotice(''); }}><span className="nav-icon">{['◫', '◎', '▤', '⌕', '↺'][index]}</span>{item}</button>)}</nav>
    <div className="sidebar-foot"><span className="status-dot" /> Administrator<button onClick={() => { if (leaveEditor()) run(async () => { await client?.auth.signOut(); setAllowed(false); }); }}>Sign out</button></div>
  </aside><main className="workspace"><header className="page-header"><div><p className="eyebrow">FINCOACH WORKSPACE</p><h1>{tab}</h1><p className="muted">{({ Overview: 'Monitor accounts, knowledge, and service readiness.', Accounts: 'Manage student access while preserving their records.', 'Knowledge base': 'Maintain reviewed financial guidance for the AI coach.', 'Search test': 'Check the sources returned by the published knowledge base.', 'Audit history': 'Review account and knowledge-management changes.' })[tab]}</p></div><button disabled={busy} onClick={() => run(async () => { await loadPage(); if (detail) await openSource(detail.source.id, true); })}>↻ Refresh</button></header>
    {error && <div ref={errorMessage} className="alert error" role="alert" tabIndex={-1}>{error}</div>}{notice && <div className="alert success" role="status">{notice}</div>}
    {tab === 'Overview' && <>{dashboard ? <><div className="stats-grid">{[['Accounts', 'account_access'], ['Knowledge documents', 'knowledge_sources'], ['Coaching sessions', 'coaching_sessions'], ['Coaching messages', 'coaching_messages']].map(([label, key]) => <section className="stat" key={key}><span>{label}</span><strong>{dashboard.counts[key].toLocaleString()}</strong><span className="muted small">Across FinCoach</span></section>)}</div><div className="two-column"><section className="panel"><h2>Service status</h2>{Object.entries(dashboard.components).map(([key, value]) => <div className="status-row" key={key}><span>{key === 'ocr' ? 'Receipt OCR' : 'Knowledge embeddings'}</span>{badge(value)}</div>)}{Object.entries(dashboard.providers).map(([key, configured]) => <div className="status-row" key={key}><span>{key.startsWith('llm') ? 'LLM provider' : 'Tavily search'}</span>{badge(configured ? 'configured' : 'not_configured')}</div>)}<p className="muted small">Provider configuration does not confirm current network availability.</p></section><section className="panel"><h2>Needs attention</h2><div className="status-row"><span>Suspended accounts</span><strong>{dashboard.counts.suspended_accounts}</strong></div><div className="status-row"><span>Failed document revisions</span><strong>{dashboard.counts.failed_revisions}</strong></div><p className="muted">Review failed revisions in the knowledge base and retry preparation after resolving the source problem.</p></section></div></> : <div className="panel empty">Loading overview…</div>}</>}
    {tab === 'Accounts' && <section className="panel"><div className="panel-toolbar"><h2>Student accounts</h2><label className="search-input">Search email<input value={searchEmail} onChange={event => { setSearchEmail(event.target.value); setPage(0); }} placeholder="student@example.com" /></label></div><div className="table-scroll"><table><thead><tr><th>Account</th><th>Role</th><th>Status</th><th>Last sign-in</th><th>Access</th></tr></thead><tbody>{accounts.map(account => <tr key={account.user_id}><td><strong>{account.display_name || 'FinCoach user'}</strong><span className="cell-sub">{account.email}</span></td><td>{account.role}</td><td>{badge(account.status)}</td><td>{fmt(account.last_sign_in_at)}</td><td>{account.role === 'student' ? <button disabled={busy} onClick={() => { setAccountAction(account); setReason(''); }}>{account.status === 'active' ? 'Suspend' : 'Restore access'}</button> : <span className="muted small">Protected admin</span>}</td></tr>)}</tbody></table>{!accounts.length && <p className="empty">No matching accounts.</p>}</div></section>}
    {tab === 'Knowledge base' && <>{!editing && <section className="panel"><div className="panel-toolbar"><h2>Knowledge documents</h2><button className="primary" disabled={busy} onClick={() => { detailRequest.current++; setDetail(null); setEditor(emptyEditor()); setEditing(true); setDirty(false); setPreview(null); setError(''); setNotice(''); }}>+ New document</button></div><div className="table-scroll"><table><thead><tr><th>Document</th><th>Availability</th><th>Updated</th><th /></tr></thead><tbody>{sources.map(source => <tr key={source.id}><td><strong>{source.title}</strong><span className="cell-sub">{source.source_key}</span></td><td>{badge(source.archived ? 'archived' : source.published_revision_id ? 'published' : 'draft')}</td><td>{fmt(source.updated_at)}</td><td><button disabled={busy} onClick={() => run(async () => { setOpeningSource(source.id); try { await openSource(source.id); } finally { setOpeningSource(null); } })}>{openingSource === source.id ? 'Opening…' : 'Open'}</button></td></tr>)}</tbody></table>{!sources.length && <p className="empty">No knowledge documents yet. Add your first reviewed source.</p>}</div></section>}
    {editing && <section ref={editorPanel} className="panel editor-panel"><div className="panel-toolbar"><div><h2 ref={editorHeading} tabIndex={-1}>{detail ? 'Edit document' : 'New document'}</h2><p className="muted small">Changes remain a draft until you prepare and publish them.</p></div><div className="actions">{detail?.latest && badge(detail.latest.status)}<button disabled={busy} onClick={closeEditor}>← Back to documents</button></div></div>
      {detail?.latest?.error_message && <div className="alert error">{detail.latest.error_message}</div>}
      <label className="upload-zone">Upload Markdown, text, or a text-based PDF<input type="file" accept=".md,.txt,.pdf" disabled={busy} onChange={event => { const file = event.target.files?.[0]; if (!file) return; run(async () => { const form = new FormData(); form.append('file', file); const result = await api<{ upload_id: string; content: string; filename: string }>('/uploads', { method: 'POST', body: form }); setEditor(old => ({ ...old, title: old.title || result.filename.replace(/\.[^.]+$/, ''), content: result.content, upload_id: result.upload_id })); setDirty(true); setPreview(null); }); event.target.value = ''; }} /><span className="muted small">Maximum 10 MiB · Text is extracted locally · PDFs are edited as text</span></label>
      <label>Document title<input maxLength={200} value={editor.title} onChange={event => edit('title', event.target.value)} /></label>
      <div className="two-column"><label>Source URLs — one per line<textarea rows={3} value={editor.urls} onChange={event => edit('urls', event.target.value)} placeholder="https://official-source.example/guidance" /></label><label>Source last checked<input type="date" max={today()} value={editor.checked_at} onChange={event => edit('checked_at', event.target.value)} /><span className="muted small">Record the date you verified the source.</span></label></div>
      <label>Knowledge content<textarea className="content-editor" rows={16} maxLength={200000} value={editor.content} onChange={event => edit('content', event.target.value)} spellCheck /><span className="muted small">{editor.content.length.toLocaleString()} / 200,000 characters</span></label>
      <div className="actions"><button disabled={busy} onClick={() => run(async () => setPreview(await api<Preview>('/preview', { method: 'POST', body: JSON.stringify(body()) })))}>Preview chunks</button><button className="primary" disabled={busy || !editor.title.trim() || !editor.content.trim()} onClick={() => run(async () => { const result = await api<{ source_id: string }>(detail ? `/knowledge/${detail.source.id}/revisions` : '/knowledge', { method: 'POST', body: JSON.stringify(body()) }); await openSource(result.source_id); await loadPage(); setNotice('Draft saved. Prepare its embeddings before publishing.'); })}>Save draft</button>
      {detail && <><button disabled={busy || dirty || !['draft', 'failed'].includes(detail.latest?.status || '')} onClick={() => run(() => actionKnowledge('prepare', detail.source.latest_revision_id))}>Prepare embeddings</button><button className="primary" disabled={busy || dirty || detail.latest?.status !== 'ready'} onClick={() => setConfirmation({ action: 'publish', revisionId: detail.source.latest_revision_id })}>Publish</button><button className="danger-button" disabled={busy || dirty || detail.source.archived} onClick={() => setConfirmation({ action: 'archive', revisionId: null })}>Archive</button></>}</div>
      {dirty && <p className="muted small">Save your changes before preparing or publishing.</p>}
      {preview && <div className="preview"><h3>{preview.chunk_count} retrieval chunks</h3>{preview.stale && <div className="alert">Source verification is more than 90 days old. Review its current accuracy.</div>}{preview.excerpts.map((excerpt, index) => <details key={index} open={index === 0}><summary>Chunk {index + 1}</summary><pre>{excerpt}</pre></details>)}{preview.chunk_count > 5 && <p className="muted small">Showing the first five chunks.</p>}</div>}
      {detail && <div className="revision-list"><h3>Revision history</h3><p className="muted small">Older prepared revisions can be restored. Previous citations remain available.</p>{detail.revisions.map(revision => <div className="revision-row" key={revision.id}><div><strong>{revision.title}</strong><span className="cell-sub">{fmt(revision.created_at)} · {revision.chunk_count} chunks</span></div>{badge(revision.status)}<div className="actions">{revision.file_path && <button disabled={busy} onClick={() => run(async () => { const result = await api<{ url: string }>(`/knowledge/${detail.source.id}/revisions/${revision.id}/original`); window.open(result.url, '_blank', 'noopener,noreferrer'); })}>Original</button>}{['ready', 'published'].includes(revision.status) && (detail.source.archived || detail.source.published_revision_id !== revision.id) && <button disabled={busy || dirty} onClick={() => setConfirmation({ action: 'restore', revisionId: revision.id })}>Restore version</button>}</div></div>)}</div>}
      {detail && !historyComplete && <button disabled={busy} onClick={() => run(async () => { const requestId = detailRequest.current; const result = await api<{items: Revision[]; total: number}>(`/knowledge/${detail.source.id}/revisions?offset=${detail.revisions.length}`); if (requestId !== detailRequest.current) return; setDetail(old => old && old.source.id === detail.source.id ? {...old, revisions: [...old.revisions, ...result.items]} : old); setHistoryComplete(detail.revisions.length + result.items.length >= result.total); })}>Load older revisions</button>}
    </section>}</>}
    {tab === 'Search test' && <section className="panel"><h2>Test published knowledge</h2><p className="muted">Searches reviewed corpus documents. Student records, Tavily, and LLM generation are excluded from this test.</p><form className="search-form" onSubmit={event => { event.preventDefault(); run(async () => { const result = await api<{ items: Match[] }>('/search', { method: 'POST', body: JSON.stringify({ question }) }); setMatches(result.items); setNotice(result.items.length ? `Retrieved ${result.items.length} excerpts.` : 'No published knowledge matched this query.'); }); }}><input aria-label="Knowledge search question" maxLength={500} value={question} onChange={event => setQuestion(event.target.value)} placeholder="How should a student build an emergency fund?" required /><button className="primary" disabled={busy}>{busy ? 'Searching…' : 'Search knowledge'}</button></form><div className="match-list">{matches.map(match => <article className="match" key={match.id}><h3>{match.title}</h3><p className="muted small">{match.source} · Similarity {match.similarity.toFixed(3)}</p><pre>{match.content}</pre></article>)}</div></section>}
    {tab === 'Audit history' && <section className="panel"><h2>Administrative changes</h2><div className="table-scroll"><table><thead><tr><th>When</th><th>Action</th><th>Target</th><th>Details</th></tr></thead><tbody>{audits.map(entry => <tr key={entry.id}><td>{fmt(entry.created_at)}</td><td><strong>{entry.action}</strong><span className="cell-sub">Actor {entry.actor_id}</span></td><td>{entry.target_type}<span className="cell-sub mono">{entry.target_id}</span></td><td><pre className="small">{JSON.stringify(entry.details, null, 2)}</pre></td></tr>)}</tbody></table>{!audits.length && <p className="empty">No administrative changes recorded.</p>}</div></section>}
    {['Accounts', 'Knowledge base', 'Audit history'].includes(tab) && !(tab === 'Knowledge base' && editing) && <div className="pagination"><span className="muted small">{total ? `${page * 25 + 1}–${Math.min((page + 1) * 25, total)} of ${total}` : '0 records'}</span><button disabled={page === 0 || busy} onClick={() => setPage(old => old - 1)}>Previous</button><button disabled={(page + 1) * 25 >= total || busy} onClick={() => setPage(old => old + 1)}>Next</button></div>}
  </main>
  {accountAction && <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="account-title"><h2 id="account-title">{accountAction.status === 'active' ? 'Suspend account' : 'Restore account access'}</h2><p>{accountAction.email}</p><p className="muted">Financial records are preserved. Suspension stops server access and new notification delivery.</p><label>Reason<textarea maxLength={300} value={reason} onChange={event => setReason(event.target.value)} required /></label><div className="actions"><button disabled={busy} onClick={() => setAccountAction(null)}>Cancel</button><button className="primary" disabled={busy || !reason.trim()} onClick={() => run(async () => { await api(`/accounts/${accountAction.user_id}`, { method: 'PATCH', body: JSON.stringify({ status: accountAction.status === 'active' ? 'suspended' : 'active', expected_status: accountAction.status, reason }) }); setAccountAction(null); await loadPage(); setNotice('Account access updated.'); })}>Confirm</button></div></section></div>}
  {confirmation && <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="knowledge-title"><h2 id="knowledge-title">{confirmation.action === 'archive' ? 'Archive document?' : confirmation.action === 'restore' ? 'Restore this version?' : 'Publish this draft?'}</h2><p className="muted">{confirmation.action === 'archive' ? 'This document will stop appearing in new knowledge searches. Its revisions and saved citations are retained.' : 'This prepared version will become the knowledge used by new coaching answers.'}</p><div className="actions"><button disabled={busy} onClick={() => setConfirmation(null)}>Cancel</button><button className="primary" disabled={busy} onClick={() => run(() => actionKnowledge(confirmation.action, confirmation.revisionId))}>Confirm</button></div></section></div>}
  </div>;
}
