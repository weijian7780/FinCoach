import type {
  CoachActionResponse,
  CoachConversation,
  CoachInteractionReply,
  CoachMessage,
  CoachMessagePage,
  CoachTurnResponse,
} from './types';
import type { CoachFeedback } from './coach-ui';

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export type CoachNetworkStatus = 'online' | 'offline' | 'unknown';
export type CoachErrorCode = 'network' | 'offline' | 'timeout' | 'consent_required';

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

    const execute = async (token: string): Promise<Response> => {
      const controller = new AbortController();
      let timedOut = false;
      const timeout = setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, timeoutMs);
      try {
        return await fetchImpl(`${baseUrl}${path}`, {
          ...init,
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
            ...init.headers,
          },
          signal: controller.signal,
        });
      } catch {
        if (timedOut) {
          throw new CoachApiError(
            0,
            'The financial coach request took too long.',
            'timeout',
          );
        }
        const status = await networkStatus();
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

    let response = await execute(initialToken);
    if (response.status === 401) {
      const refreshedToken = await auth.refreshAccessToken();
      if (!refreshedToken) throw new CoachApiError(401, 'No active session found.');
      response = await execute(refreshedToken);
    }
    if (!response.ok) throw await safeError(response);
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
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
    confirmAction: (messageId: string, actionId: string) =>
      request<CoachActionResponse>(`/coach/messages/${encodeURIComponent(messageId)}/actions/confirm`, {
        method: 'POST',
        body: JSON.stringify({ action_id: actionId }),
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
    ) =>
      request<CoachActionResponse>(`/coach/messages/${encodeURIComponent(messageId)}/actions/complete`, {
        method: 'POST',
        body: JSON.stringify({ action_id: actionId, success, result }),
      }),
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
