import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  REPORT_ATTEMPT_HEARTBEAT_MS,
  clearReportAttempt,
  loadReportAttempt,
  parseReportAttempt,
  reconcileReportAttempt,
  saveReportAttempt,
  startReportAttemptHeartbeat,
  type ReportAttemptStore,
} from './report-attempt';
import type { CoachReportAttempt } from './types';

function serverAttempt(overrides: Partial<CoachReportAttempt> = {}): CoachReportAttempt {
  return {
    attempt_id: 'attempt-1',
    message_id: 'message-1',
    action_id: 'action-1',
    status: 'active',
    storage_path: 'user-1/coach/attempt-1.pdf',
    period: 'current_month',
    report_type: 'monthly',
    start_date: '2026-10-01',
    end_date: '2026-10-31',
    category_id: null,
    category_name: null,
    report_id: null,
    ...overrides,
  };
}

function memoryStore(initial: Record<string, string> = {}) {
  const items = new Map(Object.entries(initial));
  const store: ReportAttemptStore = {
    getItemAsync: vi.fn(async (key: string) => items.get(key) ?? null),
    setItemAsync: vi.fn(async (key: string, value: string) => {
      items.set(key, value);
    }),
    deleteItemAsync: vi.fn(async (key: string) => {
      items.delete(key);
    }),
  };
  return { store, items };
}

afterEach(() => {
  vi.useRealTimers();
});

describe('saved report attempts', () => {
  it('persists, reloads, and clears one owner-scoped attempt reservation', async () => {
    const { store, items } = memoryStore();
    const record = {
      userId: 'user-1', messageId: 'message-1', actionId: 'action-1', attemptId: 'attempt-1',
    };

    await saveReportAttempt(record, store);
    expect(items.size).toBe(1);
    await expect(loadReportAttempt('user-1', 'message-1', 'action-1', store)).resolves.toEqual(record);

    await clearReportAttempt('user-1', 'message-1', 'action-1', store);
    await expect(loadReportAttempt('user-1', 'message-1', 'action-1', store)).resolves.toBeNull();
  });

  it('never returns another owner or action reservation', async () => {
    const { store } = memoryStore();
    await saveReportAttempt({
      userId: 'user-1', messageId: 'message-1', actionId: 'action-1', attemptId: 'attempt-1',
    }, store);

    await expect(loadReportAttempt('user-2', 'message-1', 'action-1', store)).resolves.toBeNull();
    await expect(loadReportAttempt('user-1', 'message-1', 'action-2', store)).resolves.toBeNull();
  });

  it('treats corrupted local state as absent instead of trusting it', async () => {
    const { store, items } = memoryStore();
    await saveReportAttempt({
      userId: 'user-1', messageId: 'message-1', actionId: 'action-1', attemptId: 'attempt-1',
    }, store);
    for (const key of items.keys()) items.set(key, '{not json');

    await expect(loadReportAttempt('user-1', 'message-1', 'action-1', store)).resolves.toBeNull();
  });

  it('treats a mismatched stored record as absent', async () => {
    const { store, items } = memoryStore();
    await saveReportAttempt({
      userId: 'user-1', messageId: 'message-1', actionId: 'action-1', attemptId: 'attempt-1',
    }, store);
    for (const key of items.keys()) {
      items.set(key, JSON.stringify({
        userId: 'user-1', messageId: 'message-2', actionId: 'action-1', attemptId: 'attempt-1',
      }));
    }

    await expect(loadReportAttempt('user-1', 'message-1', 'action-1', store)).resolves.toBeNull();
  });
});

describe('report attempt payloads', () => {
  it('accepts a complete server-issued attempt', () => {
    expect(parseReportAttempt(serverAttempt())).toEqual(serverAttempt());
  });

  it('rejects payloads that cannot safely drive storage', () => {
    expect(parseReportAttempt(null)).toBeNull();
    expect(parseReportAttempt({})).toBeNull();
    expect(parseReportAttempt(serverAttempt({ storage_path: '' }))).toBeNull();
    expect(parseReportAttempt({ ...serverAttempt(), status: 'expired' })).toBeNull();
    expect(parseReportAttempt({ ...serverAttempt(), report_type: 'weekly' })).toBeNull();
    expect(parseReportAttempt({ ...serverAttempt(), report_id: 'forty-two' })).toBeNull();
  });
});

describe('report attempt reconciliation', () => {
  it('reports a live attempt as active', async () => {
    const attempt = serverAttempt();
    await expect(reconcileReportAttempt({
      attemptId: 'attempt-1',
      fetchAttempt: async () => attempt,
    })).resolves.toEqual({ kind: 'active', attempt });
  });

  it('reports a finished attempt with its saved history row', async () => {
    const attempt = serverAttempt({ status: 'completed', report_id: 42 });
    await expect(reconcileReportAttempt({
      attemptId: 'attempt-1',
      fetchAttempt: async () => attempt,
    })).resolves.toEqual({ kind: 'completed', attempt });
  });

  it('treats a replaced or cancelled attempt as definitively missing', async () => {
    for (const status of ['cancelled', 'superseded'] as const) {
      await expect(reconcileReportAttempt({
        attemptId: 'attempt-1',
        fetchAttempt: async () => serverAttempt({ status }),
      })).resolves.toEqual({ kind: 'missing' });
    }
  });

  it('treats a 404 as missing and any other failure as unknown', async () => {
    await expect(reconcileReportAttempt({
      attemptId: 'attempt-1',
      fetchAttempt: async () => {
        throw Object.assign(new Error('gone'), { status: 404 });
      },
    })).resolves.toEqual({ kind: 'missing' });

    await expect(reconcileReportAttempt({
      attemptId: 'attempt-1',
      fetchAttempt: async () => {
        throw new Error('offline');
      },
    })).resolves.toEqual({ kind: 'unknown' });

    await expect(reconcileReportAttempt({
      attemptId: 'attempt-1',
      fetchAttempt: async () => 'not an attempt',
    })).resolves.toEqual({ kind: 'unknown' });

    await expect(reconcileReportAttempt({
      attemptId: 'attempt-1',
      fetchAttempt: async () => serverAttempt({ attempt_id: 'attempt-2' }),
    })).resolves.toEqual({ kind: 'unknown' });
  });
});

describe('report attempt heartbeat', () => {
  it('renews the five-minute lease once a minute and stops on request', async () => {
    vi.useFakeTimers();
    const renew = vi.fn(async () => serverAttempt());
    const heartbeat = startReportAttemptHeartbeat({ renew });

    await vi.advanceTimersByTimeAsync(REPORT_ATTEMPT_HEARTBEAT_MS * 3);
    expect(renew).toHaveBeenCalledTimes(3);

    heartbeat.stop();
    heartbeat.stop();
    await vi.advanceTimersByTimeAsync(REPORT_ATTEMPT_HEARTBEAT_MS * 2);
    expect(renew).toHaveBeenCalledTimes(3);
  });

  it('keeps one renewal in flight at a time', async () => {
    vi.useFakeTimers();
    let resolveRenew!: () => void;
    const renew = vi.fn(() => new Promise<void>((resolve) => {
      resolveRenew = resolve;
    }));
    const heartbeat = startReportAttemptHeartbeat({ renew });

    await vi.advanceTimersByTimeAsync(REPORT_ATTEMPT_HEARTBEAT_MS * 2);
    expect(renew).toHaveBeenCalledTimes(1);

    resolveRenew();
    await vi.advanceTimersByTimeAsync(REPORT_ATTEMPT_HEARTBEAT_MS);
    expect(renew).toHaveBeenCalledTimes(2);
    heartbeat.stop();
  });

  it('stops and reports a lost attempt while retrying transient failures', async () => {
    vi.useFakeTimers();
    const lost = Object.assign(new Error('lease expired or was replaced'), { status: 404 });
    const renew = vi.fn()
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce(serverAttempt())
      .mockRejectedValueOnce(lost);
    const onLost = vi.fn();
    const heartbeat = startReportAttemptHeartbeat({ renew, onLost });

    await vi.advanceTimersByTimeAsync(REPORT_ATTEMPT_HEARTBEAT_MS * 2);
    expect(renew).toHaveBeenCalledTimes(2);
    expect(onLost).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(REPORT_ATTEMPT_HEARTBEAT_MS * 3);
    expect(renew).toHaveBeenCalledTimes(3);
    expect(onLost).toHaveBeenCalledTimes(1);

    heartbeat.stop();
    expect(onLost).toHaveBeenCalledTimes(1);
  });
});
