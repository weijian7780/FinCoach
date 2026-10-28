import { LatestRequestGate } from './request-gate';
import { canPublish, knowledgeProvenanceLabel, knowledgeSaveNotice, validateKnowledgeContent, validateKnowledgeSave } from './knowledge-editor';
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { createClient, type Session, type SupabaseClient } from '@supabase/supabase-js';

type Config = { supabase_url: string; publishable_key: string; enabled: boolean };
type Tab = 'Accounts' | 'Knowledge base';
type Account = { user_id: string; role: string; status: string; email: string; display_name: string; created_at: string; last_sign_in_at: string | null };
type Source = { id: string; title: string; source_key: string; archived: boolean; published_revision_id: string | null; latest_revision_id: string | null; updated_at: string };
type Revision = { id: string; title: string; content?: string; source_urls?: string[]; checked_at: string | null; status: string; created_at: string; chunk_count: number; error_message: string | null; file_path: string | null };
type Detail = { source: Source; latest: Revision | null; revisions: Revision[] };
type Editor = { title: string; content: string; urls: string; checked_at: string; upload_id?: string; expected_revision_id?: string | null };
type Preview = { chunk_count: number; excerpts: string[]; stale: boolean };
const tabs: Tab[] = ['Accounts', 'Knowledge base'];
const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kuala_Lumpur', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
const emptyEditor = (): Editor => ({ title: '', content: '', urls: '', checked_at: '' });
const fmt = (value: string | null) => value ? new Date(value).toLocaleString('en-MY') : '—';
const badge = (value: string) => <span className={`badge ${value}`}>{value.replaceAll('_', ' ')}</span>;

export function App() {
  const [config, setConfig] = useState<Config | null>(null);
  const [client, setClient] = useState<SupabaseClient | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [allowed, setAllowed] = useState(false);
  const [checking, setChecking] = useState(false);
  const [tab, setTab] = useState<Tab>('Accounts');
  const [busy, setBusy] = useState(false);
  // React's disabled state may not render between rapid submit events. Reserve
  // the action synchronously so only one import/save can start at a time.
  const actionInFlight = useRef(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [searchEmail, setSearchEmail] = useState('');
  const [sources, setSources] = useState<Source[]>([]);
  const [page, setPage] = useState(0);
  const [total, setTotal] = useState(0);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [editing, setEditing] = useState(false);
  const [openingSource, setOpeningSource] = useState<string | null>(null);
  const [editor, setEditor] = useState<Editor>(emptyEditor);
  const [dirty, setDirty] = useState(false);
  const [inputMode, setInputMode] = useState<'upload' | 'paste' | 'link' | null>(null);
  const [importUrl, setImportUrl] = useState('');
  const [editorStep, setEditorStep] = useState<'add' | 'review' | 'publish'>('add');
  const [saveUncertain, setSaveUncertain] = useState(false);
  // Remember a committed save even if the following read or preparation fails.
  const savedTarget = useRef<{ source_id: string; revision_id: string } | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewError, setPreviewError] = useState('');
  const [historyComplete, setHistoryComplete] = useState(false);
  const [accountAction, setAccountAction] = useState<Account | null>(null);
  const [reason, setReason] = useState('');
  const [confirmation, setConfirmation] = useState<{ action: 'publish' | 'archive' | 'restore'; revisionId: string | null } | null>(null);
  // Prevent stale detail responses from switching the editor to another source.
  const detailRequest = useRef(0);
  const pageRequests = useRef(new LatestRequestGate());
  const editorPanel = useRef<HTMLElement>(null);
  const editorHeading = useRef<HTMLHeadingElement>(null);
  const errorMessage = useRef<HTMLDivElement>(null);

  const api = useCallback(async <T,>(path: string, init: RequestInit = {}): Promise<T> => {
    const token = (await client?.auth.getSession())?.data.session?.access_token;
    let response: Response;
    try {
      response = await fetch(`/api/admin${path}`, { ...init, headers: { ...(init.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers } });
    } catch {
      throw Object.assign(new Error('The admin service could not be reached. Check your connection and try again.'), { status: 0 });
    }
    // A failed upstream request may return plain text instead of JSON.
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      // A delayed error from an old token must not revoke a newer session.
      const currentToken = (await client?.auth.getSession())?.data.session?.access_token;
      if (token && currentToken === token) {
        if (response.status === 403) setAllowed(false);
        if (response.status === 401) { setAllowed(false); await client?.auth.signOut({ scope: 'local' }); }
      }
      throw Object.assign(new Error(typeof body?.detail === 'string' ? body.detail : response.status >= 500 ? 'The admin service is temporarily unavailable. Please retry.' : 'Please check the entered values and try again.'), { status: response.status });
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
      const subscription = instance.auth.onAuthStateChange((_event, next) => { if (!disposed) { pageRequests.current.invalidate(); setSession(next); } });
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
    pageRequests.current.invalidate();
    // Drop previously loaded admin data whenever the authenticated identity
    // changes; authorization is still enforced independently by the server.
    setAccounts([]); setSources([]); setDetail(null); setEditing(false); setPreviewError('');
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
    const request = pageRequests.current.begin();
    if (!allowed) return;
    try {
      if (tab === 'Accounts') { const data = await api<{ items: Account[]; total: number }>(`/accounts?offset=${page * 25}&search=${encodeURIComponent(searchEmail)}`); if (request.isCurrent()) { setAccounts(data.items); setTotal(data.total); } }
      if (tab === 'Knowledge base') { const data = await api<{ items: Source[]; total: number }>(`/knowledge?offset=${page * 25}`); if (request.isCurrent()) { setSources(data.items); setTotal(data.total); } }
    } catch (caught) { if (request.isCurrent()) throw caught; }
  }, [allowed, tab, page, api, searchEmail]);
  useEffect(() => {
    let disposed = false;
    loadPage().catch(caught => { if (!disposed) setError(caught.message); });
    return () => { disposed = true; pageRequests.current.invalidate(); };
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
    if (actionInFlight.current) return;
    actionInFlight.current = true;
    setBusy(true); setError(''); setNotice('');
    try { await action(); } catch (caught) { setError(caught instanceof Error ? caught.message : 'Operation failed. Please retry.'); }
    finally { actionInFlight.current = false; setBusy(false); }
  }

  async function openSource(id: string, preserveEditor = false) {
    const requestId = ++detailRequest.current;
    const data = await api<Detail>(`/knowledge/${id}`);
    if (requestId !== detailRequest.current) return;
    setDetail(data); setEditing(true);
    setHistoryComplete(data.revisions.length < 50);
    if (!preserveEditor) {
      setEditor({ title: data.latest?.title || data.source.title, content: data.latest?.content || '', urls: (data.latest?.source_urls || []).join('\n'), checked_at: data.latest?.checked_at || '', expected_revision_id: data.source.latest_revision_id });
      setDirty(false); setPreview(null); setPreviewError('');
      savedTarget.current = null;
      setSaveUncertain(false);
      setInputMode('paste');
      setEditorStep(data.latest?.status === 'draft' ? 'review' : 'publish');
    }
    return data;
  }
  useEffect(() => {
    if (!allowed || !detail || !['queued', 'processing'].includes(detail.latest?.status || '')) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try { await openSource(detail.source.id, true); }
      catch (caught) { if (!disposed) setError(caught instanceof Error ? caught.message : 'Unable to refresh document status.'); }
      // Starting another request before this one finishes invalidates its
      // response through detailRequest. On slower connections that can leave
      // a completed revision showing "queued" forever. Keep one poll in flight.
      if (!disposed) timer = setTimeout(poll, 3000);
    };
    timer = setTimeout(poll, 3000);
    return () => { disposed = true; clearTimeout(timer); };
  }, [allowed, detail?.source.id, detail?.latest?.status, api]);

  const body = () => ({ title: editor.title, content: editor.content, source_urls: editor.urls.split('\n').map(value => value.trim()).filter(Boolean), checked_at: editor.checked_at || null, expected_revision_id: editor.expected_revision_id || null, upload_id: editor.upload_id || null });
  const edit = (field: keyof Editor, value: string) => { setEditor(old => ({ ...old, [field]: value })); setDirty(true); setPreview(null); setPreviewError(''); setEditorStep('review'); };
  const leaveEditor = () => !dirty || window.confirm('Discard unsaved document changes?');
  const closeEditor = () => {
    if (!leaveEditor()) return;
    detailRequest.current++;
    setEditing(false); setDetail(null); setEditor(emptyEditor()); setDirty(false); setPreview(null); setPreviewError('');
    savedTarget.current = null; setInputMode(null); setEditorStep('add');
    setSaveUncertain(false);
    setError(''); setNotice('');
    // Imports can commit before a response is lost. Refresh the list when
    // leaving so the recovery instruction exposes the already-saved draft.
    void run(loadPage);
  };
  async function actionKnowledge(action: string, revisionId: string | null) {
    if (!detail) return;
    await api(`/knowledge/${detail.source.id}/actions`, { method: 'POST', body: JSON.stringify({ action, revision_id: revisionId, expected_revision_id: detail.source.latest_revision_id }) });
    setConfirmation(null); await openSource(detail.source.id); await loadPage(); setNotice(`Document ${action === 'prepare' ? 'queued for processing' : action === 'archive' ? 'archived' : 'published'}.`);
  }

  function validateEditor() {
    validateKnowledgeSave(editor, detail, today());
  }

  async function previewChunks() {
    if (actionInFlight.current) return;
    actionInFlight.current = true;
    setBusy(true); setPreviewError('');
    try {
      validateKnowledgeContent(editor, today());
      setPreview(await api<Preview>('/preview', { method: 'POST', body: JSON.stringify(body()) }));
    } catch (caught) {
      // Keep preview failures beside their control. Global save errors retain
      // their existing focus/scroll behaviour and lost-response protection.
      setPreview(null);
      setPreviewError(caught instanceof Error ? caught.message : 'Unable to preview chunks. Please retry.');
    } finally { actionInFlight.current = false; setBusy(false); }
  }

  async function importContent(value: { title: string; content: string; source_urls: string[]; upload_id?: string }) {
    const payload = { ...value, checked_at: null, expected_revision_id: detail?.source.latest_revision_id || null };
    // A lost save response may hide a committed draft: never replay blindly.
    let saved: { source_id: string; revision_id: string };
    try {
      saved = await api(detail ? `/knowledge/${detail.source.id}/revisions` : '/knowledge', { method: 'POST', body: JSON.stringify(payload) });
    } catch (caught) {
      setEditor({ title: value.title, content: value.content, urls: value.source_urls.join('\n'), checked_at: '', upload_id: value.upload_id, expected_revision_id: detail?.source.latest_revision_id });
      setDirty(true); setEditorStep('review');
      const status = (caught as { status?: number }).status;
      if (!status || status >= 500) {
        setSaveUncertain(true);
        throw new Error('Import saving could not be confirmed. Check the document list before importing again.');
      }
      throw caught;
    }
    savedTarget.current = saved; setDirty(false); setSaveUncertain(false);
    try { await openSource(saved.source_id); }
    catch {
      setSaveUncertain(true);
      throw new Error('Your document is saved, but its preview could not load. Go back to documents and reopen it before importing again.');
    }
    // Saving precedes queuing; failed processing can always resume the draft.
    try {
      await api(`/knowledge/${saved.source_id}/actions`, { method: 'POST', body: JSON.stringify({ action: 'prepare', revision_id: saved.revision_id, expected_revision_id: saved.revision_id }) });
      await openSource(saved.source_id, true);
    } catch {
      setEditorStep('publish');
      throw new Error('Your document is saved. Reopen it or use Retry processing if processing has not started.');
    }
    setEditorStep('review'); setNotice('Document imported. Check the preview; processing continues in the background.');
  }

  async function saveDocument(prepare: boolean) {
    validateEditor();
    let target = savedTarget.current || (detail?.latest ? { source_id: detail.source.id, revision_id: detail.latest.id } : null);
    if (dirty || !target) {
      let result: { source_id: string; revision_id: string };
      try { result = await api(target ? `/knowledge/${target.source_id}/revisions` : '/knowledge', { method: 'POST', body: JSON.stringify(body()) }); }
      catch (caught) {
        const status = (caught as { status?: number }).status;
        if (!status || status >= 500) {
          // The server may have committed before its response was lost. Do not
          // offer a blind save retry that could create duplicate documents.
          setSaveUncertain(true);
          throw new Error('The save could not be confirmed. Go back to documents and check for your saved draft before saving again.');
        }
        throw caught;
      }
      savedTarget.current = result; target = result;
      setEditor(old => ({ ...old, expected_revision_id: result.revision_id }));
      setDirty(false);
    }
    // A failed preparation must leave the committed draft available for retry.
    let current: Detail | undefined;
    try { current = await openSource(target.source_id); }
    catch { throw new Error('Your draft is saved, but its details could not load. Click Next again or reopen the document.'); }
    if (!current) return;
    if (!prepare) { setEditorStep('review'); setNotice('Draft saved. You can continue when you are ready.'); await loadPage(); return; }
    setEditorStep('publish');
    if (current.source.latest_revision_id !== target.revision_id) throw new Error('Another administrator updated this document. Reopen it before continuing.');
    if (['draft', 'failed'].includes(current.latest?.status || '')) {
      try {
        await api(`/knowledge/${target.source_id}/actions`, { method: 'POST', body: JSON.stringify({ action: 'prepare', revision_id: target.revision_id, expected_revision_id: target.revision_id }) });
      } catch {
        setNotice('Your draft is saved.');
        throw new Error('Processing could not start. Your draft is saved; use Retry processing to try again.');
      }
      current = await openSource(target.source_id, true);
    }
    setNotice(knowledgeSaveNotice(current?.latest?.status));
    await loadPage();
  }

  const revisionBadge = (status: string) => <span className={`badge ${status}`}>{({ queued: 'Processing', processing: 'Processing', ready: 'Ready to publish', failed: 'Processing failed', draft: 'Draft', published: 'Published' } as Record<string, string>)[status] || status}</span>;

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
    </form>}
    <p className="login-foot">Restricted to provisioned administrators.</p>
  </div></main>;

  return <div className="app-shell"><aside className="sidebar">
    <div className="brand"><span className="brand-symbol">F</span><span>FinCoach<span className="brand-sub">ADMINISTRATION</span></span></div>
    <nav aria-label="Admin sections">{tabs.map((item, index) => <button key={item} disabled={busy} className={tab === item ? 'active' : ''} onClick={() => { if (!leaveEditor()) return; detailRequest.current++; setTab(item); setPage(0); setEditing(false); setDetail(null); setDirty(false); setError(''); setNotice(''); }}><span className="nav-icon">{['◎', '▤'][index]}</span>{item}</button>)}</nav>
    <div className="sidebar-foot"><span className="status-dot" /> Administrator<button disabled={busy} onClick={() => { if (leaveEditor()) run(async () => {
      // This browser session should not revoke the same account's mobile login.
      const result = await client?.auth.signOut({ scope: 'local' });
      if (result?.error) throw result.error;
      setAllowed(false);
    }); }}>Sign out</button></div>
  </aside><main className="workspace"><header className="page-header"><div><p className="eyebrow">FINCOACH WORKSPACE</p><h1>{tab}</h1><p className="muted">{({ Accounts: 'Manage student access while preserving their records.', 'Knowledge base': 'Maintain reviewed financial guidance for the AI coach.' })[tab]}</p></div><button disabled={busy} onClick={() => run(async () => { await loadPage(); if (detail) await openSource(detail.source.id, true); })}>↻ Refresh</button></header>
    {error && <div ref={errorMessage} className="alert error" role="alert" tabIndex={-1}>{error}</div>}{notice && <div className="alert success" role="status">{notice}</div>}
    {tab === 'Accounts' && <section className="panel"><div className="panel-toolbar"><h2>Student accounts</h2><label className="search-input">Search email<input value={searchEmail} onChange={event => { setSearchEmail(event.target.value); setPage(0); }} placeholder="student@example.com" /></label></div><div className="table-scroll"><table><thead><tr><th>Account</th><th>Role</th><th>Status</th><th>Last sign-in</th><th>Access</th></tr></thead><tbody>{accounts.map(account => <tr key={account.user_id}><td><strong>{account.display_name || 'FinCoach user'}</strong><span className="cell-sub">{account.email}</span></td><td>{account.role}</td><td>{badge(account.status)}</td><td>{fmt(account.last_sign_in_at)}</td><td>{account.role === 'student' ? <button disabled={busy} onClick={() => { setAccountAction(account); setReason(''); }}>{account.status === 'active' ? 'Suspend' : 'Restore access'}</button> : <span className="muted small">Protected admin</span>}</td></tr>)}</tbody></table>{!accounts.length && <p className="empty">No matching accounts.</p>}</div></section>}
    {tab === 'Knowledge base' && <>{!editing && <section className="panel"><div className="panel-toolbar"><h2>Knowledge documents</h2><button className="primary" disabled={busy} onClick={() => { detailRequest.current++; savedTarget.current = null; setSaveUncertain(false); setInputMode(null); setImportUrl(''); setEditorStep('add'); setDetail(null); setEditor(emptyEditor()); setEditing(true); setDirty(false); setPreview(null); setPreviewError(''); setError(''); setNotice(''); }}>+ New document</button></div><div className="table-scroll"><table><thead><tr><th>Document</th><th>Availability</th><th>Updated</th><th /></tr></thead><tbody>{sources.map(source => <tr key={source.id}><td><strong>{source.title}</strong><span className="cell-sub">{source.source_key}</span></td><td>{badge(source.archived ? 'archived' : source.published_revision_id ? 'published' : 'draft')}</td><td>{fmt(source.updated_at)}</td><td><button disabled={busy} onClick={() => run(async () => { setOpeningSource(source.id); try { await openSource(source.id); } finally { setOpeningSource(null); } })}>{openingSource === source.id ? 'Opening…' : 'Open'}</button></td></tr>)}</tbody></table>{!sources.length && <p className="empty">No knowledge documents yet. Add your first reviewed source.</p>}</div></section>}
    {editing && <section ref={editorPanel} className="panel editor-panel">
      <div className="panel-toolbar"><div><h2 ref={editorHeading} tabIndex={-1}>{detail ? 'Edit document' : 'New document'}</h2><p className="muted small">Add your content, review it, then publish when you are ready.</p></div><button disabled={busy} onClick={closeEditor}>← Back to documents</button></div>
      <ol className="editor-steps" aria-label="Document steps">{(['add', 'review', 'publish'] as const).map((step, index) => <li key={step} aria-current={editorStep === step ? 'step' : undefined} className={editorStep === step ? 'current' : ''}><span>{index + 1}</span>{['Add content', 'Review', 'Publish'][index]}</li>)}</ol>
      {detail?.source.published_revision_id && !detail.source.archived && (dirty || detail.source.published_revision_id !== detail.source.latest_revision_id) && <div className="alert">The published version remains available while you prepare this update.</div>}
      {editorStep === 'add' && <>
        <div className="content-options"><button disabled={busy || saveUncertain} onClick={() => setInputMode('upload')}>Upload file</button><button disabled={busy || saveUncertain} onClick={() => setInputMode('link')}>Paste link</button><p className="muted small">Import a document or a public webpage. We prepare its searchable content automatically.</p></div>
        {inputMode === 'upload' && <label className="upload-zone">Choose a document<input type="file" accept=".md,.txt,.pdf" disabled={busy || saveUncertain} onChange={event => { const file = event.target.files?.[0]; if (!file) return; run(async () => { if (file.size > 10 * 1024 * 1024) throw new Error('Choose a file no larger than 10 MiB.'); if (!file.size) throw new Error('Choose a document containing text.'); const form = new FormData(); form.append('file', file); const value = await api<{ upload_id: string; content: string; filename: string }>('/uploads', { method: 'POST', body: form }); await importContent({ title: value.filename.replace(/\.[^.]+$/, '').slice(0, 200), content: value.content, source_urls: [], upload_id: value.upload_id }); }); event.target.value = ''; }} /><span className="muted small">PDF with selectable text, TXT or Markdown · Maximum 10 MiB. Scanned PDFs are unsupported.</span></label>}
        {inputMode === 'link' && <form onSubmit={event => { event.preventDefault(); run(async () => { const value = await api<{title: string; content: string; source_urls: string[]}>('/imports/link', { method: 'POST', body: JSON.stringify({url: importUrl.trim()}) }); await importContent(value); }); }}><label>Webpage link<input type="url" required value={importUrl} maxLength={2048} disabled={busy || saveUncertain} onChange={event => setImportUrl(event.target.value)} placeholder="https://example.org/financial-guidance" /></label><button className="primary" disabled={busy || saveUncertain || !importUrl.trim()}>{busy ? 'Importing…' : 'Import webpage'}</button><p className="muted small">Imports this page only. Pages requiring login or blocking extraction may need a file upload.</p></form>}
        {busy && <p role="status">Importing and saving your document. Keep this page open until the preview appears.</p>}
        {editor.content.trim() && <div className="actions"><button disabled={busy} onClick={() => setEditorStep('review')}>Next → Review</button><span className="muted small">Your imported content is kept when you go back.</span></div>}
      </>}
      {editorStep === 'review' && <>
        <label>Document title<input maxLength={200} disabled={busy} value={editor.title} onChange={event => edit('title', event.target.value)} /></label>
        <div className="status-row"><span>Search preparation</span>{detail?.source.archived ? badge('archived') : revisionBadge(detail?.latest?.status || 'draft')}</div>
        {['queued', 'processing'].includes(detail?.latest?.status || '') && <p role="status">Preparing searchable content in the background. You can leave and return later.</p>}
        {detail?.latest?.error_message && <div className="alert error">{detail.latest.error_message}</div>}
        <div className="content-review"><h3>Content preview</h3><pre>{editor.content.slice(0, 2000)}{editor.content.length > 2000 ? '\n…' : ''}</pre><p className="muted small">{editor.content.length.toLocaleString()} characters · {knowledgeProvenanceLabel(editor, detail)}</p></div>
        <details className="advanced-details"><summary>Edit extracted content</summary><label>Knowledge content<textarea className="content-editor" rows={10} disabled={busy} maxLength={200000} value={editor.content} onChange={event => edit('content', event.target.value)} spellCheck /></label></details>
        <details className="advanced-details"><summary>Reference details (optional)</summary><label>Source links<textarea rows={2} disabled={busy} value={editor.urls} onChange={event => edit('urls', event.target.value)} /><span className="muted small">Uploaded files do not need a website link. Imported links are recorded automatically.</span></label><label>Source accuracy checked on<input type="date" disabled={busy} max={today()} value={editor.checked_at} onChange={event => edit('checked_at', event.target.value)} /><span className="muted small">Leave blank unless you independently checked the source.</span></label></details>
        <div className="actions"><button disabled={busy} onClick={() => setEditorStep('add')}>← Back to add content</button><button className="primary" disabled={busy || saveUncertain} onClick={() => run(() => saveDocument(true))}>{busy ? 'Saving…' : 'Next → Publish'}</button><button disabled={busy || saveUncertain || (!dirty && !!detail)} onClick={() => run(() => saveDocument(false))}>Save draft</button></div>
      </>}
      {editorStep === 'publish' && detail && <div className="publish-review">
        <div className="panel-toolbar"><h3>{detail.latest?.title || detail.source.title}</h3>{detail.source.archived ? badge('archived') : revisionBadge(detail.latest?.status || 'draft')}</div>
        {detail.source.archived ? (canPublish(detail) ? <p>This document is archived. Publish to make this version available to the AI coach again.</p> : <p>This document is archived and excluded from new knowledge searches.</p>) : ['queued', 'processing'].includes(detail.latest?.status || '') ? <p role="status">Processing your document. You can leave this page and return later. Publication still needs your confirmation.</p> : detail.latest?.status === 'ready' ? <p>Ready to publish. Confirm below to make this version available to the AI coach.</p> : detail.latest?.status === 'published' ? <p>This version is published and available to the AI coach.</p> : <p>Your draft is saved. Retry processing before publishing.</p>}
        {detail.latest?.error_message && <div className="alert error">{detail.latest.error_message}</div>}
        <details className="content-review"><summary>Review saved content</summary><pre>{detail.latest?.content}</pre><p className="muted small">{detail.latest?.source_urls?.join(' · ')} · {detail.latest?.checked_at ? `Accuracy checked ${detail.latest.checked_at}` : 'Accuracy not independently checked'}</p></details>
        <div className="actions"><button disabled={busy} onClick={() => setEditorStep('review')}>← Back to review</button><button className="primary" disabled={busy || dirty || !canPublish(detail)} onClick={() => setConfirmation({ action: 'publish', revisionId: detail.source.latest_revision_id })}>Publish</button>{!detail.source.archived && ['draft', 'failed'].includes(detail.latest?.status || '') && <button disabled={busy} onClick={() => run(() => saveDocument(true))}>Retry processing</button>}</div>
      </div>}
      {editorStep !== 'add' && <details className="advanced-details"><summary>Advanced details</summary><p className="muted small">Inspect how this content will be split for knowledge search.</p><button disabled={busy} onClick={() => void previewChunks()}>Preview chunks</button>
        {previewError && <div className="alert error" role="alert">{previewError}</div>}
        {preview && <div className="preview"><h3>{preview.chunk_count} retrieval chunks</h3>{preview.stale && <div className="alert">Source verification is more than 90 days old. Review its current accuracy.</div>}{preview.excerpts.map((excerpt, index) => <details key={index} open={index === 0}><summary>Chunk {index + 1}</summary><pre>{excerpt}</pre></details>)}{preview.chunk_count > 5 && <p className="muted small">Showing the first five chunks.</p>}</div>}
      </details>}
      {detail && <details className="revision-list"><summary>Version history</summary><p className="muted small">Restore a previous prepared version or download its original file.</p>{detail.revisions.map(revision => <div className="revision-row" key={revision.id}><div><strong>{revision.title}</strong><span className="cell-sub">{fmt(revision.created_at)} · {revision.chunk_count} chunks</span></div>{revisionBadge(revision.status)}<div className="actions">{revision.file_path && <button disabled={busy} onClick={() => run(async () => { const result = await api<{ url: string }>(`/knowledge/${detail.source.id}/revisions/${revision.id}/original`); window.open(result.url, '_blank', 'noopener,noreferrer'); })}>Original</button>}{['ready', 'published'].includes(revision.status) && (detail.source.archived || detail.source.published_revision_id !== revision.id) && <button disabled={busy || dirty} onClick={() => setConfirmation({ action: 'restore', revisionId: revision.id })}>Restore version</button>}</div></div>)}
        {!historyComplete && <button disabled={busy} onClick={() => run(async () => { const requestId = detailRequest.current; const result = await api<{items: Revision[]; total: number}>(`/knowledge/${detail.source.id}/revisions?offset=${detail.revisions.length}`); if (requestId !== detailRequest.current) return; setDetail(old => old && old.source.id === detail.source.id ? {...old, revisions: [...old.revisions, ...result.items]} : old); setHistoryComplete(detail.revisions.length + result.items.length >= result.total); })}>Load older revisions</button>}
      </details>}
      {detail && <div className="document-maintenance"><button className="danger-button" disabled={busy || dirty || detail.source.archived} onClick={() => setConfirmation({ action: 'archive', revisionId: null })}>Archive</button><span className="muted small">Archive removes this document from new knowledge searches and keeps its history.</span></div>}
    </section>}</>}
    {!(tab === 'Knowledge base' && editing) && <div className="pagination"><span className="muted small">{total ? `${page * 25 + 1}–${Math.min((page + 1) * 25, total)} of ${total}` : '0 records'}</span><button disabled={page === 0 || busy} onClick={() => setPage(old => old - 1)}>Previous</button><button disabled={(page + 1) * 25 >= total || busy} onClick={() => setPage(old => old + 1)}>Next</button></div>}
  </main>
  {accountAction && <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="account-title"><h2 id="account-title">{accountAction.status === 'active' ? 'Suspend account' : 'Restore account access'}</h2><p>{accountAction.email}</p><p className="muted">Financial records are preserved. Suspension stops server access and new notification delivery.</p><label>Reason<textarea maxLength={300} value={reason} onChange={event => setReason(event.target.value)} required /></label><div className="actions"><button disabled={busy} onClick={() => setAccountAction(null)}>Cancel</button><button className="primary" disabled={busy || !reason.trim()} onClick={() => run(async () => { await api(`/accounts/${accountAction.user_id}`, { method: 'PATCH', body: JSON.stringify({ status: accountAction.status === 'active' ? 'suspended' : 'active', expected_status: accountAction.status, reason }) }); setAccountAction(null); await loadPage(); setNotice('Account access updated.'); })}>Confirm</button></div></section></div>}
  {confirmation && <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="knowledge-title"><h2 id="knowledge-title">{confirmation.action === 'archive' ? 'Archive document?' : confirmation.action === 'restore' ? 'Restore this version?' : 'Publish this draft?'}</h2><p className="muted">{confirmation.action === 'archive' ? 'This document will stop appearing in new knowledge searches. Its revisions and saved citations are retained.' : 'This prepared version will become the knowledge used by new coaching answers.'}</p><div className="actions"><button disabled={busy} onClick={() => setConfirmation(null)}>Cancel</button><button className="primary" disabled={busy} onClick={() => run(() => actionKnowledge(confirmation.action, confirmation.revisionId))}>Confirm</button></div></section></div>}
  </div>;
}
