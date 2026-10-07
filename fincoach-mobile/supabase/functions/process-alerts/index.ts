import type { SupabaseClient } from 'npm:@supabase/supabase-js@2.108.1';

import { deliverAlert } from '../_shared/deliver-alerts.ts';
import { isAccountActive } from '../_shared/account-access.ts';
import {
  advanceRecurrence,
  PENDING_ALERT_RECOVERY_DELAY_MS,
  savingsDeadlineReminderAt,
  shouldAttemptAlertDelivery,
  spendingPeriod,
  spendingScheduleIsDue,
  summarizeReceipts,
} from '../_shared/due-domain.ts';
import {
  corsHeaders,
  errorResponse,
  jsonResponse,
  timingSafeEqual,
} from '../_shared/http.ts';
import {
  chunkExpoMessages,
  classifyExpoError,
  nextRetryDelayMilliseconds,
} from '../_shared/push-domain.ts';
import { createServiceClient } from '../_shared/supabase.ts';

const RECOVERABLE_DELIVERY_BATCH_SIZE = 100;

function isUniqueViolation(error: unknown): boolean {
  return Boolean(error && typeof error === 'object' && 'code' in error && error.code === '23505');
}

function dueWithinSevenDays(triggerAt: string | null, now: Date): boolean {
  if (!triggerAt) return false;
  const trigger = new Date(triggerAt).getTime();
  const elapsed = now.getTime() - trigger;
  return Number.isFinite(trigger) && elapsed >= 0 && elapsed <= 7 * 24 * 60 * 60 * 1000;
}

async function insertDeduplicatedAlert(
  service: SupabaseClient,
  value: Record<string, unknown>,
): Promise<boolean> {
  const { error } = await service.from('alerts').insert(value);
  if (!error) return true;
  if (isUniqueViolation(error)) return false;
  throw error;
}

export async function processBillReminders(service: SupabaseClient, now: Date): Promise<number> {
  const { data, error } = await service
    .from('reminders')
    .select('id,user_id,title,amount,due_at,lead_days,recurrence,recurrence_anchor_day,next_trigger_at')
    .eq('enabled', true)
    .not('next_trigger_at', 'is', null)
    .lte('next_trigger_at', now.toISOString())
    .order('next_trigger_at', { ascending: true })
    .limit(100);
  if (error) throw error;

  let claimed = 0;
  for (const reminder of data ?? []) {
    if (!await isAccountActive(service, reminder.user_id)) continue;
    const expectedTrigger = reminder.next_trigger_at as string;
    const nextDue = advanceRecurrence(
      reminder.due_at,
      reminder.recurrence,
      reminder.recurrence_anchor_day,
    );
    const amountText = reminder.amount == null ? '' : ` RM ${Number(reminder.amount).toFixed(2)} is due.`;
    const { data: alertId, error: claimError } = await service.rpc(
      'claim_bill_reminder_occurrence',
      {
        p_reminder_id: reminder.id,
        p_expected_trigger_at: expectedTrigger,
        p_next_due_at: nextDue,
        p_title: reminder.title,
        p_message: `${reminder.title} is coming up.${amountText}`.trim(),
        p_dedupe_key: `bill:${reminder.id}:${expectedTrigger}`,
      },
    );
    if (claimError) throw claimError;
    if (alertId) claimed += 1;
  }
  return claimed;
}

export async function processSavingsDeadlines(service: SupabaseClient, now: Date): Promise<number> {
  const { data: preferences, error } = await service
    .from('notification_preferences')
    .select('user_id,savings_lead_days,savings_reminder_time,timezone')
    .eq('savings_enabled', true)
    .limit(500);
  if (error) throw error;

  let inserted = 0;
  for (const preference of preferences ?? []) {
    if (!await isAccountActive(service, preference.user_id)) continue;
    const { data: goals, error: goalError } = await service
      .from('savings_goals')
      .select('id,name,target_amount,current_amount,deadline')
      .eq('user_id', preference.user_id)
      .not('deadline', 'is', null)
      .limit(100);
    if (goalError) throw goalError;

    for (const goal of goals ?? []) {
      if (!goal.deadline || Number(goal.current_amount) >= Number(goal.target_amount)) continue;
      const triggerAt = savingsDeadlineReminderAt(
        goal.deadline,
        preference.savings_lead_days,
        preference.savings_reminder_time,
        preference.timezone,
      );
      if (!dueWithinSevenDays(triggerAt, now)) continue;

      const remaining = Math.max(Number(goal.target_amount) - Number(goal.current_amount), 0);
      const created = await insertDeduplicatedAlert(service, {
        user_id: preference.user_id,
        type: 'savings_deadline',
        kind: 'alert',
        title: `${String(goal.name).slice(0, 66)} deadline is approaching`,
        message: `RM ${remaining.toFixed(2)} remains before ${goal.deadline}.`,
        savings_goal_id: goal.id,
        source_data: { deadline: goal.deadline },
        dedupe_key: `savings:${goal.id}:deadline:${goal.deadline}`,
        scheduled_for: triggerAt,
      });
      if (created) inserted += 1;
    }
  }
  return inserted;
}

export async function processSpendingReminders(service: SupabaseClient, now: Date): Promise<number> {
  const { data: preferences, error } = await service
    .from('notification_preferences')
    .select('user_id,spending_frequency,spending_weekday,spending_reminder_time,timezone')
    .eq('spending_enabled', true)
    .limit(500);
  if (error) throw error;

  let inserted = 0;
  for (const preference of preferences ?? []) {
    if (!await isAccountActive(service, preference.user_id)) continue;
    const nowIso = now.toISOString();
    if (
      !spendingScheduleIsDue(
        nowIso,
        preference.timezone,
        preference.spending_frequency,
        preference.spending_weekday,
        preference.spending_reminder_time,
      )
    ) {
      continue;
    }

    const period = spendingPeriod(nowIso, preference.timezone, preference.spending_frequency);
    const { count, error: transactionError } = await service
      .from('transactions')
      .select('id', { count: 'exact', head: true })
      .eq('user_id', preference.user_id)
      .gte('transaction_date', period.startDate)
      .lt('transaction_date', period.endDate);
    if (transactionError) throw transactionError;
    if ((count ?? 0) > 0) continue;

    const created = await insertDeduplicatedAlert(service, {
      user_id: preference.user_id,
      type: 'spending_reminder',
      kind: 'insight',
      title: 'Keep your spending record current',
      message:
        preference.spending_frequency === 'daily'
          ? 'Record today’s transactions while they are fresh.'
          : 'Add this week’s transactions to keep your budget accurate.',
      source_data: { periodStart: period.startDate, frequency: preference.spending_frequency },
      dedupe_key: `spending:${preference.spending_frequency}:${period.periodKey}`,
      scheduled_for: nowIso,
    });
    if (created) inserted += 1;
  }
  return inserted;
}

export async function processPushReceipts(
  service: SupabaseClient,
  now: Date,
  fetchImpl: typeof fetch = fetch,
): Promise<number> {
  const { data: alerts, error } = await service
    .from('alerts')
    .select('id,delivery_attempt_count,delivery_receipts')
    .eq('delivery_status', 'sent')
    .order('created_at', { ascending: true })
    .limit(100);
  if (error) throw error;

  const tickets = (alerts ?? []).flatMap((alert) =>
    Object.entries(alert.delivery_receipts ?? {})
      .filter(([, receipt]) => (receipt as { status?: string }).status === 'sent')
      .map(([deviceId, receipt]) => ({
        alertId: alert.id as string,
        deviceId,
        ticketId: (receipt as { ticketId: string }).ticketId,
      })),
  );
  if (tickets.length === 0) return 0;

  const received = new Map<string, { status: string; details?: { error?: string } }>();
  const expoAccessToken = Deno.env.get('EXPO_ACCESS_TOKEN');
  for (const chunk of chunkExpoMessages(tickets, 1000)) {
    const response = await fetchImpl('https://exp.host/--/api/v2/push/getReceipts', {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        ...(expoAccessToken ? { Authorization: `Bearer ${expoAccessToken}` } : {}),
      },
      body: JSON.stringify({ ids: chunk.map((ticket) => ticket.ticketId) }),
    });
    if (!response.ok) continue;
    const payload = (await response.json()) as {
      data?: Record<string, { status: string; details?: { error?: string } }>;
    };
    for (const [ticketId, receipt] of Object.entries(payload.data ?? {})) {
      received.set(ticketId, receipt);
    }
  }

  let updated = 0;
  for (const alert of alerts ?? []) {
    const receipts = { ...(alert.delivery_receipts ?? {}) } as Record<
      string,
      { status: 'sent' | 'delivered' | 'retryable' | 'failed'; ticketId?: string; error?: string }
    >;
    let changed = false;
    for (const [deviceId, stored] of Object.entries(receipts)) {
      if (stored.status !== 'sent' || !stored.ticketId) continue;
      const receipt = received.get(stored.ticketId);
      if (!receipt) continue;
      changed = true;
      if (receipt.status === 'ok') {
        receipts[deviceId] = { ...stored, status: 'delivered' };
      } else {
        const receiptError = receipt.details?.error ?? 'UnknownExpoReceiptError';
        receipts[deviceId] = {
          ...stored,
          status: classifyExpoError(receiptError) === 'retryable' ? 'retryable' : 'failed',
          error: receiptError,
        };
      }
    }
    if (!changed) continue;

    const summary = summarizeReceipts(receipts);
    await Promise.all(
      summary.invalidDeviceIds.map((deviceId) =>
        service
          .from('user_devices')
          .update({ active: false, last_error: 'DeviceNotRegistered' })
          .eq('id', deviceId),
      ),
    );
    const retryAt =
      summary.deliveryStatus === 'retryable'
        ? new Date(
            now.getTime() + nextRetryDelayMilliseconds(alert.delivery_attempt_count),
          ).toISOString()
        : null;
    const { error: updateError } = await service
      .from('alerts')
      .update({
        delivery_receipts: receipts,
        delivery_status: summary.deliveryStatus,
        delivery_error:
          summary.retryableDeviceIds.length > 0 ? 'Temporary Expo receipt failure.' : null,
        next_delivery_attempt_at: retryAt,
        delivered_at:
          summary.deliveryStatus === 'delivered' ||
          summary.deliveryStatus === 'partially_delivered'
            ? now.toISOString()
            : null,
      })
      .eq('id', alert.id);
    if (updateError) throw updateError;
    updated += 1;
  }
  return updated;
}

export async function processRecoverableDeliveries(
  service: SupabaseClient,
  now: Date,
): Promise<number> {
  if (Deno.env.get('ACCOUNT_ACCESS_ENFORCED') === 'true') {
    // Owner status is filtered in SQL before pagination; suspended work is
    // retained without occupying active users' recovery slots.
    const { data, error } = await service.rpc('admin_recoverable_alerts', { p_now: now.toISOString(), p_limit: RECOVERABLE_DELIVERY_BATCH_SIZE });
    if (error) throw error;
    let attempted = 0;
    for (const alert of data ?? []) {
      const result = await deliverAlert(service, alert.id);
      if (result.status !== 'skipped') attempted++;
    }
    return attempted;
  }
  const pendingBefore = new Date(
    now.getTime() - PENDING_ALERT_RECOVERY_DELAY_MS,
  ).toISOString();
  const alertFields = 'id,created_at,delivery_status,next_delivery_attempt_at';

  const { data: pendingAlerts, error: pendingError } = await service
    .from('alerts')
    .select(alertFields)
    .eq('delivery_status', 'pending')
    .lte('created_at', pendingBefore)
    .order('created_at', { ascending: true })
    .limit(RECOVERABLE_DELIVERY_BATCH_SIZE);
  if (pendingError) throw pendingError;

  const { data: retryableAlerts, error: retryableError } = await service
    .from('alerts')
    .select(alertFields)
    .eq('delivery_status', 'retryable')
    .lte('next_delivery_attempt_at', now.toISOString())
    .order('next_delivery_attempt_at', { ascending: true })
    .limit(RECOVERABLE_DELIVERY_BATCH_SIZE);
  if (retryableError) throw retryableError;

  const recoverableAlerts = [
    ...(pendingAlerts ?? []),
    ...(retryableAlerts ?? []),
  ]
    .filter(
      (alert, index, alerts) =>
        alerts.findIndex((candidate) => candidate.id === alert.id) === index,
    )
    .sort((left, right) => {
      const leftDueAt =
        left.delivery_status === 'pending'
          ? left.created_at
          : (left.next_delivery_attempt_at ?? left.created_at);
      const rightDueAt =
        right.delivery_status === 'pending'
          ? right.created_at
          : (right.next_delivery_attempt_at ?? right.created_at);
      return Date.parse(leftDueAt) - Date.parse(rightDueAt);
    })
    .slice(0, RECOVERABLE_DELIVERY_BATCH_SIZE);

  let attempted = 0;
  for (const alert of recoverableAlerts) {
    if (
      !shouldAttemptAlertDelivery(
        {
          deliveryStatus: alert.delivery_status,
          createdAt: alert.created_at,
          nextDeliveryAttemptAt: alert.next_delivery_attempt_at,
        },
        now.toISOString(),
      )
    ) {
      continue;
    }
    await deliverAlert(service, alert.id);
    attempted += 1;
  }
  return attempted;
}

Deno.serve(async (request) => {
  if (request.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });
  if (request.method !== 'POST') return errorResponse('Method not allowed.', 405, 'method_not_allowed');

  const suppliedSecret = request.headers.get('x-fincoach-cron-secret') ?? '';
  const expectedSecret = Deno.env.get('ALERT_CRON_SECRET') ?? '';
  if (!expectedSecret || !timingSafeEqual(suppliedSecret, expectedSecret)) {
    return errorResponse('Cron authentication failed.', 401, 'unauthorized');
  }

  const service = createServiceClient();
  const now = new Date();
  try {
    const bills = await processBillReminders(service, now);
    const savings = await processSavingsDeadlines(service, now);
    const spending = await processSpendingReminders(service, now);
    const receipts = await processPushReceipts(service, now);
    const recoveries = await processRecoverableDeliveries(service, now);
    return jsonResponse({ bills, savings, spending, receipts, recoveries });
  } catch {
    return errorResponse('Scheduled alert processing failed.', 500, 'processing_failed');
  }
});
