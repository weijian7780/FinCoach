import { describe, expect, it, vi } from 'vitest';

import { CoachApiError, createCoachApiClient } from './coach-api';

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

describe('coach API client', () => {
  it('preserves structured report protocol errors and the competing lease', async () => {
    const client = createCoachApiClient({
      baseUrl: 'http://api',
      auth: { getAccessToken: async () => 'token', refreshAccessToken: async () => null },
      fetchImpl: async () => jsonResponse({ detail: {
        code: 'action_in_progress', message: 'Report generation is already in progress.',
        lease_expires_at: '2030-01-01T00:05:00Z',
      } }, 409),
    });
    await expect(client.listConversations()).rejects.toMatchObject({
      status: 409, code: 'action_in_progress', message: 'Report generation is already in progress.',
      leaseExpiresAt: '2030-01-01T00:05:00Z',
    });
  });
  it('keeps the deadline active while the response body is still downloading', async () => {
    vi.useFakeTimers();
    const client = createCoachApiClient({
      baseUrl: 'http://api',
      auth: { getAccessToken: async () => 'token', refreshAccessToken: async () => null },
      timeoutMs: 100,
      fetchImpl: async (_url, init) => ({
        ok: true, status: 200,
        json: () => new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => reject(new Error('aborted body')));
        }),
      }) as Response,
      networkStatus: async () => 'online',
    });
    try {
      let settled: unknown = 'pending';
      void client.listConversations().catch((error: unknown) => { settled = error; });
      await vi.advanceTimersByTimeAsync(101);
      expect(settled).toMatchObject({ code: 'timeout' });
    } finally {
      vi.useRealTimers();
    }
  });

  it('preserves a safe network error when connectivity diagnostics also fail', async () => {
    const client = createCoachApiClient({
      baseUrl: 'http://api',
      auth: { getAccessToken: async () => 'token', refreshAccessToken: async () => null },
      fetchImpl: async () => { throw new Error('socket disconnected'); },
      networkStatus: async () => { throw new Error('native module unavailable'); },
    });
    await expect(client.listConversations()).rejects.toMatchObject({ code: 'network', status: 0 });
  });

  it('waits through the two-minute server deadline and aborts at 150 seconds', async () => {
    vi.useFakeTimers();
    let signal: AbortSignal | undefined;
    const client = createCoachApiClient({
      baseUrl: 'http://api',
      auth: { getAccessToken: async () => 'token', refreshAccessToken: async () => null },
      fetchImpl: async (_url, init) => new Promise<Response>((_resolve, reject) => {
        signal = init?.signal ?? undefined;
        signal?.addEventListener('abort', () => reject(new Error('aborted')));
      }),
      networkStatus: async () => 'online',
    });
    try {
      const outcome = client.listConversations().catch((error: unknown) => error);
      await vi.advanceTimersByTimeAsync(90_000);
      expect(signal?.aborted).toBe(false);
      await vi.advanceTimersByTimeAsync(30_000);
      expect(signal?.aborted).toBe(false);
      await vi.advanceTimersByTimeAsync(30_000);
      expect(await outcome).toMatchObject({ code: 'timeout' });
      expect(signal?.aborted).toBe(true);
      expect(vi.getTimerCount()).toBe(0);
    } finally {
      vi.useRealTimers();
    }
  });

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

  it('classifies an aborted request as a client timeout instead of a connection failure', async () => {
    const fetchImpl = vi.fn().mockImplementation((_url: string, init?: RequestInit) => (
      new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => {
          reject(Object.assign(new Error('Aborted'), { name: 'AbortError' }));
        });
      })
    ));
    const client = createCoachApiClient({
      baseUrl: 'http://api',
      auth: { getAccessToken: vi.fn().mockResolvedValue('token'), refreshAccessToken: vi.fn() },
      fetchImpl,
      timeoutMs: 1,
      networkStatus: vi.fn().mockResolvedValue('online'),
    });

    await expect(client.listConversations()).rejects.toMatchObject({
      status: 0,
      code: 'timeout',
    });
  });

  it('classifies a failed request as offline when device connectivity is unavailable', async () => {
    const client = createCoachApiClient({
      baseUrl: 'http://api',
      auth: { getAccessToken: vi.fn().mockResolvedValue('token'), refreshAccessToken: vi.fn() },
      fetchImpl: vi.fn().mockRejectedValue(new TypeError('Network request failed')),
      networkStatus: vi.fn().mockResolvedValue('offline'),
    });

    await expect(client.listConversations()).rejects.toMatchObject({
      status: 0,
      code: 'offline',
    });
  });

  it('sends a stable client message id to the selected conversation', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ assistant_message: { id: 'reply' } }, 201));
    const client = createCoachApiClient({
      baseUrl: 'http://api',
      auth: { getAccessToken: vi.fn().mockResolvedValue('token'), refreshAccessToken: vi.fn() },
      fetchImpl,
    });

    await client.sendMessage('session-1', 'message-1', ' Help me save ', undefined, 'openrouter-free-v1');

    expect(fetchImpl.mock.calls[0][0]).toBe('http://api/coach/conversations/session-1/messages');
    expect(JSON.parse(fetchImpl.mock.calls[0][1].body)).toEqual({
      message_id: 'message-1',
      content: 'Help me save',
    });
    expect(fetchImpl.mock.calls[0][1].headers).toMatchObject({
      'X-FinCoach-Provider-Consent': 'openrouter-free-v1',
    });
  });

  it('classifies required AI provider consent without exposing server internals', async () => {
    const client = createCoachApiClient({
      baseUrl: 'http://api',
      auth: { getAccessToken: vi.fn().mockResolvedValue('token'), refreshAccessToken: vi.fn() },
      fetchImpl: vi.fn().mockResolvedValue(jsonResponse({ detail: 'AI provider consent is required.' }, 403)),
    });

    await expect(client.sendMessage('session-1', 'message-1', 'Help')).rejects.toMatchObject({
      status: 403,
      code: 'consent_required',
    });
  });

  it('sends the server-owned clarification message and machine value with a follow-up', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ assistant_message: { id: 'reply' } }, 201));
    const client = createCoachApiClient({
      baseUrl: 'http://api',
      auth: { getAccessToken: vi.fn().mockResolvedValue('token'), refreshAccessToken: vi.fn() },
      fetchImpl,
    });

    await client.sendMessage('session-1', 'message-2', 'Tomorrow', {
      assistant_message_id: 'assistant-1',
      value: '2026-07-29',
    });

    expect(JSON.parse(fetchImpl.mock.calls[0][1].body)).toEqual({
      message_id: 'message-2',
      content: 'Tomorrow',
      interaction_reply: {
        assistant_message_id: 'assistant-1',
        value: '2026-07-29',
      },
    });
  });

  it('loads a bounded older-message page using a cursor', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({
      messages: [],
      next_before: '2026-07-17T02:00:00+00:00',
    }));
    const client = createCoachApiClient({
      baseUrl: 'http://api',
      auth: { getAccessToken: vi.fn().mockResolvedValue('token'), refreshAccessToken: vi.fn() },
      fetchImpl,
    });

    await expect(client.listMessages('session-1', {
      limit: 30,
      before: '2026-07-17T03:00:00+00:00',
    })).resolves.toEqual({
      messages: [],
      next_before: '2026-07-17T02:00:00+00:00',
    });

    expect(fetchImpl.mock.calls[0][0]).toBe(
      'http://api/coach/conversations/session-1/messages?limit=30&before=2026-07-17T03%3A00%3A00%2B00%3A00',
    );
  });

  it('persists or clears feedback for one assistant message', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({
      id: 'reply-1',
      feedback: 'helpful',
    }));
    const client = createCoachApiClient({
      baseUrl: 'http://api',
      auth: { getAccessToken: vi.fn().mockResolvedValue('token'), refreshAccessToken: vi.fn() },
      fetchImpl,
    });

    await client.setMessageFeedback('reply-1', 'helpful');

    expect(fetchImpl.mock.calls[0][0]).toBe('http://api/coach/messages/reply-1/feedback');
    expect(fetchImpl.mock.calls[0][1].method).toBe('PATCH');
    expect(JSON.parse(fetchImpl.mock.calls[0][1].body)).toEqual({ feedback: 'helpful' });
  });

  it('confirms, cancels, and completes one server-owned coach action', async () => {
    const fetchImpl = vi.fn().mockImplementation(
      () => Promise.resolve(jsonResponse({ message: { id: 'reply-1' } })),
    );
    const client = createCoachApiClient({
      baseUrl: 'http://api',
      auth: { getAccessToken: vi.fn().mockResolvedValue('token'), refreshAccessToken: vi.fn() },
      fetchImpl,
    });

    await client.confirmAction('reply-1', 'action-1');
    await client.cancelAction('reply-1', 'action-1');
    await client.completeAction('reply-1', 'action-1', true, {
      report_id: 42, storage_path: 'user-1/coach/attempt-1.pdf',
    });

    expect(fetchImpl.mock.calls.map(([url]) => url)).toEqual([
      'http://api/coach/messages/reply-1/actions/confirm',
      'http://api/coach/messages/reply-1/actions/cancel',
      'http://api/coach/messages/reply-1/actions/complete',
    ]);
    expect(JSON.parse(fetchImpl.mock.calls[0][1].body)).toEqual({ action_id: 'action-1' });
    expect(JSON.parse(fetchImpl.mock.calls[2][1].body)).toEqual({
      action_id: 'action-1',
      success: true,
      result: { report_id: 42, storage_path: 'user-1/coach/attempt-1.pdf' },
    });
  });

  it('reserves the attempt id on confirmation and carries it through completion', async () => {
    const fetchImpl = vi.fn().mockImplementation(
      () => Promise.resolve(jsonResponse({ message: { id: 'reply-1' } })),
    );
    const client = createCoachApiClient({
      baseUrl: 'http://api',
      auth: { getAccessToken: vi.fn().mockResolvedValue('token'), refreshAccessToken: vi.fn() },
      fetchImpl,
    });

    await client.confirmAction('reply-1', 'action-1', 'attempt-1');
    await client.completeAction('reply-1', 'action-1', true, {
      title: 'October report',
      file_name: 'FinCoach_October_2026.pdf',
      generated_at: '2026-10-16T00:00:00.000Z',
    }, 'attempt-1');

    expect(JSON.parse(fetchImpl.mock.calls[0][1].body)).toEqual({
      action_id: 'action-1',
      attempt_id: 'attempt-1',
    });
    expect(JSON.parse(fetchImpl.mock.calls[1][1].body)).toEqual({
      action_id: 'action-1',
      success: true,
      result: {
        title: 'October report',
        file_name: 'FinCoach_October_2026.pdf',
        generated_at: '2026-10-16T00:00:00.000Z',
      },
      attempt_id: 'attempt-1',
    });
  });

  it('reads and renews the owner-scoped report attempt', async () => {
    const attempt = { attempt_id: 'attempt-1', status: 'active' };
    const fetchImpl = vi.fn().mockImplementation(() => Promise.resolve(jsonResponse(attempt)));
    const client = createCoachApiClient({
      baseUrl: 'http://api',
      auth: { getAccessToken: vi.fn().mockResolvedValue('token'), refreshAccessToken: vi.fn() },
      fetchImpl,
    });

    await expect(client.getReportAttempt('reply-1', 'attempt-1')).resolves.toEqual(attempt);
    await expect(client.renewReportAttempt('reply-1', 'attempt-1')).resolves.toEqual(attempt);

    expect(fetchImpl.mock.calls.map(([url]) => url)).toEqual([
      'http://api/coach/messages/reply-1/actions/report-attempt/attempt-1',
      'http://api/coach/messages/reply-1/actions/report-attempt/attempt-1/renew',
    ]);
    expect(fetchImpl.mock.calls[0][1].method).toBeUndefined();
    expect(fetchImpl.mock.calls[1][1].method).toBe('POST');
  });
});
