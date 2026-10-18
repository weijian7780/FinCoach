import type { CoachReportAttempt } from './types';

// One server lease lasts five minutes; one heartbeat a minute keeps it alive
// during a slow render without ever outrunning the server-side renewal rule.
export const REPORT_ATTEMPT_HEARTBEAT_MS = 60_000;

export type ReportAttemptStore = {
  getItemAsync: (key: string) => Promise<string | null>;
  setItemAsync: (key: string, value: string) => Promise<void>;
  deleteItemAsync: (key: string) => Promise<void>;
};

// The device reserves one attempt id and persists it before the confirmation
// request leaves, so a lost acknowledgement is reconciled instead of silently
// replaced by a second attempt.
export type SavedReportAttempt = {
  userId: string;
  messageId: string;
  actionId: string;
  attemptId: string;
};

function reportAttemptKey(userId: string, messageId: string, actionId: string) {
  return `fincoach.report-attempt.${userId}.${messageId}.${actionId}`;
}

async function nativeStore(): Promise<ReportAttemptStore> {
  return import('expo-secure-store');
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0;
}

export function parseSavedReportAttempt(value: unknown): SavedReportAttempt | null {
  if (!isRecord(value)) return null;
  const { userId, messageId, actionId, attemptId } = value;
  if (!nonEmptyString(userId) || !nonEmptyString(messageId) || !nonEmptyString(actionId)
    || !nonEmptyString(attemptId)) {
    return null;
  }
  return { userId, messageId, actionId, attemptId };
}

export async function saveReportAttempt(
  record: SavedReportAttempt,
  store?: ReportAttemptStore,
): Promise<void> {
  const selectedStore = store ?? await nativeStore();
  await selectedStore.setItemAsync(
    reportAttemptKey(record.userId, record.messageId, record.actionId),
    JSON.stringify(record),
  );
}

export async function loadReportAttempt(
  userId: string,
  messageId: string,
  actionId: string,
  store?: ReportAttemptStore,
): Promise<SavedReportAttempt | null> {
  const selectedStore = store ?? await nativeStore();
  const raw = await selectedStore.getItemAsync(
    reportAttemptKey(userId, messageId, actionId),
  );
  let stored: unknown = null;
  try {
    stored = raw ? JSON.parse(raw) : null;
  } catch {
    // A corrupted entry is treated as absent; the retry then reconciles from
    // the server instead of trusting unreadable local state.
    return null;
  }
  const record = parseSavedReportAttempt(stored);
  if (!record || record.userId !== userId || record.messageId !== messageId
    || record.actionId !== actionId) {
    return null;
  }
  return record;
}

export async function clearReportAttempt(
  userId: string,
  messageId: string,
  actionId: string,
  store?: ReportAttemptStore,
): Promise<void> {
  const selectedStore = store ?? await nativeStore();
  await selectedStore.deleteItemAsync(reportAttemptKey(userId, messageId, actionId));
}

const REPORT_ATTEMPT_STATUSES = ['active', 'completed', 'cancelled', 'superseded'] as const;
const REPORT_ATTEMPT_TYPES = [
  'monthly', 'monthly_category', 'multi_month', 'multi_month_category', 'custom', 'custom_category',
] as const;

/** Validate a server-issued attempt before any storage path or id is trusted. */
export function parseReportAttempt(value: unknown): CoachReportAttempt | null {
  if (!isRecord(value)) return null;
  const {
    attempt_id: attemptId,
    message_id: messageId,
    action_id: actionId,
    status,
    storage_path: storagePath,
    period,
    report_type: reportType,
    start_date: startDate,
    end_date: endDate,
    category_id: categoryId,
    category_name: categoryName,
    report_id: reportId,
    lease_expires_at: leaseExpiresAt,
    server_time: serverTime,
    lease_valid: leaseValid,
  } = value;
  if (!nonEmptyString(attemptId) || !nonEmptyString(messageId) || !nonEmptyString(actionId)) {
    return null;
  }
  if (typeof status !== 'string'
    || !(REPORT_ATTEMPT_STATUSES as readonly string[]).includes(status)) {
    return null;
  }
  if (!nonEmptyString(storagePath) || !nonEmptyString(period)) return null;
  if (typeof reportType !== 'string'
    || !(REPORT_ATTEMPT_TYPES as readonly string[]).includes(reportType)) {
    return null;
  }
  if (typeof startDate !== 'string' || typeof endDate !== 'string') return null;
  if (categoryId != null && typeof categoryId !== 'number') return null;
  if (categoryName != null && typeof categoryName !== 'string') return null;
  if (reportId != null && typeof reportId !== 'number') return null;
  if (leaseExpiresAt !== undefined && (typeof leaseExpiresAt !== 'string' || !Number.isFinite(Date.parse(leaseExpiresAt)))) return null;
  if (serverTime !== undefined && (typeof serverTime !== 'string' || !Number.isFinite(Date.parse(serverTime)))) return null;
  if (leaseValid !== undefined && typeof leaseValid !== 'boolean') return null;
  return {
    attempt_id: attemptId,
    message_id: messageId,
    action_id: actionId,
    status: status as CoachReportAttempt['status'],
    storage_path: storagePath,
    period,
    report_type: reportType as CoachReportAttempt['report_type'],
    start_date: startDate,
    end_date: endDate,
    category_id: categoryId ?? null,
    category_name: categoryName ?? null,
    report_id: reportId ?? null,
    ...(leaseExpiresAt !== undefined ? { lease_expires_at: leaseExpiresAt as string } : {}),
    ...(serverTime !== undefined ? { server_time: serverTime as string } : {}),
    ...(leaseValid !== undefined ? { lease_valid: leaseValid as boolean } : {}),
  };
}

/** A 404 from the coach API is the only definitive "no live attempt" answer. */
export function isAttemptGone(error: unknown): boolean {
  return isRecord(error) && (error.status === 404
    || error.code === 'attempt_expired' || error.code === 'attempt_id_reused');
}

export type ReportAttemptReconciliation =
  | { kind: 'active'; attempt: CoachReportAttempt }
  | { kind: 'completed'; attempt: CoachReportAttempt }
  | { kind: 'missing' }
  | { kind: 'unknown' };

/**
 * Resolve what the server actually did with one attempt id after an uncertain
 * response. `unknown` never permits cleanup: only a definitive server answer
 * may discard the persisted reservation.
 */
export async function reconcileReportAttempt(options: {
  attemptId: string;
  fetchAttempt: (attemptId: string) => Promise<unknown>;
}): Promise<ReportAttemptReconciliation> {
  let response: unknown;
  try {
    response = await options.fetchAttempt(options.attemptId);
  } catch (error) {
    return isAttemptGone(error) ? { kind: 'missing' } : { kind: 'unknown' };
  }
  const attempt = parseReportAttempt(response);
  if (!attempt || attempt.attempt_id !== options.attemptId) return { kind: 'unknown' };
  if (attempt.status === 'active') return { kind: 'active', attempt };
  if (attempt.status === 'completed') return { kind: 'completed', attempt };
  return { kind: 'missing' };
}

export type ReportAttemptHeartbeat = {
  stop: () => void;
};

/**
 * Renew the live lease every minute while the PDF is still rendering. A lease
 * the server no longer recognises (404) stops the heartbeat; transient
 * failures simply wait for the next tick inside the five-minute lease.
 */
export function startReportAttemptHeartbeat(options: {
  renew: () => Promise<unknown>;
  onLost?: () => void;
  intervalMs?: number;
}): ReportAttemptHeartbeat {
  const requested = options.intervalMs ?? REPORT_ATTEMPT_HEARTBEAT_MS;
  const intervalMs = Number.isFinite(requested) && requested > 0
    ? Math.trunc(requested)
    : REPORT_ATTEMPT_HEARTBEAT_MS;
  let stopped = false;
  let inFlight = false;
  let timer: ReturnType<typeof setInterval> | undefined;
  const stop = () => {
    if (stopped) return;
    stopped = true;
    if (timer !== undefined) clearInterval(timer);
  };
  timer = setInterval(() => {
    if (stopped || inFlight) return;
    inFlight = true;
    void options.renew().then(
      () => { inFlight = false; },
      (error: unknown) => {
        inFlight = false;
        if (stopped || !isAttemptGone(error)) return;
        stop();
        options.onLost?.();
      },
    );
  }, intervalMs);
  return { stop };
}
