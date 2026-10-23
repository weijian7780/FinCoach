import type { CoachConversation, CoachMessagePage } from './types';

// Memory-only cache: it speeds up tab switching and reopening chats without
// persisting private conversations to device storage. Every entry is scoped to
// its owner before it is read back, and the coach and history screens share it.
const conversationCache = new Map<string, CoachConversation[]>();
const messagePageCache = new Map<string, CoachMessagePage>();
const pendingLatestPages = new Map<string, Promise<CoachMessagePage>>();

function pageKey(userId: string, sessionId: string) {
  return `${userId}:${sessionId}`;
}

export function readCachedConversations(userId: string) {
  return conversationCache.get(userId) ?? null;
}

export function writeCachedConversations(userId: string, conversations: CoachConversation[]) {
  conversationCache.set(userId, conversations);
}

export function readCachedMessagePage(userId: string, sessionId: string) {
  return messagePageCache.get(pageKey(userId, sessionId)) ?? null;
}

export function writeCachedMessagePage(userId: string, sessionId: string, page: CoachMessagePage) {
  messagePageCache.set(pageKey(userId, sessionId), page);
}

export function forgetCachedConversation(userId: string, sessionId: string) {
  messagePageCache.delete(pageKey(userId, sessionId));
  const conversations = conversationCache.get(userId);
  if (conversations) {
    conversationCache.set(userId, conversations.filter((item) => item.id !== sessionId));
  }
}

/**
 * A reply or action update changed the chat on the server, so a page request
 * that started before it may be stale. Later loads must start a fresh one.
 */
export function invalidatePendingMessagePage(userId: string, sessionId: string) {
  pendingLatestPages.delete(pageKey(userId, sessionId));
}

/**
 * Share one in-flight request for a chat's newest page. Focus, reconnect and
 * retry can all ask for the same page at once; they should cost one request.
 * The caller decides whether the result is still current before caching it.
 */
export function fetchLatestMessagePageOnce(
  userId: string,
  sessionId: string,
  fetchPage: () => Promise<CoachMessagePage>,
) {
  const key = pageKey(userId, sessionId);
  const pending = pendingLatestPages.get(key);
  if (pending) return pending;
  const request = fetchPage().finally(() => {
    if (pendingLatestPages.get(key) === request) pendingLatestPages.delete(key);
  });
  pendingLatestPages.set(key, request);
  return request;
}
