import assert from 'node:assert/strict';
import { test } from 'node:test';
import { canPublish, knowledgeProvenanceLabel, knowledgeSaveNotice, validateKnowledgeContent, validateKnowledgeSave } from '../src/knowledge-editor.ts';

const editor = { title: 'Existing compound-interest guidance', content: 'Existing saved content.', urls: '', checked_at: '', expected_revision_id: 'revision-1' };
const saved = { source: { id: 'source-1', latest_revision_id: 'revision-1' }, latest: { id: 'revision-1', source_urls: [], file_path: null, status: 'published' } };
const today = '2026-10-20';

test('an existing legacy revision can proceed without being imported again', () => {
  assert.doesNotThrow(() => validateKnowledgeSave(editor, saved, today));
});

test('previewing existing text does not require an upload receipt', () => {
  assert.doesNotThrow(() => validateKnowledgeContent(editor, today));
});

test('new documents without an import remain rejected', () => {
  assert.throws(() => validateKnowledgeSave(editor, null, today), /Import a file or webpage first/);
});

test('new file and webpage imports remain valid', () => {
  assert.doesNotThrow(() => validateKnowledgeSave({ ...editor, upload_id: 'upload-1' }, null, today));
  assert.doesNotThrow(() => validateKnowledgeSave({ ...editor, urls: 'https://example.org/guidance' }, null, today));
});

test('existing uploads inherit their saved original reference', () => {
  const uploaded = { ...saved, latest: { ...saved.latest, file_path: 'admin/original.md' } };
  assert.doesNotThrow(() => validateKnowledgeSave(editor, uploaded, today));
  assert.equal(knowledgeProvenanceLabel(editor, uploaded), 'Uploaded original retained in version history');
});

test('a linked source cannot silently lose its only provenance', () => {
  const linked = { ...saved, latest: { ...saved.latest, source_urls: ['https://example.org/original'] } };
  assert.throws(() => validateKnowledgeSave(editor, linked, today), /Import a file or webpage first/);
});

test('stale revision metadata cannot grant a legacy exception', () => {
  assert.throws(() => validateKnowledgeSave({ ...editor, expected_revision_id: 'old-revision' }, saved, today), /Another administrator/);
  assert.throws(() => validateKnowledgeSave(editor, { ...saved, source: { ...saved.source, latest_revision_id: 'newer-revision' } }, today), /Another administrator/);
});

test('legacy documents without file metadata are labelled honestly', () => {
  assert.equal(knowledgeProvenanceLabel(editor, saved), 'No original file or source links recorded');
  assert.equal(knowledgeProvenanceLabel({ ...editor, urls: 'https://example.org/guidance' }, saved), 'https://example.org/guidance');
});

test('published versions are not reported as newly saved drafts', () => {
  assert.equal(knowledgeSaveNotice('published'), 'This version is already published.');
  assert.match(knowledgeSaveNotice('ready'), /ready to publish/);
  assert.match(knowledgeSaveNotice('queued'), /processing/);
});

for (const [name, value, expected] of [
  ['blank title', { ...editor, title: ' ' }, /document title/],
  ['blank content', { ...editor, content: ' ' }, /text first/],
  ['malformed link', { ...editor, urls: 'not a URL' }, /valid source links/],
  ['unsafe scheme', { ...editor, urls: 'file:///private/file' }, /HTTP or HTTPS/],
  ['embedded credentials', { ...editor, urls: 'https://user:secret@example.org' }, /no login details/],
  ['future accuracy date', { ...editor, checked_at: '2026-10-21' }, /today or earlier/],
] as const) {
  test(`preview and save both reject ${name}`, () => {
    assert.throws(() => validateKnowledgeContent(value, today), expected);
    assert.throws(() => validateKnowledgeSave(value, saved, today), expected);
  });
}

test('archived documents can be published again from their prepared version', () => {
  assert.equal(canPublish({ source: { archived: false }, latest: { status: 'ready' } }), true);
  assert.equal(canPublish({ source: { archived: true }, latest: { status: 'ready' } }), true);
  assert.equal(canPublish({ source: { archived: true }, latest: { status: 'published' } }), true);
  assert.equal(canPublish({ source: { archived: false }, latest: { status: 'published' } }), false);
  assert.equal(canPublish({ source: { archived: true }, latest: { status: 'draft' } }), false);
  assert.equal(canPublish({ source: { archived: false }, latest: null }), false);
});
