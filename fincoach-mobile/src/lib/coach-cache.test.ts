import { describe, expect, it, vi } from 'vitest';

import {
  fetchLatestMessagePageOnce,
  forgetCachedConversation,
  invalidatePendingMessagePage,
  readCachedConversations,
  readCachedMessagePage,
  writeCachedConversations,
  writeCachedMessagePage,
} from './coach-cache';
import type { CoachConversation, CoachMessagePage } from './types';

const page: CoachMessagePage = { messages: [], next_before: null };

function conversation(id: string, userId: string): CoachConversation {
  return { id, user_id: userId, title: id, created_at: '', updated_at: '', last_message_at: '' };
}

describe('coach cache', () => {
  it('shares one in-flight request for the same chat and owner', async () => {
    const fetchPage = vi.fn().mockResolvedValue(page);
    const [first, second] = await Promise.all([
      fetchLatestMessagePageOnce('owner-share', 'chat', fetchPage),
      fetchLatestMessagePageOnce('owner-share', 'chat', fetchPage),
    ]);
    expect(first).toBe(second);
    expect(fetchPage).toHaveBeenCalledTimes(1);
    await fetchLatestMessagePageOnce('owner-share', 'chat', fetchPage);
    expect(fetchPage).toHaveBeenCalledTimes(2);
  });

  it('never shares a request across owners', async () => {
    const fetchPage = vi.fn().mockResolvedValue(page);
    await Promise.all([
      fetchLatestMessagePageOnce('owner-a', 'chat', fetchPage),
      fetchLatestMessagePageOnce('owner-b', 'chat', fetchPage),
    ]);
    expect(fetchPage).toHaveBeenCalledTimes(2);
  });

  it('starts a fresh request after the chat changed on the server', async () => {
    let release!: (value: CoachMessagePage) => void;
    const stale = vi.fn(() => new Promise<CoachMessagePage>((resolve) => { release = resolve; }));
    const fresh = vi.fn().mockResolvedValue(page);
    const before = fetchLatestMessagePageOnce('owner-reply', 'chat', stale);
    invalidatePendingMessagePage('owner-reply', 'chat');
    await fetchLatestMessagePageOnce('owner-reply', 'chat', fresh);
    expect(fresh).toHaveBeenCalledTimes(1);
    release(page);
    await before;
  });

  it('forgets a deleted chat from both caches', () => {
    writeCachedConversations('owner-delete', [conversation('a', 'owner-delete'), conversation('b', 'owner-delete')]);
    writeCachedMessagePage('owner-delete', 'a', page);
    forgetCachedConversation('owner-delete', 'a');
    expect(readCachedMessagePage('owner-delete', 'a')).toBeNull();
    expect(readCachedConversations('owner-delete')?.map((item) => item.id)).toEqual(['b']);
  });
});
