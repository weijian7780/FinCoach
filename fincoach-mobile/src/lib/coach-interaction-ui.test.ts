import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

const source = fs.readFileSync(
  path.join(process.cwd(), 'src/components/coach/coach-interaction-card.tsx'),
  'utf8',
);

describe('coach interaction cards', () => {
  it('supports suggested choices, flexible Other text, and natural submission', () => {
    expect(source).toContain('Other');
    expect(source).toContain('Tell FinCoach in your own words');
    expect(source).toContain('clarificationReply');
    expect(source).toContain('multi_select');
  });

  it('lets an executed report be opened through a fresh signed URL', () => {
    expect(source).toContain('createReportSignedUrl');
    expect(source).toContain('fetchReportStoragePath');
    expect(source).toContain('Linking.openURL');
    expect(source).toContain('Open PDF');
    // The button must only appear once the PDF actually exists in storage.
    expect(source).toContain("payload.status === 'executed'");
  });

  it('requires an explicit confirmation and keeps change/cancel controls', () => {
    expect(source).toContain('payload.confirm_label');
    expect(source).toContain('Change details');
    expect(source).toContain('Cancel');
    expect(source).toContain("payload.status === 'pending'");
  });

  it('renders a read clarification through the same card with the same reply shape', () => {
    const messageSource = fs.readFileSync(
      path.join(process.cwd(), 'src/components/coach/coach-message.tsx'),
      'utf8',
    );
    // A read question reuses the clarification card, not the write action card.
    expect(messageSource).toContain('isCoachReadClarification');
    expect(messageSource).toContain('CoachClarificationCard');
    // The reply carries only the assistant message id and answer value — the
    // same interaction_reply structure as the existing write clarification.
    expect(messageSource).toContain('assistant_message_id: message.id');
    expect(messageSource).toContain('value: reply.value');
    // The card accepts the read payload type and still gates submission.
    expect(source).toContain('CoachReadClarificationPayload');
    expect(source).toContain('disabled');
  });
});
