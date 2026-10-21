import type {
  CoachActionResponse,
  CoachConversation,
  CoachInteractionReply,
  CoachMessage,
  CoachMessagePage,
  CoachReportAttempt,
  CoachTurnResponse,
} from './types';
import type { CoachFeedback } from './coach-ui';

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export type CoachNetworkStatus = 'online' | 'offline' | 'unknown';
export type CoachErrorCode = 'network' | 'offline' | 'timeout' | 'consent_required'
  | 'update_required' | 'action_in_progress' | 'attempt_expired' | 'attempt_id_reused'
  | 'report_artifact_invalid' | 'report_state_conflict';
const REPORT_ERROR_CODES: readonly string[] = ['update_required', 'action_in_progress',
  'attempt_expired', 'attempt_id_reused', 'report_artifact_invalid', 'report_state_conflict'];

export type CoachAuthAdapter = {
  getAccessToken: () => Promise<string | null>;
  refreshAccessToken: () => Promise<string | null>;
};

type ClientOptions = {
  baseUrl?: string;
  auth?: CoachAuthAdapter;
  fetchImpl?: FetchLike;
  timeoutMs?: number;
  networkStatus?: () => Promise<CoachNetworkStatus>;
};

type MessagePageOptions = {
  before?: string | null;
  limit?: number;
};

export class CoachApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly code?: CoachErrorCode,
    public readonly leaseExpiresAt?: string,
  ) {
    super(message);
    this.name = 'CoachApiError';
  }
}

async function nativeNetworkStatus(): Promise<CoachNetworkStatus> {
  const { default: NetInfo } = await import('@react-native-community/netinfo');
  const state = await NetInfo.fetch();
  if (state.isConnected === false || state.isInternetReachable === false) {
    return 'offline';
  }
  return state.isConnected === true ? 'online' : 'unknown';
}

const supabaseAuth: CoachAuthAdapter = {
  async getAccessToken() {
    const { supabase } = await import('./supabase');
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token ?? null;
  },
  async refreshAccessToken() {
    const { supabase } = await import('./supabase');
    const { data, error } = await supabase.auth.refreshSession();
    if (error) return null;
    return data.session?.access_token ?? null;
  },
};

async function safeError(response: Response): Promise<CoachApiError> {
  try {
    const body: unknown = await response.json();
    if (typeof body === 'object' && body !== null && 'detail' in body) {
      const detail = (body as { detail?: unknown }).detail;
      if (typeof detail === 'object' && detail !== null) {
        const value = detail as Record<string, unknown>;
        if (typeof value.message === 'string' && value.message.length <= 200
          && typeof value.code === 'string' && REPORT_ERROR_CODES.includes(value.code)) {
          return new CoachApiError(response.status, value.message, value.code as CoachErrorCode,
            typeof value.lease_expires_at === 'string' ? value.lease_expires_at : undefined);
        }
      }
      if (typeof detail === 'string' && detail.length <= 200) {
        return new CoachApiError(
          response.status,
          detail,
          response.status === 403 && detail === 'AI provider consent is required.'
            ? 'consent_required'
            : undefined,
        );
      }
    }
  } catch {
    // The API may be offline or a proxy may return a non-JSON error page.
  }
  return new CoachApiError(response.status, 'The financial coach request failed.');
}

export function createCoachApiClient(options: ClientOptions = {}) {
  const configuredBaseUrl = options.baseUrl;
  const auth = options.auth ?? supabaseAuth;
  const fetchImpl = options.fetchImpl ?? globalThis.fetch;
  const timeoutMs = options.timeoutMs ?? 150_000;
  const networkStatus = options.networkStatus ?? nativeNetworkStatus;

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const defaultBaseUrl = configuredBaseUrl === undefined
      ? (await import('./env')).fincoachApiUrl
      : configuredBaseUrl;
    const baseUrl = defaultBaseUrl.replace(/\/$/, '');
    if (!baseUrl) throw new CoachApiError(0, 'Missing EXPO_PUBLIC_FINCOACH_API_URL.');
    const initialToken = await auth.getAccessToken();
    if (!initialToken) throw new CoachApiError(401, 'No active session found.');

    const execute = async (token: string): Promise<{ response: Response; value?: T; error?: CoachApiError }> => {
      const controller = new AbortController();
      let timedOut = false;
      const timeout = setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, timeoutMs);
      try {
        const response = await fetchImpl(`${baseUrl}${path}`, {
          ...init,
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
            ...init.headers,
          },
          signal: controller.signal,
        });
        // Fetch resolves at the headers. Keep the deadline until the body has
        // arrived too, otherwise an interrupted download can leave the chat busy.
        if (!response.ok) return { response, error: await safeError(response) };
        return { response, value: response.status === 204 ? undefined : await response.json() as T };
      } catch {
        if (timedOut) {
          throw new CoachApiError(
            0,
            'The financial coach request took too long.',
            'timeout',
          );
        }
        const status = await networkStatus().catch(() => 'unknown' as const);
        if (status === 'offline') {
          throw new CoachApiError(
            0,
            'No internet connection is available.',
            'offline',
          );
        }
        throw new CoachApiError(
          0,
          'Unable to reach the financial coach.',
          'network',
        );
      } finally {
        clearTimeout(timeout);
      }
    };

    let result = await execute(initialToken);
    if (result.response.status === 401) {
      const refreshedToken = await auth.refreshAccessToken();
      if (!refreshedToken) throw new CoachApiError(401, 'No active session found.');
      result = await execute(refreshedToken);
    }
    if (result.error) throw result.error;
    return result.value as T;
  }

  return {
    listConversations: () => request<CoachConversation[]>('/coach/conversations'),
    createConversation: (title = 'New conversation') =>
      request<CoachConversation>('/coach/conversations', {
        method: 'POST',
        body: JSON.stringify({ title: title.trim() }),
      }),
    renameConversation: (sessionId: string, title: string) =>
      request<CoachConversation>(`/coach/conversations/${encodeURIComponent(sessionId)}`, {
        method: 'PATCH',
        body: JSON.stringify({ title: title.trim() }),
      }),
    deleteConversation: (sessionId: string) =>
      request<void>(`/coach/conversations/${encodeURIComponent(sessionId)}`, { method: 'DELETE' }),
    listMessages: (sessionId: string, options: MessagePageOptions = {}) => {
      const params = new URLSearchParams();
      params.set('limit', String(Math.max(1, Math.min(30, options.limit ?? 30))));
      if (options.before) params.set('before', options.before);
      return request<CoachMessagePage>(
        `/coach/conversations/${encodeURIComponent(sessionId)}/messages?${params.toString()}`,
      );
    },
    sendMessage: (
      sessionId: string,
      messageId: string,
      content: string,
      interactionReply?: CoachInteractionReply,
      providerConsent?: string,
    ) =>
      request<CoachTurnResponse>(`/coach/conversations/${encodeURIComponent(sessionId)}/messages`, {
        method: 'POST',
        headers: providerConsent
          ? { 'X-FinCoach-Provider-Consent': providerConsent }
          : undefined,
        body: JSON.stringify({
          message_id: messageId,
          content: content.trim(),
          ...(interactionReply ? { interaction_reply: interactionReply } : {}),
        }),
      }),
    setMessageFeedback: (messageId: string, feedback: CoachFeedback | null) =>
      request<CoachMessage>(`/coach/messages/${encodeURIComponent(messageId)}/feedback`, {
        method: 'PATCH',
        body: JSON.stringify({ feedback }),
      }),
    confirmAction: (messageId: string, actionId: string, attemptId?: string) =>
      request<CoachActionResponse>(`/coach/messages/${encodeURIComponent(messageId)}/actions/confirm`, {
        method: 'POST',
        body: JSON.stringify({
          action_id: actionId,
          ...(attemptId ? { attempt_id: attemptId } : {}),
        }),
      }),
    cancelAction: (messageId: string, actionId: string) =>
      request<CoachActionResponse>(`/coach/messages/${encodeURIComponent(messageId)}/actions/cancel`, {
        method: 'POST',
        body: JSON.stringify({ action_id: actionId }),
      }),
    completeAction: (
      messageId: string,
      actionId: string,
      success: boolean,
      result: Record<string, unknown>,
      attemptId?: string,
    ) =>
      request<CoachActionResponse>(`/coach/messages/${encodeURIComponent(messageId)}/actions/complete`, {
        method: 'POST',
        body: JSON.stringify({
          action_id: actionId,
          success,
          result,
          ...(attemptId ? { attempt_id: attemptId } : {}),
        }),
      }),
    getReportAttempt: (messageId: string, attemptId: string) =>
      request<CoachReportAttempt>(
        `/coach/messages/${encodeURIComponent(messageId)}/actions/report-attempt/${encodeURIComponent(attemptId)}`,
      ),
    renewReportAttempt: (messageId: string, attemptId: string) =>
      request<CoachReportAttempt>(
        `/coach/messages/${encodeURIComponent(messageId)}/actions/report-attempt/${encodeURIComponent(attemptId)}/renew`,
        { method: 'POST' },
      ),
  };
}

const defaultClient = createCoachApiClient();

export const listCoachConversations = defaultClient.listConversations;
export const createCoachConversation = defaultClient.createConversation;
export const renameCoachConversation = defaultClient.renameConversation;
export const deleteCoachConversation = defaultClient.deleteConversation;
export const listCoachMessages = defaultClient.listMessages;
export const sendCoachMessage = defaultClient.sendMessage;
export const setCoachMessageFeedback = defaultClient.setMessageFeedback;
export const confirmCoachAction = defaultClient.confirmAction;
export const cancelCoachAction = defaultClient.cancelAction;
export const completeCoachAction = defaultClient.completeAction;
export const getReportAttempt = defaultClient.getReportAttempt;
export const renewReportAttempt = defaultClient.renewReportAttempt;
