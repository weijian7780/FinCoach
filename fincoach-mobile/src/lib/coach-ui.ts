import type { CoachFollowUpSuggestion, CoachInteractionReply, CoachSource, CoachUiPayload } from './types';

export type CoachFeedback = 'helpful' | 'not_helpful';

/** One pending attempt owns its timer; cleanup prevents late UI updates. */
export function scheduleCoachPendingNotice(onVisible: (visible: boolean) => void): () => void {
  onVisible(false);
  const timer = setTimeout(() => onVisible(true), 15_000);
  return () => clearTimeout(timer);
}

export type CoachSendState =
  | { status: 'idle' }
  | { status: 'sending'; content: string; messageId: string; interactionReply?: CoachInteractionReply }
  | { status: 'failed'; content: string; messageId: string; interactionReply?: CoachInteractionReply };

export type CoachSendEvent =
  | { type: 'send'; content: string; messageId: string; interactionReply?: CoachInteractionReply }
  | { type: 'failure' }
  | { type: 'retry' }
  | { type: 'success' };

export function nextCoachSendState(state: CoachSendState, event: CoachSendEvent): CoachSendState {
  if (event.type === 'send') {
    return {
      status: 'sending',
      content: event.content.trim(),
      messageId: event.messageId,
      ...(event.interactionReply ? { interactionReply: event.interactionReply } : {}),
    };
  }
  if (event.type === 'failure' && state.status === 'sending') {
    return {
      status: 'failed',
      content: state.content,
      messageId: state.messageId,
      ...(state.interactionReply ? { interactionReply: state.interactionReply } : {}),
    };
  }
  if (event.type === 'retry' && state.status === 'failed') {
    return {
      status: 'sending',
      content: state.content,
      messageId: state.messageId,
      ...(state.interactionReply ? { interactionReply: state.interactionReply } : {}),
    };
  }
  if (event.type === 'success') return { status: 'idle' };
  return state;
}

export function coachSourceLabel(source: CoachSource): string | null {
  const rawName = source.title?.trim() || source.source?.trim();
  const name = rawName ? readableSourceName(rawName) : null;
  if (!name) return null;
  return `${name} · ${Math.round(source.similarity * 100)}% match`;
}

const SOURCE_ACRONYMS = new Set(['epf', 'kwsp', 'myr', 'perkeso', 'ptptn', 'socso']);

function readableSourceName(value: string): string {
  const fileName = value.replaceAll('\\', '/').split('/').pop() ?? value;
  const looksLikeFileName = /\.(md|pdf|txt)$/i.test(fileName);
  if (!looksLikeFileName) return value;

  const words = fileName
    .replace(/\.(md|pdf|txt)$/i, '')
    .replace(/^official[-_ ]+/i, '')
    .split(/[-_ ]+/)
    .filter(Boolean);

  return words.map((word) => {
    const lower = word.toLowerCase();
    if (SOURCE_ACRONYMS.has(lower)) return lower.toUpperCase();
    return `${lower.charAt(0).toUpperCase()}${lower.slice(1)}`;
  }).join(' ');
}

export type CoachTextSegment = {
  text: string;
  bold: boolean;
};

export type CoachResponseSection = {
  kind: 'action' | 'body' | 'guidance' | 'insight';
  title: 'Educational guidance' | 'Insight' | 'Recommended action' | null;
  content: string;
};

const COACH_SECTION_HEADINGS = {
  insight: { kind: 'insight', title: 'Insight' },
  'recommended action': { kind: 'action', title: 'Recommended action' },
  'educational guidance': { kind: 'guidance', title: 'Educational guidance' },
} as const;

export function parseCoachResponseSections(content: string): CoachResponseSection[] {
  const lines = content.replace(/\r\n?/g, '\n').split('\n');
  const sections: CoachResponseSection[] = [];
  let active: (typeof COACH_SECTION_HEADINGS)[keyof typeof COACH_SECTION_HEADINGS] | null = null;
  let buffer: string[] = [];

  const flush = () => {
    const sectionContent = buffer.join('\n').trim();
    if (sectionContent) {
      sections.push(active
        ? { ...active, content: sectionContent }
        : { kind: 'body', title: null, content: sectionContent });
    }
    buffer = [];
  };

  for (const line of lines) {
    const match = /^\s*\*\*(Insight|Recommended action|Educational guidance)\*\*\s*:?\s*$/i.exec(line);
    if (match) {
      flush();
      active = COACH_SECTION_HEADINGS[
        match[1].toLowerCase() as keyof typeof COACH_SECTION_HEADINGS
      ];
    } else {
      buffer.push(line);
    }
  }
  flush();

  return sections.length > 0
    ? sections
    : [{ kind: 'body', title: null, content: content.trim() }];
}

export function parseCoachMarkdown(content: string): CoachTextSegment[] {
  const segments: CoachTextSegment[] = [];
  const boldPattern = /\*\*([^*\n]+)\*\*/g;
  let cursor = 0;
  let match: RegExpExecArray | null;

  while ((match = boldPattern.exec(content)) !== null) {
    if (match.index > cursor) {
      segments.push({ text: content.slice(cursor, match.index), bold: false });
    }
    segments.push({ text: match[1], bold: true });
    cursor = match.index + match[0].length;
  }

  if (cursor < content.length) {
    segments.push({ text: content.slice(cursor), bold: false });
  }
  return segments.length > 0 ? segments : [{ text: content, bold: false }];
}

export function coachSourceDisclosure(sourceCount: number, expanded: boolean) {
  if (sourceCount <= 0) {
    return { label: 'No sources', showSources: false };
  }
  return {
    label: expanded ? 'Hide sources' : `View sources (${sourceCount})`,
    showSources: expanded,
  };
}

// The backend selects next-step chips beside its verified-tool and routing
// logic (branching on the tool that answered and dropping intents the user
// already raised) and delivers them in the assistant message's ui_payload. The
// client only reads and validates that payload — it no longer guesses from the
// answer text, which produced the same repeated pair on every budget reply.
export function coachFollowUpChips(payload: CoachUiPayload | undefined): CoachFollowUpSuggestion[] {
  if (!payload || !('follow_ups' in payload) || !Array.isArray(payload.follow_ups)) {
    return [];
  }
  return payload.follow_ups
    .filter(
      (chip): chip is CoachFollowUpSuggestion =>
        !!chip &&
        typeof chip.label === 'string' &&
        typeof chip.query === 'string' &&
        chip.label.trim().length > 0 &&
        chip.query.trim().length > 0,
    )
    .slice(0, 3);
}

export function nextCoachFeedback(
  current: CoachFeedback | null,
  selected: CoachFeedback,
): CoachFeedback | null {
  return current === selected ? null : selected;
}

export function validateCoachTitle(title: string): string | null {
  const length = title.trim().length;
  if (length === 0) return 'Conversation name is required.';
  if (length > 80) return 'Conversation name must be 80 characters or fewer.';
  return null;
}

export function coachDeleteConfirmation(title: string): string {
  return `Delete “${title}”? This conversation and its messages cannot be undone.`;
}
