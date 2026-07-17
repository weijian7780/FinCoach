import { describe, expect, it, vi } from 'vitest';

import { CoachApiError, createCoachApiClient } from './coach-api';

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

describe('coach API client', () => {
  it('sends bearer auth, JSON content type, method, path, and body', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ id: 'session-1' }, 201));
    const client = createCoachApiClient({
      baseUrl: 'http://10.0.0.2:8000/',
      auth: { getAccessToken: vi.fn().mockResolvedValue('access-token'), refreshAccessToken: vi.fn() },
      fetchImpl,
    });

    await client.createConversation('Semester plan');

    expect(fetchImpl).toHaveBeenCalledOnce();
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe('http://10.0.0.2:8000/coach/conversations');
    expect(init.method).toBe('POST');
    expect(init.headers).toMatchObject({
      Authorization: 'Bearer access-token',
      'Content-Type': 'application/json',
    });
    expect(JSON.parse(init.body)).toEqual({ title: 'Semester plan' });
  });

  it('refreshes once after 401 and retries with the replacement token', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ detail: 'Authentication required.' }, 401))
      .mockResolvedValueOnce(jsonResponse([]));
    const refreshAccessToken = vi.fn().mockResolvedValue('new-token');
    const client = createCoachApiClient({
      baseUrl: 'http://api',
      auth: { getAccessToken: vi.fn().mockResolvedValue('old-token'), refreshAccessToken },
      fetchImpl,
    });

    await expect(client.listConversations()).resolves.toEqual([]);
    expect(refreshAccessToken).toHaveBeenCalledOnce();
    expect(fetchImpl).toHaveBeenCalledTimes(2);
    expect(fetchImpl.mock.calls[1][1].headers.Authorization).toBe('Bearer new-token');
  });

  it('does not retry another client error and exposes only decoded safe detail', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ detail: 'Coaching message limit reached.' }, 429));
    const refreshAccessToken = vi.fn();
    const client = createCoachApiClient({
      baseUrl: 'http://api',
      auth: { getAccessToken: vi.fn().mockResolvedValue('token'), refreshAccessToken },
      fetchImpl,
    });

    await expect(client.listConversations()).rejects.toMatchObject({
      status: 429,
      message: 'Coaching message limit reached.',
    });
    expect(fetchImpl).toHaveBeenCalledOnce();
    expect(refreshAccessToken).not.toHaveBeenCalled();
  });

  it('fails clearly when configuration or session is missing', async () => {
    const auth = { getAccessToken: vi.fn().mockResolvedValue(null), refreshAccessToken: vi.fn() };
    await expect(createCoachApiClient({ baseUrl: '', auth }).listConversations()).rejects.toEqual(
      new CoachApiError(0, 'Missing EXPO_PUBLIC_FINCOACH_API_URL.'),
    );
    await expect(createCoachApiClient({ baseUrl: 'http://api', auth }).listConversations()).rejects.toEqual(
      new CoachApiError(401, 'No active session found.'),
    );
  });

  it('sends a stable client message id to the selected conversation', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ assistant_message: { id: 'reply' } }, 201));
    const client = createCoachApiClient({
      baseUrl: 'http://api',
      auth: { getAccessToken: vi.fn().mockResolvedValue('token'), refreshAccessToken: vi.fn() },
      fetchImpl,
    });

    await client.sendMessage('session-1', 'message-1', ' Help me save ');

    expect(fetchImpl.mock.calls[0][0]).toBe('http://api/coach/conversations/session-1/messages');
    expect(JSON.parse(fetchImpl.mock.calls[0][1].body)).toEqual({
      message_id: 'message-1',
      content: 'Help me save',
    });
  });
});
