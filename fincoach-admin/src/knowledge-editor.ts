/** Shared editor rules. Previewing text never requires an upload receipt. */
export type KnowledgeEditor = {
  title: string; content: string; urls: string; checked_at: string;
  upload_id?: string; expected_revision_id?: string | null;
};
export type SavedKnowledge = {
  source: { id: string; latest_revision_id: string | null };
  latest: { id: string; file_path: string | null; source_urls?: string[] } | null;
} | null;

export function validateKnowledgeContent(editor: KnowledgeEditor, today: string) {
  if (!editor.title.trim()) throw new Error('Enter a document title.');
  if (!editor.content.trim()) throw new Error('Upload a document or paste its text first.');
  for (const value of editor.urls.split('\n').map(url => url.trim()).filter(Boolean)) {
    let url: URL;
    try { url = new URL(value); } catch { throw new Error('Enter valid source links beginning with https:// or http://.'); }
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) {
      throw new Error('Source links must use HTTP or HTTPS and contain no login details.');
    }
  }
  if (editor.checked_at && editor.checked_at > today) throw new Error('Choose a source check date that is today or earlier.');
}

export function validateKnowledgeSave(editor: KnowledgeEditor, detail: SavedKnowledge, today: string) {
  validateKnowledgeContent(editor, today);
  const saved = detail?.latest;
  if (saved && (detail.source.latest_revision_id !== saved.id || editor.expected_revision_id !== saved.id)) {
    throw new Error('Another administrator updated this document. Reopen it before continuing.');
  }
  // Only the loaded, current revision can establish inherited provenance or
  // legacy status. The database independently checks this under its row lock.
  const legacy = saved && !saved.file_path && saved.source_urls?.length === 0;
  if (!editor.urls.trim() && !editor.upload_id && !saved?.file_path && !legacy) {
    throw new Error('Import a file or webpage first.');
  }
}

export function knowledgeProvenanceLabel(editor: KnowledgeEditor, detail: SavedKnowledge) {
  if (editor.urls.trim()) return editor.urls.trim();
  if (editor.upload_id || detail?.latest?.file_path) return 'Uploaded original retained in version history';
  return 'No original file or source links recorded';
}

/** Publishing an archived document's current prepared version un-archives it. */
export function canPublish(detail: { source: { archived: boolean }; latest: { status: string } | null }) {
  const status = detail.latest?.status;
  return status === 'ready' || (detail.source.archived && status === 'published');
}

export function knowledgeSaveNotice(status: string | undefined) {
  if (status === 'published') return 'This version is already published.';
  if (status === 'ready') return 'This draft is ready to publish. Confirm publication below.';
  if (status === 'queued' || status === 'processing') return 'Your saved version is processing. Publication still needs your confirmation.';
  return 'Draft saved. Retry processing before publishing.';
}
